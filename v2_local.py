"""Local-only onboarding and template library. No Etsy network calls here."""
from pathlib import Path
import base64
import importlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid


def status(app):
    settings = app.get_settings()
    secrets = settings['_secrets']
    collections = app.selection_catalog_payload()['selections']
    return {
        'workspace_name': settings.get('workspace_name', 'Benim stüdyom'),
        'data_dir': str(app.DATA),
        'callback_url': app.oauth_redirect_uri(),
        'keys_saved': bool(secrets.get('etsy_keystring') and secrets.get('etsy_shared_secret')),
        'etsy_connected': bool(secrets.get('etsy_access_token')),
        'shop_id': str(secrets.get('etsy_shop_id') or ''),
        'photoshop_ready': Path(settings.get('photoshop_exe_path') or '').is_file(),
        'photoshop_path': settings.get('photoshop_exe_path', ''),
        'mode': settings['etsy_mode'],
        'collections': collections,
        'dependencies': {name: dependency_ready(module) for name, module in [('Görsel işleme', 'PIL.Image'), ('PDF', 'pypdf'), ('Görsel analizi', 'cv2'), ('Video kontrolü', 'imageio_ffmpeg')]},
    }


def dependency_ready(module):
    try:
        loaded = importlib.import_module(module)
        return bool(getattr(loaded, '__file__', None))
    except (ImportError, OSError):
        return False


