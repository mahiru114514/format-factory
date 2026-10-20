"""Run the actual Flutter HTTP client against a private temporary API instance."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import requests

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='factory-api-live-') as temp:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    environment = dict(os.environ, FACTORY_STORAGE=temp)
    url = f'http://127.0.0.1:{port}'
    log = ROOT / '.work/mobile-live-service.log'
    with log.open('wb') as output:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'mobile_server.app:app', '--host', '127.0.0.1', '--port', str(port), '--workers', '1', '--no-access-log'], cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            session = requests.Session()
            session.trust_env = False
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Local integration service failed; see .work/mobile-live-service.log')
                try:
                    session.get(url + '/v1/capabilities', timeout=1).raise_for_status()
                    break
                except requests.RequestException:
                    time.sleep(.1)
            else:
                raise TimeoutError('Integration service did not become ready')
            environment['FACTORY_TEST_SERVER'] = url
            build_root = Path('F:/') if Path('F:/.tools/mobile-workspace-id').exists() else ROOT
            flutter = build_root / '.tools/flutter/bin/flutter.bat'
            command = ['cmd', '/c', str(flutter), 'test', '--no-pub', 'test/integration/remote_live_test.dart']
            result = subprocess.run(command, cwd=build_root / 'mobile', env=environment, timeout=180)
            if result.returncode:
                raise SystemExit(result.returncode)
            if list(Path(temp).iterdir()):
                raise AssertionError('Client did not acknowledge remote job deletion')
            print('Live Flutter/API conversion and remote deletion verified.', flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
