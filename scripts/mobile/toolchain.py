"""Prepare a project-local mobile toolchain from official download metadata."""
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / '.tools'
TOOLS.mkdir(exist_ok=True)


def download(url, destination, checksum=None, algorithm='sha256'):
    destination = Path(destination)
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + '.part')
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {'Range': f'bytes={existing}-'} if existing else {}
        with requests.get(url, headers=headers, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            append = response.status_code == 206 and existing > 0
            with partial.open('ab' if append else 'wb') as stream:
                size = existing if append else 0
                next_report = size + 100 * 1024 * 1024
                for data in response.iter_content(1024 * 1024):
                    stream.write(data)
                    size += len(data)
                    if size >= next_report:
                        print(destination.name, round(size / 1024**2), 'MiB', flush=True)
                        next_report += 100 * 1024 * 1024
        partial.replace(destination)
    if checksum:
        with destination.open('rb') as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
        if actual.lower() != checksum.lower():
            raise ValueError(f'Checksum mismatch: {destination.name}')
    return destination


def extract(file, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(file) as archive:
        for name in archive.namelist():
            candidate = (destination / name).resolve()
            if not candidate.is_relative_to(destination):
                raise ValueError('Archive path escapes destination')
        archive.extractall(destination)


def flutter():
    url = 'https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json'
    metadata = requests.get(url, timeout=60)
    metadata.raise_for_status()
    metadata = metadata.json()
    release = next(item for item in metadata['releases'] if item['hash'] == metadata['current_release']['stable'])
    print('Flutter stable', release['version'], release['archive'], flush=True)
    (TOOLS / 'flutter-release.json').write_text(json.dumps(release, indent=2), encoding='utf-8')
    if not (TOOLS / 'flutter' / 'bin' / 'flutter.bat').exists():
        archive = download(metadata['base_url'] + '/' + release['archive'], TOOLS / 'flutter-sdk.zip', release['sha256'])
        print('Extracting Flutter', flush=True)
        extract(archive, TOOLS)
    print('Flutter ready', flush=True)


def android():
    response = requests.get('https://dl.google.com/android/repository/repository2-1.xml', timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    packages = [p for p in root.findall('remotePackage') if p.attrib.get('path', '').startswith('cmdline-tools;')]
    # Keep the established Java SDK Manager for deterministic unattended builds.
    package = next(p for p in packages if p.attrib['path'] == 'cmdline-tools;19.0')
    archives = package.find('archives')
    archive = next(a for a in archives.findall('archive') if a.findtext('host-os') == 'windows')
    complete = archive.find('complete')
    url = 'https://dl.google.com/android/repository/' + complete.findtext('url')
    checksum_node = complete.find('checksum')
    algorithm = checksum_node.attrib.get('type', 'sha1')
    print('Android command tools', url, flush=True)
    sdk = TOOLS / 'android-sdk'
    latest = sdk / 'cmdline-tools' / '19.0'
    if not (latest / 'bin' / 'sdkmanager.bat').exists():
        archive_file = download(url, TOOLS / 'android-command-tools-19.zip', checksum_node.text, algorithm)
        staging = TOOLS / 'android-extract-19'
        extract(archive_file, staging)
        latest.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(staging / 'cmdline-tools'), str(latest))
    stable_platforms = sorted([p.attrib['path'] for p in root.findall('remotePackage')
                               if p.attrib.get('path', '').startswith('platforms;android-')
                               and p.attrib['path'].split('-')[-1].isdigit()
                               and p.findtext('channelRef', default='') == ''],
                              key=lambda v: int(v.split('-')[-1]))
    print('Available platforms', stable_platforms[-6:], flush=True)
    print('Android command tools ready', flush=True)


if __name__ == '__main__':
    {'flutter': flutter, 'android': android}[sys.argv[1]]()
