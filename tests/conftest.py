import os
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TEMP = PROJECT / '.work' / 'tmp'
TEMP.mkdir(parents=True, exist_ok=True)
os.environ['TEMP'] = str(TEMP)
os.environ['TMP'] = str(TEMP)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
tempfile.tempdir = str(TEMP)
