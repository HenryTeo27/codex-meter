"""Build on macOS with the architecture of the active Python interpreter."""
import importlib.metadata
import platform
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import meter

if sys.platform!='darwin': raise SystemExit('Build macOS bundles on macOS.')
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
    '--name','CodexMeter','--osx-bundle-identifier','com.henryteo.codex-meter',
    '--icon',str(root/'assets/codex-gradient.png'),
    '--add-data',str(root/'assets/codex-gradient.ico')+':assets',
    '--add-data',str(root/'scripts/apply-update-macos.sh')+':scripts',
    '--collect-all','rich','--collect-all','joblib','--collect-all','tzdata',
    '--hidden-import','pystray._darwin','--hidden-import','orjson','--hidden-import','zoneinfo',
    '--hidden-import','statistics','--hidden-import','csv','--hidden-import','gzip',
    '--hidden-import','argparse','--hidden-import','dataclasses',
    '--exclude-module','numpy','--exclude-module','pandas','--exclude-module','scipy',
    '--exclude-module','matplotlib','--exclude-module','IPython','--exclude-module','pytest',str(root/'meter.py')],cwd=root,check=True)
bundle=root/'dist/CodexMeter.app';info=bundle/'Contents/Info.plist'
with info.open('rb') as stream: metadata=plistlib.load(stream)
metadata.update(CFBundleShortVersionString=meter.VERSION,CFBundleVersion=meter.VERSION,CFBundleDisplayName='Codex Meter')
with info.open('wb') as stream: plistlib.dump(metadata,stream)
licenses=bundle/'Contents/Resources/licenses';licenses.mkdir(exist_ok=True)
for name in ('pystray','Pillow','rich','joblib','cloudpickle','tzdata','orjson','pyinstaller',
             'six','markdown-it-py','mdurl','pygments','pyobjc-core','pyobjc-framework-Cocoa','pyobjc-framework-Quartz'):
    package=importlib.metadata.distribution(name)
    for entry in package.files or []:
        if 'license' in str(entry).lower() or 'copying' in str(entry).lower():
            source=Path(package.locate_file(entry))
            if source.is_file():
                target=licenses/name/str(entry);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for name in ('LICENSE','THIRD_PARTY_NOTICES.md'): shutil.copyfile(root/name,licenses/name)
# Metadata changes invalidate PyInstaller's ad-hoc signature; sign the final bundle.
subprocess.run(['/usr/bin/codesign','--force','--deep','--sign','-',str(bundle)],check=True)
subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(bundle)],check=True)
release=root/'release';release.mkdir(exist_ok=True)
archive=release/f'Codex-Meter-macOS-{platform.machine()}.zip'
subprocess.run(['/usr/bin/ditto','-c','-k','--norsrc','--keepParent',str(bundle),str(archive)],check=True)
installer=root/'install-macos.command';installer.chmod(0o755)
subprocess.run(['/usr/bin/zip','-j',str(archive),str(installer),str(root/'README.md'),str(root/'LICENSE'),str(root/'THIRD_PARTY_NOTICES.md')],check=True)
print(archive)
