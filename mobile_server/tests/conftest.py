import os
import tempfile
from pathlib import Path

TEMP = Path(__file__).resolve().parents[2] / '.work' / 'tmp'
TEMP.mkdir(parents=True, exist_ok=True)
os.environ['TEMP'] = str(TEMP)
os.environ['TMP'] = str(TEMP)
tempfile.tempdir = str(TEMP)
