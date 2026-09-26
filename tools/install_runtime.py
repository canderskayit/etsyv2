"""Rebuild the portable Windows runtime from pinned PyPI packages."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
runtime = ROOT / 'runtime'
with urllib.request.urlopen('https://pypi.org/pypi/pip/26.2.1/json', timeout=60) as response:
    metadata = json.load(response)
wheel = next(row for row in metadata['urls'] if row['filename'].endswith('py3-none-any.whl'))
if not wheel['url'].startswith('https://files.pythonhosted.org/'):
    raise ValueError('Unexpected package host')
with urllib.request.urlopen(wheel['url'], timeout=90) as response:
    content = response.read()
if hashlib.sha256(content).hexdigest() != wheel['digests']['sha256']:
    raise ValueError('Package checksum mismatch')
bootstrap = runtime / 'pip-bootstrap.whl'
bootstrap.write_bytes(content)
command = 'import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("pip",run_name="__main__")'
subprocess.run([sys.executable,'-B','-c',command,str(bootstrap),'install','--upgrade','--only-binary=:all:','--no-compile','--disable-pip-version-check','--target',str(runtime/'Lib'/'site-packages'),'-r',str(ROOT/'requirements-lock.txt')],check=True)
subprocess.run([sys.executable,'-B','-c','from PIL import Image; import pypdf,numpy,cv2,imageio_ffmpeg; print("Runtime ready")'],check=True)
(runtime/'ready.json').write_text(json.dumps({'app':'etsy-ekosistem-v2','version':'2.0.0'}),encoding='utf-8')
