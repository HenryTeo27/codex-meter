"""macOS launch paths and a per-user, event-driven single-instance channel."""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import threading


def configure_path():
    # Finder launches do not inherit the shell's Homebrew or Node version paths.
    choices=[Path('/opt/homebrew/bin'),Path('/usr/local/bin'),Path.home()/'.local/bin',
             Path.home()/'.volta/bin',Path.home()/'.npm-global/bin']
    choices+=sorted((Path.home()/'.nvm/versions/node').glob('*/bin'),reverse=True)
    parts=os.environ.get('PATH','/usr/bin:/bin:/usr/sbin:/sbin').split(os.pathsep)
    os.environ['PATH']=os.pathsep.join(dict.fromkeys(parts+[str(p) for p in choices if p.is_dir()]))


class SingleInstance:
    def __init__(self,data):
        key=hashlib.sha256(str(Path(data).resolve()).encode()).hexdigest()[:20]
        self.folder=Path(tempfile.gettempdir())/f'codex-meter-{os.getuid()}-{key}'
        self.folder.mkdir(mode=0o700,exist_ok=True)
        if self.folder.is_symlink() or self.folder.stat().st_uid!=os.getuid():
            raise RuntimeError('Unsafe instance directory')
        self.path=self.folder/'instance.sock';self.stream=None;self.server=None

    def acquire(self):
        import fcntl
        self.stream=(self.folder/'instance.lock').open('a+')
        try: fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: self.stream.close();self.stream=None;return False
        self.path.unlink(missing_ok=True)
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.server.bind(str(self.path));os.chmod(self.path,0o600);self.server.listen(4)
        return True

    def notify(self):
        import time
        for _ in range(40):
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(0.2);client.connect(str(self.path));client.sendall(b'open')
                return
            except OSError: time.sleep(0.05)

    def listen(self,app):
        def serve():
            while not app.closed:
                try:
                    connection,_=self.server.accept()
                    with connection:
                        connection.settimeout(1)
                        if connection.recv(16)==b'open': app.root.after(0,app.show)
                except (OSError,RuntimeError): return
        threading.Thread(target=serve,daemon=True,name='instance-listener').start()

    def close(self):
        if self.server:
            try: self.server.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.server.close();self.path.unlink(missing_ok=True);self.server=None
        if self.stream: self.stream.close();self.stream=None
