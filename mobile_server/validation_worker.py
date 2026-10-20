"""Untrusted deep parsing runs here, never in the API interpreter."""
import json
import os
from pathlib import Path
import sys


def execute(directory):
    directory = Path(directory).resolve()
    request = json.loads((directory / 'request.json').read_text(encoding='utf-8'))
    if os.name != 'nt':
        # Set the limit inside the new interpreter, avoiding unsafe preexec_fn
        # callbacks in the multithreaded API server. Windows uses its Job Object.
        import resource
        ceiling = request['memory_limit_bytes']
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[variable] = '1'
    scratch = directory / 'scratch'
    scratch.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = os.environ['TMPDIR'] = str(scratch)
    import tempfile
    tempfile.tempdir = str(scratch)
    try:
        from .validation import validate_content
        validate_content((directory / 'input.bin').read_bytes(), request['source'], request['options'],
                         request['max_uncompressed_bytes'])
        outcome = {'valid': True, 'error': None}
    except Exception as error:
        outcome = {'valid': False, 'error': (str(error).replace(str(directory), '[validation]')[:1500]
                                            or '文件无效或校验内存不足。')}
    (directory / 'validation.json').write_text(json.dumps(outcome, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    execute(sys.argv[1])
