"""Allowlisted distribution: never ship customer data, credentials or logs."""
from pathlib import Path
import zipfile
import hashlib

ROOT = Path(__file__).resolve().parent.parent
FILES = ['BASLAT.cmd', 'DURDUR.cmd', 'run.ps1', 'stop.ps1', 'setup.ps1', 'server.py', 'v2_local.py', 'requirements.txt', 'requirements-lock.txt', 'KULLANIM.html', 'README.md', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', 'index.html', 'build.ps1', '.gitignore', '.gitattributes']
DIRS = ['runtime', 'static', 'src', 'tests']
TOOLS = ['mockup_workflow.py', 'MockupBatchExport.jsx', 'video_mockup_helpers.jsx', 'package_release.py', 'install_runtime.py']

def release_files():
    files = [ROOT / name for name in FILES] + [ROOT/'tools'/name for name in TOOLS]
    for name in DIRS:
        files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)
        yield path

def main():
    destination = ROOT.parent / 'etsy ekosistem v2 - dagitim.zip'
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in release_files():
            archive.write(source, Path('etsy ekosistem v2') / source.relative_to(ROOT))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256.txt').write_text(f'{digest}  {destination.name}\n', encoding='utf-8')
    print(f'{destination.name}: {destination.stat().st_size / 1024**2:.1f} MB')
    print(f'SHA256: {digest}')

if __name__ == '__main__':
    main()
