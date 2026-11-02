"""Verified, per-user macOS bundle updates. Windows keeps its existing updater."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import posixpath
import re
import shutil
import stat
import subprocess
import time
import uuid
import zipfile
import app_updater as base

open_url=base.open_url
version_tuple=base.version_tuple
remove_stage=base.remove_stage
clean_stale_stages=base.clean_stale_stages
previous_failure=base.previous_failure
BUNDLE='CodexMeter.app'
ARCHIVE='Codex-Meter-macOS-'+platform.machine()+'.zip'


def installed_root(source_file,executable,frozen,data_dir):
    expected=Path.home()/'Applications'/BUNDLE
    return expected if (frozen and Path(executable).resolve().parents[2]==expected.resolve()
        and Path(data_dir).resolve()==(Path.home()/'Library/Application Support/CodexMeter').resolve()) else None


def configure_logon_resume(*args):
    # A pending archive resumes on the next app launch; no login item is added.
    pass


def release_candidate(metadata,current):
    if metadata.get('draft') or metadata.get('prerelease'): return None
    tag=metadata.get('tag_name','')
    if version_tuple(tag)<=version_tuple(current): return None
    assets=[a for a in metadata.get('assets',[]) if a.get('name')==ARCHIVE]
    if len(assets)!=1: raise ValueError('No macOS update for this architecture')
    asset=assets[0];digest=asset.get('digest','');size=asset.get('size')
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest): raise ValueError('Missing update digest')
    if type(size) is not int or not 0<size<=base.MAX_DOWNLOAD: raise ValueError('Invalid update size')
    url=f'https://github.com/{base.REPO}/releases/download/{tag}/{ARCHIVE}'
    if asset.get('browser_download_url')!=url: raise ValueError('Unexpected update URL')
    return {'version':tag.removeprefix('v'),'url':url,'sha256':digest[7:].lower(),'size':size}


def latest_release(current):
    with open_url(base.API) as stream: raw=stream.read(1024*1024+1)
    if len(raw)>1024*1024: raise ValueError('Release metadata too large')
    return release_candidate(json.loads(raw),current)


def validate_archive(archive):
    total=0;seen=set()
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            name=item.filename.rstrip('/')
            if name in ('install-macos.command','README.md','LICENSE','THIRD_PARTY_NOTICES.md'):
                if stat.S_ISLNK(item.external_attr>>16): raise ValueError('Unsafe installer link')
                if name.casefold() in seen: raise ValueError('Duplicate archive entry')
                seen.add(name.casefold());total+=item.file_size
                if total>base.MAX_EXTRACTED: raise ValueError('Bundle too large')
                continue
            if not name or name.split('/')[0]!=BUNDLE or any(p in ('','..','.') for p in name.split('/')) or chr(92) in name:
                raise ValueError('Unsafe bundle path')
            key=name.casefold()
            if key in seen: raise ValueError('Duplicate bundle path')
            seen.add(key);total+=item.file_size
            if total>base.MAX_EXTRACTED or len(seen)>base.MAX_FILES: raise ValueError('Bundle too large')
            if stat.S_ISLNK(item.external_attr>>16):
                link=bundle.read(item).decode('utf-8')
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),link))
                if link.startswith('/') or not target.startswith(BUNDLE+'/'): raise ValueError('Unsafe bundle link')
        # Reject children under any archived link; extraction must not follow aliases.
        links={i.filename.rstrip('/') for i in bundle.infolist() if stat.S_ISLNK(i.external_attr>>16)}
        if any(any(name.startswith(link+'/') for link in links) for name in seen):
            raise ValueError('Archive writes through a link')


def unpack(archive,stage,version):
    validate_archive(archive)
    target=Path(stage)/BUNDLE
    if target.exists(): shutil.rmtree(target)
    subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),str(stage)],check=True,timeout=120,capture_output=True)
    with (target/'Contents/Info.plist').open('rb') as stream: info=plistlib.load(stream)
    if info.get('CFBundleIdentifier')!='com.henryteo.codex-meter' or info.get('CFBundleShortVersionString')!=version:
        raise ValueError('Wrong app identity or version')
    subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(target)],check=True,timeout=60,capture_output=True)
    executable=target/'Contents/MacOS/CodexMeter'
    if not executable.is_file(): raise ValueError('Incomplete app bundle')
    return executable


def ready_update(data,current):
    updates=(Path(data)/'updates').resolve()
    try:
        saved=json.loads((updates/'ready-update.json').read_text());candidate=saved['candidate'];stage=Path(saved['stage']).resolve()
        if (stage.parent!=updates or not re.fullmatch(r'update-[0-9a-f]{32}',stage.name)
            or version_tuple(candidate['version'])<=version_tuple(current) or not (stage/ARCHIVE).is_file()): return None
        release_candidate({'tag_name':'v'+candidate['version'],'assets':[{'name':ARCHIVE,
            'size':candidate['size'],'digest':'sha256:'+candidate['sha256'],'browser_download_url':candidate['url']}]},current)
        return candidate,stage
    except (OSError,ValueError,KeyError,TypeError): return None


def verify(archive,candidate):
    digest=hashlib.sha256()
    with archive.open('rb') as stream:
        while chunk:=stream.read(1024*1024): digest.update(chunk)
    if archive.stat().st_size!=candidate['size'] or digest.hexdigest()!=candidate['sha256']: raise ValueError('Update checksum mismatch')


def resume_ready(data,current,health_check,cancelled=lambda:False):
    ready=ready_update(data,current)
    if ready is None: return None
    candidate,stage=ready
    try:
        if cancelled(): raise RuntimeError('Update cancelled')
        verify(stage/ARCHIVE,candidate)
        health_check(unpack(stage/ARCHIVE,stage,candidate['version']),candidate['version'],stage)
        return ready
    except Exception:
        remove_stage(stage,Path(data)/'updates');raise


def download_and_stage(candidate,data,health_check,cancelled=lambda:False):
    updates=Path(data)/'updates';updates.mkdir(parents=True,exist_ok=True)
    stage=updates/('update-'+uuid.uuid4().hex);stage.mkdir();archive=stage/ARCHIVE
    try:
        size=0;started=time.monotonic()
        with open_url(candidate['url'],30) as stream,archive.open('xb') as output:
            while chunk:=stream.read(1024*1024):
                size+=len(chunk)
                if cancelled() or time.monotonic()-started>600: raise RuntimeError('Update cancelled or timed out')
                if size>candidate['size']: raise ValueError('Update too large')
                output.write(chunk)
        verify(archive,candidate)
        health_check(unpack(archive,stage,candidate['version']),candidate['version'],stage)
        base.remember_ready(candidate,stage,data)
        return stage
    except Exception:
        remove_stage(stage,updates);raise


def start_installer(stage,target,data,helper,version,relaunch):
    stage=Path(stage).resolve();target=Path(target).resolve();data=Path(data).resolve()
    if (target!=(Path.home()/'Applications'/BUNDLE).resolve() or stage.parent!=data/'updates'
        or not re.fullmatch(r'update-[0-9a-f]{32}',stage.name) or not (stage/BUNDLE).is_dir()):
        raise ValueError('Invalid macOS installation path')
    version_tuple(version)
    script=stage/'apply-update.sh';shutil.copyfile(helper,script)
    subprocess.Popen(['/bin/sh',str(script),str(os.getpid()),str(target),str(stage),version,str(int(relaunch))],
        cwd=str(data/'updates'),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
