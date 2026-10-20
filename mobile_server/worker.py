"""One isolated process per conversion; only the parent chooses this directory."""
import json
import os
from pathlib import Path
import sys
import zipfile


def execute(directory):
    from .engines import convert
    directory = Path(directory).resolve()
    # Third party engines may use tempfile; keep every scratch file inside job.
    scratch = directory / 'scratch'
    scratch.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(scratch)
    os.environ['TMPDIR'] = str(scratch)
    import tempfile
    tempfile.tempdir = str(scratch)
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[variable] = '1'
    try:
        request = json.loads((directory / 'request.json').read_text(encoding='utf-8'))
        source = directory / ('input.' + request['source'])
        output = directory / 'output'
        result = convert(request['category'], source, request['target'], output, request['options'])
        # Original names are display names only. Never use upload names as paths.
        for main in result.paths:
            suffix = main.name[len(source.stem):] if main.name.startswith(source.stem) else '.' + request['target']
            desired = output / (request['stem'] + suffix)
            if main != desired:
                main.replace(desired)
        files = sorted(p for p in output.rglob('*') if p.is_file())
        if not files or sum(p.stat().st_size for p in files) > request['max_result_bytes']:
            raise ValueError('输出为空或超过大小限制。')
        with zipfile.ZipFile(directory / 'result.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                if path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
                    raise ValueError('输出路径不安全。')
                archive.write(path, path.relative_to(output).as_posix())
        outcome = {'state': 'succeeded', 'outputs': [p.relative_to(output).as_posix() for p in files],
                   'warnings': result.warnings, 'error': None}
    except Exception as error:
        # Keep errors useful without disclosing absolute server paths.
        message = str(error).replace(str(directory), '[job]')
        outcome = {'state': 'failed', 'error': message[:1500] or type(error).__name__, 'outputs': [], 'warnings': []}
    staged = directory / 'outcome.tmp'
    staged.write_text(json.dumps(outcome, ensure_ascii=False), encoding='utf-8')
    staged.replace(directory / 'outcome.json')


if __name__ == '__main__':
    execute(sys.argv[1])
