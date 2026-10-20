from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'mobile' / 'assets'
ASSETS.mkdir(parents=True, exist_ok=True)
files = {
    'NotoSansSC.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/NotoSansSC[wght].ttf',
    'NotoSansSC-OFL.txt': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/OFL.txt',
}
for name, url in files.items():
    destination = ASSETS / name
    if destination.exists():
        continue
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)
    print(name, len(response.content), flush=True)
