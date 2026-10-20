"""Download only public formula model assets; never uploads user files."""
import hashlib
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'resources' / 'formula'
ASSETS = ['image_resizer.onnx', 'encoder.onnx', 'decoder.onnx', 'tokenizer.json']
BASE = 'https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0'


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    manifest_file = MODEL_DIR / 'sha256.json'
    previous = json.loads(manifest_file.read_text(encoding='utf-8')) if manifest_file.exists() else {}
    manifest = {}
    for name in ASSETS:
        destination = MODEL_DIR / name
        if not destination.exists():
            print('Downloading', name, flush=True)
            part = destination.with_suffix(destination.suffix + '.part')
            try:
                with requests.get(f'{BASE}/{name}', stream=True, timeout=(30, 180)) as response:
                    response.raise_for_status()
                    with part.open('wb') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                if part.stat().st_size < (1000 if name.endswith('.json') else 100_000):
                    raise ValueError(f'Model download is unexpectedly small: {name}')
                part.replace(destination)
            finally:
                part.unlink(missing_ok=True)
        digest = hashlib.file_digest(destination.open('rb'), 'sha256').hexdigest()
        if name in previous and previous[name] != digest:
            raise ValueError(f'模型校验失败：{name}，请删除该模型后重新准备。')
        manifest[name] = digest
        print(name, destination.stat().st_size, digest, flush=True)
    manifest_file.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
