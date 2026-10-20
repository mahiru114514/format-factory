"""Fetch a verified public pub archive when the Dart downloader stalls locally."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile

import requests

ROOT = Path(__file__).resolve().parents[2]
name, version = sys.argv[1:3]
response = requests.get(f'https://pub.dev/api/packages/{name}/versions/{version}', timeout=60)
response.raise_for_status()
metadata = response.json()
archive = requests.get(metadata['archive_url'], timeout=120)
archive.raise_for_status()
digest = hashlib.sha256(archive.content).hexdigest()
if digest != metadata['archive_sha256']:
    raise ValueError('Package checksum mismatch')
destination = ROOT / '.tools' / 'pub-cache' / 'hosted' / 'pub.dev' / f'{name}-{version}'
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(archive.content), mode='r:gz') as package:
    package.extractall(destination, filter='data')
hashes = ROOT / '.tools' / 'pub-cache' / 'hosted-hashes' / 'pub.dev'
hashes.mkdir(parents=True, exist_ok=True)
(hashes / f'{name}-{version}.sha256').write_text(digest, encoding='utf-8')
print('Verified pub package:', name, version, len(archive.content), flush=True)