def pick(kind):
    if os.name != 'nt':
        raise ValueError('Dosya seçici Windows bilgisayarlarda kullanılabilir.')
    options = {
        'mockups': ('Photoshop PSD|*.psd', True),
        'video': ('Video veya Photoshop şablonu|*.psd;*.mp4;*.mov', False),
        'photoshop': ('Photoshop uygulaması|Photoshop.exe', False),
        'folder': ('', False),
    }
    if kind not in options:
        raise ValueError('Bilinmeyen dosya seçimi.')
    file_filter, multiple = options[kind]
    script = '$ErrorActionPreference = "Stop"; [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); '
    script += 'try { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::EnableVisualStyles(); '
    if kind == 'folder':
        script += '$d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = "Koleksiyonların bulunduğu klasör"; '
        result = '@($d.SelectedPath)'
    else:
        script += f'$d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = "{file_filter}"; $d.Multiselect = ${str(multiple).lower()}; '
        result = '@($d.FileNames)'
    script += '$owner = New-Object System.Windows.Forms.Form; $owner.Text = "Etsy V2 - Dosya secimi"; '
    script += '$owner.TopMost = $true; $owner.ShowInTaskbar = $true; $owner.StartPosition = "CenterScreen"; '
    script += '$owner.Width = 1; $owner.Height = 1; $owner.Opacity = 0; '
    # TopMost must have a live owner window before opening the modal dialog.
    script += '$owner.Show(); $owner.Activate(); '
    script += f'try {{ if ($d.ShowDialog($owner) -eq "OK") {{ ConvertTo-Json -InputObject {result} -Compress }} else {{ "[]" }} }} finally {{ $d.Dispose(); $owner.Dispose() }} '
    script += '} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }'
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    hint = 'Kütüphanedeki "Dosya yollarıyla ekle" alanını da kullanabilirsiniz.'
    try:
        completed = subprocess.run(
            ['powershell.exe', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
            capture_output=True, encoding='utf-8-sig', errors='replace', timeout=90, creationflags=0x08000000,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Dosya seçimi zaman aşımına uğradı. {hint}') from exc
    except OSError as exc:
        raise RuntimeError(f'Windows dosya seçici başlatılamadı. {hint}') from exc
    if completed.returncode:
        raise RuntimeError(f'Windows dosya seçici açılamadı. {hint}')
    try:
        paths = json.loads(completed.stdout.strip())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'Windows dosya seçimi sonucu okunamadı. {hint}') from exc
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise RuntimeError(f'Windows geçersiz dosya seçimi döndürdü. {hint}')
    return {'paths': paths}


def create_collection(app, payload):
    name = app.canonical_selection_name(str(payload.get('name') or '').strip())
    if not name or len(name) > 70 or any(c in name for c in '\\/:*?"<>|\0') or name.endswith(('.', ' ')) or name in {'.', '..'}:
        raise ValueError('Geçerli bir koleksiyon adı girin (en fazla 70 karakter).')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Bu klasör adı Windows tarafından ayrılmış.')
    paths = payload.get('mockups')
    if not isinstance(paths, list) or not 1 <= len(paths) <= 19:
        raise ValueError('1–19 mockup PSD dosyası seçin.')
    sources = [Path(str(value)).resolve() for value in paths]
    video = Path(str(payload['video'])).resolve() if payload.get('video') else None
    if len(set(sources)) != len(sources):
        raise ValueError('Aynı şablon birden fazla seçilemez.')
    for source in sources + ([video] if video else []):
        allowed = {'.psd', '.mp4', '.mov'} if source == video else {'.psd'}
        if not source.is_file() or source.suffix.lower() not in allowed or not source.stat().st_size:
            raise ValueError(f'Dosya bulunamadı veya biçimi desteklenmiyor: {source.name}')
        if source.suffix.lower() == '.psd':
            with source.open('rb') as handle:
                if handle.read(4) != b'8BPS':
                    raise ValueError(f'Geçerli bir Photoshop PSD dosyası değil: {source.name}')
    library = app.selection_mockup_root().resolve()
    library.mkdir(parents=True, exist_ok=True)
    destination = (library / name).resolve()
    if destination.parent != library:
        raise ValueError('Koleksiyon yolu geçersiz.')
    if destination.exists():
        raise ValueError('Bu isimde koleksiyon var. Yeni bir isim kullanın.')
    staging = Path(tempfile.mkdtemp(prefix='collection-', dir=app.DATA))
    try:
        (staging/'mockups').mkdir(); (staging/'video').mkdir()
        for index, source in enumerate(sources, 1):
            shutil.copy2(source, staging/'mockups'/f'{index:02d}-{source.name}')
        if video:
            shutil.copy2(video, staging/'video'/video.name)
        # Destination can be another disk: copy first, expose only after completion.
        pending = library / ('.import-' + uuid.uuid4().hex)
        try:
            shutil.copytree(staging, pending)
            pending.rename(destination)
        finally:
            if pending.exists():
                shutil.rmtree(pending)
    finally:
        shutil.rmtree(staging)
    return {'ok': True, 'name': name, 'mockup_count': len(sources), 'video_count': int(video is not None)}


def action(app, route, payload):
    if route == '/api/v2/variants/apply-defaults':
        product_id = str(payload.get('product_id') or '')
        with app.db() as conn:
            product = conn.execute('SELECT status FROM products WHERE id=?', (product_id,)).fetchone()
            if not product:
                raise ValueError('Ürün bulunamadı.')
            if product['status'] in {'queued', 'running'}:
                raise ValueError('Varyasyon eklemeden önce üretimi durdurun.')
            kinds = {row['kind'] for row in conn.execute('SELECT DISTINCT kind FROM variants WHERE product_id=?', (product_id,))}
        settings = app.get_settings()
        available = []
        for kind in ('unframed', 'framed'):
            key = f'default_{kind}_csv_path'
            if kind in kinds:
                settings[key] = ''
            elif settings.get(key):
                path = Path(settings[key])
                if not path.is_file():
                    raise ValueError(f'{kind} CSV bulunamadı. Gelişmiş ayarlardan yeniden yükleyin.')
                app.validate_variant_csv_bytes(path.read_bytes())
                available.append(kind)
        if not available:
            raise ValueError('Eksik türler için kayıtlı CSV yok. Gelişmiş ayarlarda framed/unframed dosyalarını seçip kaydedin.')
        results = app.apply_default_variant_csvs(product_id, settings)
        if any(not results.get(kind, {}).get('created') for kind in available):
            raise ValueError('Bazı varyasyonlar eklenemedi. Ürünün Son işlemler bölümündeki hatayı kontrol edin.')
        return {'created': sum(row['created'] for row in results.values()), **app.product_payload(product_id)}
    if route == '/api/v2/pick':
        return pick(payload.get('kind'))
    if route == '/api/v2/collections':
        return create_collection(app, payload)
    if route == '/api/v2/disconnect':
        if payload.get('confirmation') != 'disconnect':
            raise ValueError('Bağlantıyı kaldırma onayı gerekli.')
        saved = app.read_json_file(app.SECRETS_PATH, {})
        app.write_json_file(app.SECRETS_PATH, {k:v for k,v in saved.items() if not k.startswith('etsy_')})
        app.write_json_file(app.ETSY_OAUTH_PATH, {})
        app.save_setting_updates({'etsy_mode': 'dry_run'})
        return {'ok': True}
    raise ValueError('İşlem bulunamadı.')
