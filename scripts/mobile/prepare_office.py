import hashlib
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolchain import download

root = Path(__file__).resolve().parents[2]
version = '26.8.1'
name = f'LibreOffice_{version}_Win_x86-64.msi'
base = f'https://download.documentfoundation.org/libreoffice/stable/{version}/win/x86_64/'
metadata = requests.get(base + name + '.sha256', timeout=60)
metadata.raise_for_status()
checksum = metadata.text.split()[0]
destination = download(base + name, root / '.tools' / name, checksum)
print('LibreOffice installer verified:', destination, flush=True)
