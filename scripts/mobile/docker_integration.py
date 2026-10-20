"""Verify the built Linux image on a private, disposable loopback-only port."""
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[2]
name = 'format-factory-verify-' + uuid.uuid4().hex[:8]
image = 'format-factory-service:mobile-test'
recognition_only = '--recognition-only' in sys.argv
def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, encoding='utf-8').strip()

identifier = docker('run', '--rm', '-d', '--name', name, '--memory', '2g', '--cpus', '2',
                    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                    '-p', '127.0.0.1::8765', image,
                    'python', '-m', 'uvicorn', 'mobile_server.app:app', '--host', '0.0.0.0',
                    '--port', '8765', '--workers', '1', '--no-access-log')
try:
    port = json.loads(docker('inspect', identifier))[0]['NetworkSettings']['Ports']['8765/tcp'][0]['HostPort']
    url = f'http://127.0.0.1:{port}'
    client = requests.Session()
    client.trust_env = False
    for _ in range(100):
        try:
            response = client.get(url + '/v1/capabilities', timeout=1)
            response.raise_for_status()
            capabilities = response.json()
            break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise TimeoutError('Linux API did not become ready')
    assert capabilities['engines']['libreoffice']['ready']
    environment = dict(os.environ, FACTORY_TEST_SERVER=url, FACTORY_TEST_PDF='true')
    build_root = Path('F:/') if Path('F:/.tools/mobile-workspace-id').exists() else ROOT
    if not recognition_only:
        result = subprocess.run(['cmd', '/c', str(build_root / '.tools/flutter/bin/flutter.bat'), 'test', '--no-pub', 'test/integration/remote_live_test.dart'], cwd=build_root / 'mobile', env=environment, timeout=240)
        if result.returncode:
            raise SystemExit(result.returncode)
    def job(data, filename, target, category='images', options=None):
        response = client.post(url + '/v1/jobs', files={'file': (filename, data)}, data={'category': category, 'target': target, 'consent': 'true', 'options': json.dumps(options or {})}, timeout=30)
        response.raise_for_status()
        task = response.json()
        endpoint = url + '/v1/jobs/' + task['id']
        headers = {'Authorization': 'Bearer ' + task['token']}
        for _ in range(240):
            state = client.get(endpoint, headers=headers, timeout=5).json()
            if state['state'] == 'failed':
                raise RuntimeError(state['error'])
            if state['state'] == 'succeeded':
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Linux image conversion timed out')
        response = client.get(endpoint + '/result', headers=headers, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            content = archive.read(archive.namelist()[0])
        client.delete(endpoint, headers=headers, timeout=5).raise_for_status()
        return content
    checks = []
    if not recognition_only:
        png = io.BytesIO()
        Image.new('RGB', (64, 32), 'royalblue').save(png, format='PNG')
        heic = job(png.getvalue(), '照片.png', 'heic')
        assert heic[4:8] == b'ftyp'
        jpeg = job(heic, '照片.heic', 'jpg')
        with Image.open(io.BytesIO(jpeg)) as photo:
            assert photo.format == 'JPEG' and photo.size == (64, 32)
        checks += ['Flutter/API CSV-XLSX-CSV', 'Flutter/API Chinese DOCX-PDF-DOCX-TXT', 'Linux PNG-HEIC-JPEG']
    ocr = job((ROOT / '示例文件/文字识别示例.png').read_bytes(), '文字.png', 'txt', 'text', {'method': 'ocr'}).decode('utf-8')
    assert '你好世界' in ocr and 'Hello' in ocr and '123' in ocr, ocr
    formula = job((ROOT / '示例文件/公式识别示例.png').read_bytes(), '公式.png', 'txt', 'text', {'method': 'formula'}).decode('utf-8')
    readable_formula = re.sub(r'\\(?:mathbf|mathrm)\{([xy])\}', r'\1', formula)
    assert readable_formula.replace(' ', '').replace('\\,', '') == 'x+y=1', formula
    checks += ['Linux Chinese/English OCR to UTF-8 TXT', 'Linux formula image to LaTeX TXT', 'remote acknowledgement deletion']
    regression = ROOT / 'tests/fixtures/logic_formula_dark_frame.png'
    logic_formula = None
    if regression.is_file():
        logic_formula = job(regression.read_bytes(), 'logic.png', 'txt', 'text', {'method': 'formula'}).decode('utf-8')
        compact = ''.join(logic_formula.split())
        assert r'\bigvee_{i=0}^{5}' in compact and 'used[t]' in compact and 'slot[i]=t' in compact, logic_formula
        assert any(command in compact for command in (r'\longleftrightarrow', r'\Leftrightarrow', r'\iff')), logic_formula
        checks += ['Linux reported dark logic formula preserves relation, limits and index']
    assert not docker('exec', identifier, 'find', '/jobs', '-mindepth', '1', '-maxdepth', '1')
    report = {'image': image, 'image_id': docker('inspect', '--format', '{{.Image}}', identifier),
              'python': docker('exec', identifier, 'python', '--version'),
              'libreoffice': docker('exec', identifier, 'libreoffice', '--headless', '--version'),
              'results': checks, 'ocr': ocr, 'formula': formula, 'logic_formula': logic_formula,
              'capabilities': capabilities}
    filename = 'mobile-recognition-integration.json' if recognition_only else 'mobile-linux-integration.json'
    (ROOT / '.work' / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Linux integration passed: ' + ', '.join(checks), flush=True)
finally:
    subprocess.run(['docker', 'stop', '--timeout', '5', identifier], stdout=subprocess.DEVNULL, check=False)
