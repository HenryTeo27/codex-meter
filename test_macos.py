"""Portable macOS contract tests, plus native single-instance checks on Mac."""
import json,os,stat,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import mac_updater as update
import meter


class MacTests(unittest.TestCase):
    def test_mac_state_folder_and_override(self):
        with patch.object(meter.sys,'platform','darwin'),patch.dict(os.environ,{'CODEX_METER_DATA_DIR':''}):
            self.assertEqual(meter.state_directory(),Path.home()/'Library/Application Support/CodexMeter')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CODEX_METER_DATA_DIR':folder}):
            self.assertEqual(meter.state_directory(),Path(folder).resolve())

    def test_architecture_specific_release_and_digest(self):
        asset={'name':update.ARCHIVE,'size':100,'digest':'sha256:'+'a'*64,
            'browser_download_url':f'https://github.com/{update.base.REPO}/releases/download/v9.0.0/{update.ARCHIVE}'}
        meta={'tag_name':'v9.0.0','assets':[asset]}
        self.assertEqual(update.release_candidate(meta,'1.0.0')['version'],'9.0.0')
        self.assertIsNone(update.release_candidate(meta,'9.0.0'))
        for field,value in [('name','Windows.zip'),('digest',''),('browser_download_url','https://example.com/app.zip')]:
            with self.assertRaises(ValueError): update.release_candidate({**meta,'assets':[{**asset,field:value}]},'1.0.0')

    def test_unsafe_zip_paths_and_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'app.zip'
            for name in ('../escape','CodexMeter.app/../escape','/tmp/escape','CodexMeter.app/a\\b'):
                with zipfile.ZipFile(archive,'w') as bundle: bundle.writestr(name,'bad')
                if chr(92) in name:
                    archive.write_bytes(archive.read_bytes().replace(name.replace(chr(92),'/').encode(),name.encode()))
                with self.assertRaises(ValueError): update.validate_archive(archive)
            for link in ('/tmp/escape','../../escape'):
                item=zipfile.ZipInfo('CodexMeter.app/link');item.external_attr=(stat.S_IFLNK|0o777)<<16
                with zipfile.ZipFile(archive,'w') as bundle: bundle.writestr(item,link)
                with self.assertRaises(ValueError): update.validate_archive(archive)
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('CodexMeter.app/Contents/Info.plist','test')
                item=zipfile.ZipInfo('CodexMeter.app/Contents/alias');item.external_attr=(stat.S_IFLNK|0o777)<<16
                bundle.writestr(item,'Info.plist')
            update.validate_archive(archive)

    def test_checksum_and_pending_archive(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);stage=data/'updates'/('update-'+'a'*32);stage.mkdir(parents=True)
            archive=stage/update.ARCHIVE;archive.write_bytes(b'package')
            candidate={'version':'9.0.0','size':7,'sha256':hashlib.sha256(b'package').hexdigest(),
                'url':f'https://github.com/{update.base.REPO}/releases/download/v9.0.0/{update.ARCHIVE}'}
            update.base.remember_ready(candidate,stage,data)
            self.assertEqual(update.ready_update(data,'1.0.0'),(candidate,stage.resolve()))
            update.verify(archive,candidate);archive.write_bytes(b'corrupt')
            with self.assertRaises(ValueError): update.verify(archive,candidate)

    @unittest.skipUnless(sys.platform=='darwin','Native macOS file locks')
    def test_single_instance_lock_release_and_notification(self):
        import mac_support,socket
        with tempfile.TemporaryDirectory() as folder:
            first=mac_support.SingleInstance(folder);second=mac_support.SingleInstance(folder)
            try:
                self.assertTrue(first.acquire());self.assertFalse(second.acquire())
                second.notify()
                connection,_=first.server.accept()
                with connection: self.assertEqual(connection.recv(16),b'open')
                first.close();self.assertTrue(second.acquire())
            finally:
                first.close();second.close()

if __name__=='__main__': unittest.main()
