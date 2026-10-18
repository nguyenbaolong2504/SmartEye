"""Download MongoDB 8.0.32 portable for Windows from MongoDB's official ZIP.

Only mongod.exe is downloaded (about 29 MiB compressed). No service is installed.
Python standard library only. Existing executable is preserved.
"""
import io
from pathlib import Path
import struct
import sys
import urllib.request
import zipfile
import zlib

VERSION = '8.0.32'
URL = f'https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{VERSION}.zip'
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'data' / 'tools' / f'mongodb-{VERSION}' / 'mongod.exe'


class RemoteZip(io.RawIOBase):
    def __init__(self):
        with urllib.request.urlopen(urllib.request.Request(URL, method='HEAD'), timeout=30) as response:
            self.size = int(response.headers['Content-Length'])
        self.pos = 0

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def tell(self):
        return self.pos

    def seekable(self):
        return True

    def read(self, size=-1):
        size = min(size if size >= 0 else self.size, self.size - self.pos)
        if size <= 0:
            return b''
        end = self.pos + size - 1
        request = urllib.request.Request(URL, headers={'Range': f'bytes={self.pos}-{end}'})
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {self.pos}-{end}/{self.size}':
                raise RuntimeError('Download server did not honor the requested byte range; no full ZIP downloaded.')
            data = response.read(size + 1)
        if len(data) != size:
            raise RuntimeError('Incomplete download. Please retry.')
        self.pos += size
        return data


def main():
    if sys.platform != 'win32':
        raise SystemExit('This portable download is for Windows x64. Use MongoDB Server or Docker on other platforms.')
    if TARGET.exists():
        print(f'MongoDB executable already exists: {TARGET}')
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(RemoteZip()) as archive:
        entry = next(item for item in archive.infolist() if item.filename.endswith('/bin/mongod.exe'))
        if entry.compress_type != zipfile.ZIP_DEFLATED or entry.compress_size > 150 * 1024 * 1024 or entry.file_size > 300 * 1024 * 1024:
            raise RuntimeError('Unexpected MongoDB package format or size.')
        print(f'Downloading MongoDB {VERSION}: {entry.compress_size / 1024 / 1024:.1f} MiB', flush=True)
        remote = archive.fp
        remote.seek(entry.header_offset)
        header = remote.read(30)
        if header[:4] != b'PK\x03\x04':
            raise RuntimeError('Invalid ZIP entry.')
        name_size, extra_size = struct.unpack('<HH', header[26:30])
        remote.seek(entry.header_offset + 30 + name_size + extra_size)
        data = zlib.decompress(remote.read(entry.compress_size), -15)
        if len(data) != entry.file_size or zlib.crc32(data) != entry.CRC:
            raise RuntimeError('MongoDB ZIP integrity check failed.')
        pending = TARGET.with_suffix('.download')
        pending.write_bytes(data)
        pending.replace(TARGET)
    print(f'Ready: {TARGET}. ZIP CRC verified; no Windows service installed.')


if __name__ == '__main__':
    main()
