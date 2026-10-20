"""Seed the public Gradle distribution cache with its official SHA-256."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests

root = Path(__file__).resolve().parents[2]
url = 'https://downloads.gradle.org/distributions/gradle-9.3.1-all.zip'
expected = requests.get(url + '.sha256', timeout=60)
expected.raise_for_status()
print('Retrieved official Gradle checksum', flush=True)
cache = root / '.tools/gradle/wrapper/dists/gradle-9.3.1-all/9ot9r568e8zfvvd4mn8rbu1j0'
cache.mkdir(parents=True, exist_ok=True)
archive = cache / 'gradle-9.3.1-all.zip'
download_url = url.replace('services.gradle.org', 'downloads.gradle.org')
total = 234893460
chunk_size = 1024 * 1024
def segment(start):
    end = min(start + chunk_size, total) - 1
    for attempt in range(3):
        try:
            response = requests.get(download_url, headers={'Range': f'bytes={start}-{end}'}, timeout=30)
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{total}':
                raise ValueError('Invalid download range')
            return response.content
        except requests.RequestException:
            if attempt == 2:
                raise
with ThreadPoolExecutor(max_workers=8) as pool, archive.open('wb') as output:
    for index, data in enumerate(pool.map(segment, range(0, total, chunk_size))):
        output.write(data)
        if index % 16 == 0:
            print('Downloaded', min((index + 1) * chunk_size, total), '/', total, flush=True)
with archive.open('rb') as source:
    digest = hashlib.file_digest(source, 'sha256').hexdigest()
if digest != expected.text.strip():
    raise ValueError('Gradle checksum mismatch')
print('Verified Gradle 9.3.1:', archive.stat().st_size, flush=True)
