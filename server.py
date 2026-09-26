from __future__ import annotations

import base64
import csv
import hashlib
import html
import hmac
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = Path(os.environ.get("ETSY_V2_DATA_DIR") or (Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "EtsyEkosistemV2"))
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "app.sqlite3"
SETTINGS_PATH = DATA / "settings.json"
SECRETS_PATH = DATA / "secrets.json"
ETSY_OAUTH_PATH = DATA / "etsy_oauth.json"
GOOGLE_OAUTH_PATH = DATA / "google_oauth.json"
CANVA_OAUTH_PATH = DATA / "canva_oauth.json"

APP_HOST = "127.0.0.1"
APP_PUBLIC_HOST = os.environ.get("ETSY_V2_PUBLIC_HOST", "localhost")
APP_PORT = int(os.environ.get("ETSY_V2_PORT", "8766"))

jobs: dict[str, threading.Thread] = {}
job_queue: list[str] = []
queue_thread: threading.Thread | None = None
jobs_lock = threading.Lock()
media_replacement_threads: dict[str, threading.Thread] = {}
media_replacement_lock = threading.Lock()
photoshop_automation_lock = threading.Lock()
bulk_mockup_thread: threading.Thread | None = None
bulk_mockup_lock = threading.Lock()
bulk_analysis_semaphore = threading.Semaphore(2)
media_write_sessions: set[tuple[str, str]] = set()
media_write_lock = threading.Lock()
ETSY_SIZE_PROPERTY_ID = 513
ETSY_FORMAT_PROPERTY_ID = 514
ETSY_MAX_IMAGE_COUNT = 20
EXPECTED_EXTERNAL_MOCKUP_COUNT = 14
MEDIA_REPLACEMENT_CONFIRMATION_PREFIX = "REPLACE"
MEDIA_REPLACEMENT_MANIFEST_VERSION = 6
ETSY_PRIMARY_THUMBNAIL_STEM = "y-00837"
ETSY_PRIMARY_THUMBNAIL_ASPECT_RATIO = 4 / 3
ETSY_PRIMARY_THUMBNAIL_ASPECT_TOLERANCE = 0.01
MOCKUP_STEM_ORDER = (
    ETSY_PRIMARY_THUMBNAIL_STEM,
    "y-00639",
    "y-0156",
    "y-0355",
    "y-0379",
    "y-0256",
    "y-0363",
    "y-00611",
    "y-0151",
    "y-00601",
    "y-00824",
    "y-00660psd",
    "y-00661",
    "y-00658",
)
DIGITAL_GUIDE_PATH = DATA / "guide.png"
DIGITAL_PACKAGE_FILENAMES = ("cmyk.pdf", "rgb.pdf", "png.png", "jpg.jpg", "guide.png")
CANVA_PRINT_CMYK_PROFILE_PATH = DATA / "color_profiles" / "Canva_GRACoL2013_CRPC6.icc"
CANVA_PRINT_CMYK_PROFILE_INFO = "GRACoL 2013 CRPC6 (ISO DIS 15339-2)"
CANVA_REQUIRED_SCOPES = frozenset({"asset:read", "asset:write", "design:content:read", "design:content:write"})
SELECTION_NAMES = ["İlk koleksiyonum"]
DEFAULT_FRAME_OPTIONS = [
    "White Wooden Framed",
    "Wood Wooden Framed",
    "Dark Wood Wooden Framed",
    "Black Wooden Framed",
    "Metal Framed",
]
STATIC_LISTING_IMAGES = []

STATIC_LISTING_ROLES_BY_LABEL = {
    "Frame color detail": "frame_colors",
    "Frame back and hanger detail": "frame_back",
    "Semi glossy paper detail": "paper_detail",
    "Poster size guide": "size_guide",
}
STATIC_LISTING_ROLES = ()


STEP_DEFS = [
    ("validate", "Kaynak dosya kontrolü", 5),
    ("photoshop_prepare", "Photoshop kalite/oran hazırlığı", 18),
    ("mockup_render", "Mockup görselleri üretiliyor", 58),
    ("video_mockup", "Video mockup hazırlanıyor", 72),
    ("etsy_draft", "Etsy draft'a aktarılıyor", 96),
    ("cost_finalize", "Maliyet raporu", 100),
]
ACTIVE_STEP_KEYS = {key for key, _, _ in STEP_DEFS}

DEFAULT_SETTINGS = {
    "etsy_mode": "dry_run",
    "workspace_name": "Benim stüdyom",
    "smart_object_layer": "Kare 1",
    "etsy_listing_fee_usd": 0.20,
    "default_price_usd": 10.0,
    "default_quantity": 999,
    "default_taxonomy_id": 2078,
    "default_who_made": "i_did",
    "default_when_made": "made_to_order",
    "default_listing_type": "physical",
    "required_production_partner_name": "Gelato",
    "etsy_should_auto_renew": True,
    "etsy_ads_requested": True,
    "free_shipping_required": True,
    "required_shipping_profile_name": "Gelato: Free shipping",
    "include_shipping_in_profit": True,
    "pricing_formula": "margin",
    "fixed_unframed_prices": {
        "13x18": 56.45,
        "15x20": 58.50,
        "20x25": 60.00,
        "21x29.7": 62.00,
        "27x35": 64.05,
        "28x43": 65.45,
        "a3": 65.45,
        "30x40": 65.45,
        "30x45": 66.85,
        "40x60": 73.80,
        "a2": 74.50,
        "45x60": 75.90,
        "50x70": 81.45,
        "a1": 105.85,
        "60x80": 107.25,
        "60x90": 110.75,
        "70x100": 123.25,
        "75x100": 124.60,
        "a0": 128.80,
    },
    "fixed_framed_prices": {
        "13x18": 127.23,
        "15x20": 127.80,
        "20x25": 132.67,
        "21x29.7": 139.93,
        "27x35": 167.23,
        "28x43": 189.63,
        "a3": 192.20,
        "30x30": 157.70,
        "30x40": 176.73,
        "30x45": 194.70,
        "40x40": 216.07,
        "40x50": 237.37,
        "a2": 253.47,
        "45x60": 257.90,
        "50x50": 262.13,
        "50x70": 376.80,
        "a1": 462.40,
        "60x80": 446.40,
        "60x90": 473.87,
        "70x70": 450.97,
        "70x100": 547.13,
    },
    "gelato_retail_multiplier": 1.0,
    "default_unframed_percent": 40,
    "default_framed_percent": 40,
    "default_unframed_csv_path": "",
    "default_unframed_csv_name": "",
    "default_framed_csv_path": "",
    "default_framed_csv_name": "",
    "auto_resume_queue_on_start": False,
    "etsy_media_write_policy": "new_drafts_only",
    "google_drive_sync_enabled": False,
    "google_drive_parent_folder_id": "",
    "canva_delivery_enabled": False,
    "canva_export_quality": "pro",
    "selection_mockup_root": str(DATA / "templates" / "Selections"),
    "mockup_batch_export_jsx": "tools/MockupBatchExport.jsx",
    "mockup_mode": "external_script",
    "external_mockup_project_dir": "tools",
    "photoshop_exe_path": "",
    "mockup_wait_timeout_sec": 900,
    "photoshop_prepare_timeout_sec": 240,
    "retry_max_attempts": 3,
    "retry_base_delay_sec": 1.5,
    "qps_limit": 5,
    "prohibited_terms": [
        "nba",
        "nike",
        "adidas",
        "fifa",
        "uefa",
        "nfl",
        "mlb",
        "nhl",
        "olympic",
    ],
    "default_description_tail": (
        "Premium Print Details\n"
        "- Printed on premium semi-glossy paper\n"
        "- 170 gsm museum-quality material\n"
        "- Sharp detail with rich contrast and clarity\n"
        "- Smooth professional print finish\n"
        "- FSC-certified eco-friendly paper materials\n\n"
        "Available Sizes\n"
        "5x7, 6x8, 8x10, 8x12, 11x14, 11x17, A3, 12x16, 12x18, "
        "16x24, A2, 18x24, 20x28, A1, 24x32, 24x36, 28x40, 30x40, A0\n\n"
        "Shipping & Packaging\n"
        "- Securely packaged in a durable protective shipping tube\n"
        "- Fast production and dispatch within 24 hours\n"
        "- Estimated delivery time: 2-5 business days\n\n"
        "Important Information\n"
        "- This listing is for an UNFRAMED physical poster print\n"
        "- Colors may vary slightly depending on monitor settings\n"
        "- Slight cropping may occur depending on selected size ratio\n"
        "- Frames and accessories shown in mockups are not included"
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_settings() -> dict:
    stored_settings = read_json_file(SETTINGS_PATH, {})
    settings = DEFAULT_SETTINGS | stored_settings
    secrets = read_json_file(SECRETS_PATH, {})
    env_map = {
        "etsy_keystring": "ETSY_KEYSTRING",
        "etsy_shared_secret": "ETSY_SHARED_SECRET",
        "etsy_access_token": "ETSY_ACCESS_TOKEN",
        "etsy_shop_id": "ETSY_SHOP_ID",
        "etsy_shipping_profile_id": "ETSY_SHIPPING_PROFILE_ID",
        "etsy_readiness_state_id": "ETSY_READINESS_STATE_ID",
        "etsy_production_partner_id": "ETSY_PRODUCTION_PARTNER_ID",
        "etsy_refresh_token": "ETSY_REFRESH_TOKEN",
        "google_client_id": "GOOGLE_CLIENT_ID",
        "google_client_secret": "GOOGLE_CLIENT_SECRET",
        "google_access_token": "GOOGLE_ACCESS_TOKEN",
        "google_refresh_token": "GOOGLE_REFRESH_TOKEN",
        "canva_client_id": "CANVA_CLIENT_ID",
        "canva_client_secret": "CANVA_CLIENT_SECRET",
        "canva_access_token": "CANVA_ACCESS_TOKEN",
        "canva_refresh_token": "CANVA_REFRESH_TOKEN",
    }
    for key, env_name in env_map.items():
        if os.environ.get("ETSY_V2_" + key.upper()):
            secrets[key] = os.environ["ETSY_V2_" + key.upper()]
    # Retired panel integrations must not resume from saved settings.
    settings["google_drive_sync_enabled"] = False
    settings["canva_delivery_enabled"] = False
    photoshop = Path(str(settings.get("photoshop_exe_path") or ""))
    if not photoshop.is_file():
        adobe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Adobe"
        candidates = sorted(adobe.glob("Adobe Photoshop */Photoshop.exe"), reverse=True)
        settings["photoshop_exe_path"] = str(candidates[0]) if candidates else ""
    for key in ("selection_mockup_root", "default_unframed_csv_path", "default_framed_csv_path", "mockup_batch_export_jsx", "external_mockup_project_dir"):
        value = str(settings.get(key) or "")
        if value and not Path(value).is_absolute():
            settings[key] = str(ROOT / value)
    settings["_secrets"] = secrets
    return settings


def public_settings() -> dict:
    settings = get_settings()
    secrets = settings.pop("_secrets", {})
    visible_secret_keys = {
        "etsy_keystring",
        "etsy_shared_secret",
        "etsy_access_token",
        "etsy_refresh_token",
        "etsy_shop_id",
        "etsy_shipping_profile_id",
        "etsy_readiness_state_id",
        "etsy_production_partner_id",
        "google_client_id",
        "google_client_secret",
        "google_access_token",
        "google_refresh_token",
        "canva_client_id",
        "canva_client_secret",
        "canva_access_token",
        "canva_refresh_token",
    }
    settings["secret_status"] = {key: bool(secrets.get(key)) for key in visible_secret_keys}
    return settings


def save_settings(payload: dict) -> dict:
    current = get_settings()
    current.pop("_secrets", None)
    secrets = read_json_file(SECRETS_PATH, {})

    secrets_before = dict(secrets)
    secret_keys = {
        "etsy_keystring",
        "etsy_shared_secret",
        "etsy_access_token",
        "etsy_refresh_token",
        "etsy_shop_id",
        "etsy_shipping_profile_id",
        "etsy_readiness_state_id",
        "etsy_production_partner_id",
        "google_client_id",
        "google_client_secret",
        "google_access_token",
        "google_refresh_token",
        "canva_client_id",
        "canva_client_secret",
        "canva_access_token",
        "canva_refresh_token",
    }
    normal_updates = {}
    normal_updates.update(save_default_csv_setting(payload, "default_unframed_csv", "default-unframed"))
    normal_updates.update(save_default_csv_setting(payload, "default_framed_csv", "default-framed"))
    for key, value in payload.items():
        if key in secret_keys:
            if isinstance(value, str) and value.strip():
                secrets[key] = value.strip()
        elif key in DEFAULT_SETTINGS:
            normal_updates[key] = value

    if any(payload.get(key) and payload[key].strip() != secrets_before.get(key) for key in ("etsy_keystring", "etsy_shared_secret")):
        secrets = {key: value for key, value in secrets.items() if key in {"etsy_keystring", "etsy_shared_secret"} or not key.startswith("etsy_")}
        write_json_file(ETSY_OAUTH_PATH, {})
        normal_updates['etsy_mode'] = 'dry_run'
    merged = current | normal_updates
    write_json_file(SETTINGS_PATH, merged)
    write_json_file(SECRETS_PATH, secrets)
    return public_settings()


@contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_image_path TEXT,
                status TEXT NOT NULL,
                overall_progress INTEGER NOT NULL DEFAULT 0,
                current_step TEXT,
                listing_id TEXT,
                etsy_listing_state TEXT NOT NULL DEFAULT '',
                selection_name TEXT NOT NULL DEFAULT '',
                etsy_shop_section_id TEXT NOT NULL DEFAULT '',
                etsy_update_mode TEXT NOT NULL DEFAULT 'full',
                stop_requested INTEGER NOT NULL DEFAULT 0,
                etsy_fee_estimate_usd REAL NOT NULL DEFAULT 0,
                api_calls INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                step_key TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(product_id, step_key),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                step_key TEXT,
                message TEXT NOT NULL,
                progress INTEGER,
                meta_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                service TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS variants (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                size_label TEXT NOT NULL,
                frame_label TEXT NOT NULL DEFAULT '',
                orientation_label TEXT NOT NULL DEFAULT '',
                sku TEXT NOT NULL,
                source_row INTEGER,
                cost_usd REAL NOT NULL DEFAULT 0,
                product_cost_usd REAL NOT NULL DEFAULT 0,
                shipping_cost_usd REAL NOT NULL DEFAULT 0,
                markup_percent REAL NOT NULL DEFAULT 0,
                sale_price_usd REAL NOT NULL DEFAULT 0,
                profit_usd REAL NOT NULL DEFAULT 0,
                profit_margin_percent REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 999,
                visible INTEGER NOT NULL DEFAULT 1,
                locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                path TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                visible INTEGER NOT NULL DEFAULT 1,
                artwork_option_id TEXT,
                etsy_image_id TEXT,
                etsy_listing_id TEXT,
                protected INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL DEFAULT '',
                content_sha256 TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_variants_product_id
            ON variants(product_id);

            CREATE INDEX IF NOT EXISTS idx_assets_product_kind_sort
            ON assets(product_id, kind, sort_order, created_at);

            CREATE INDEX IF NOT EXISTS idx_events_product_id_desc
            ON events(product_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_products_mode_created
            ON products(etsy_update_mode, created_at DESC);

            CREATE TABLE IF NOT EXISTS artwork_options (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                label TEXT NOT NULL,
                source_path TEXT NOT NULL,
                prepared_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 1,
                visible INTEGER NOT NULL DEFAULT 1,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS seo_outputs (
                product_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description_intro TEXT NOT NULL,
                description_tail TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS media_replacement_jobs (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                source_path TEXT NOT NULL,
                preview_json TEXT NOT NULL DEFAULT '{}',
                backup_json TEXT NOT NULL DEFAULT '{}',
                approval_token TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                applied_at TEXT,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_media_replacement_product
            ON media_replacement_jobs(product_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS existing_mockup_queue (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                source_etsy_url TEXT NOT NULL DEFAULT '',
                source_rank INTEGER NOT NULL DEFAULT 0,
                extracted_path TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                media_job_id TEXT NOT NULL DEFAULT '',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
                UNIQUE(batch_id, product_id)
            );

            CREATE INDEX IF NOT EXISTS idx_existing_mockup_queue_status
            ON existing_mockup_queue(status, created_at);

            CREATE INDEX IF NOT EXISTS idx_existing_mockup_queue_batch
            ON existing_mockup_queue(batch_id, created_at);
            """
        )
        conn.execute("DROP TABLE IF EXISTS token_usage")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(variants)").fetchall()}
        if "orientation_label" not in columns:
            conn.execute("ALTER TABLE variants ADD COLUMN orientation_label TEXT NOT NULL DEFAULT ''")
        product_columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
        if "etsy_update_mode" not in product_columns:
            conn.execute("ALTER TABLE products ADD COLUMN etsy_update_mode TEXT NOT NULL DEFAULT 'full'")
        if "selection_name" not in product_columns:
            conn.execute("ALTER TABLE products ADD COLUMN selection_name TEXT NOT NULL DEFAULT ''")
        if "etsy_shop_section_id" not in product_columns:
            conn.execute("ALTER TABLE products ADD COLUMN etsy_shop_section_id TEXT NOT NULL DEFAULT ''")
        if "etsy_listing_state" not in product_columns:
            conn.execute("ALTER TABLE products ADD COLUMN etsy_listing_state TEXT NOT NULL DEFAULT ''")
        asset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
        if "visible" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN visible INTEGER NOT NULL DEFAULT 1")
        if "artwork_option_id" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN artwork_option_id TEXT")
        if "etsy_image_id" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN etsy_image_id TEXT")
        if "etsy_listing_id" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN etsy_listing_id TEXT")
        if "protected" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN protected INTEGER NOT NULL DEFAULT 0")
        if "role" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN role TEXT NOT NULL DEFAULT ''")
        if "content_sha256" not in asset_columns:
            conn.execute("ALTER TABLE assets ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            UPDATE variants
            SET orientation_label = CASE
                WHEN lower(size_label) LIKE '%vertical%' THEN 'Vertical'
                WHEN lower(size_label) LIKE '%portrait%' THEN 'Vertical'
                WHEN lower(size_label) LIKE '%horizontal%' THEN 'Horizontal'
                WHEN lower(size_label) LIKE '%landscape%' THEN 'Horizontal'
                ELSE orientation_label
            END
            WHERE COALESCE(orientation_label, '') = ''
            """
        )
        placeholders = ",".join("?" for _ in ACTIVE_STEP_KEYS)
        conn.execute(
            f"DELETE FROM steps WHERE step_key NOT IN ({placeholders})",
            tuple(ACTIVE_STEP_KEYS),
        )
        for key, label, _ in STEP_DEFS:
            conn.execute(
                """
                INSERT OR IGNORE INTO steps(product_id, step_key, label, status, progress, updated_at)
                SELECT id, ?, ?, 'pending', 0, ? FROM products
                """,
                (key, label, now_iso()),
            )
            conn.execute("UPDATE steps SET label=? WHERE step_key=?", (label, key))
        migrate_upload_folders_to_sku(conn)


def row_to_dict(row) -> dict:
    return dict(row) if row is not None else {}


FILENAME_TRANSLATION = str.maketrans({
    "ç": "c",
    "Ç": "C",
    "ğ": "g",
    "Ğ": "G",
    "ı": "i",
    "I": "I",
    "İ": "I",
    "ö": "o",
    "Ö": "O",
    "ş": "s",
    "Ş": "S",
    "ü": "u",
    "Ü": "U",
})


def slugify_filename(name: str, fallback: str = "file") -> str:
    name = Path((name or fallback).translate(FILENAME_TRANSLATION)).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip("-") or fallback
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(name).suffix)[:12]
    return f"{stem[:80]}{suffix}"


def digital_download_sku(product_id: str) -> str:
    return variant_sku(product_id, "digital", "DigitalDownload", "", 0)


def product_folder_name(product_id: str) -> str:
    return slugify_filename(digital_download_sku(product_id), product_id)


def product_upload_dir(product_id: str) -> Path:
    return UPLOADS / product_folder_name(product_id)


def migrate_upload_folders_to_sku(conn: sqlite3.Connection) -> None:
    for product in conn.execute("SELECT id FROM products").fetchall():
        product_id = product["id"]
        old_dir = (UPLOADS / product_id).resolve()
        new_dir = product_upload_dir(product_id).resolve()
        if old_dir == new_dir or not old_dir.exists() or new_dir.exists():
            continue
        old_dir.rename(new_dir)
        old_prefix = str(old_dir)
        new_prefix = str(new_dir)

        def moved_path(value: str | None) -> str | None:
            if not value:
                return value
            try:
                path = Path(value).resolve()
            except Exception:
                return value
            path_text = str(path)
            if path_text == old_prefix or path_text.startswith(old_prefix + os.sep):
                return new_prefix + path_text[len(old_prefix):]
            return value

        row = conn.execute("SELECT source_image_path FROM products WHERE id=?", (product_id,)).fetchone()
        updated_source = moved_path(row["source_image_path"] if row else "")
        if updated_source and row and updated_source != row["source_image_path"]:
            conn.execute("UPDATE products SET source_image_path=?, updated_at=? WHERE id=?", (updated_source, now_iso(), product_id))
        for asset in conn.execute("SELECT id, path FROM assets WHERE product_id=?", (product_id,)).fetchall():
            updated = moved_path(asset["path"])
            if updated and updated != asset["path"]:
                conn.execute("UPDATE assets SET path=?, updated_at=? WHERE id=?", (updated, now_iso(), asset["id"]))
        for option in conn.execute("SELECT id, source_path, prepared_path FROM artwork_options WHERE product_id=?", (product_id,)).fetchall():
            source_path = moved_path(option["source_path"])
            prepared_path = moved_path(option["prepared_path"])
            if source_path != option["source_path"] or prepared_path != option["prepared_path"]:
                conn.execute(
                    "UPDATE artwork_options SET source_path=?, prepared_path=?, updated_at=? WHERE id=?",
                    (source_path, prepared_path, now_iso(), option["id"]),
                )


def decode_data_url(data_url: str) -> tuple[str, bytes]:
    if "," in data_url and data_url.startswith("data:"):
        header, data = data_url.split(",", 1)
        mime = header.split(";", 1)[0].replace("data:", "") or "application/octet-stream"
        return mime, base64.b64decode(data)
    return "application/octet-stream", base64.b64decode(data_url)


def save_uploaded_data(product_id: str, filename: str, data_url: str, folder: str) -> Path:
    mime, raw = decode_data_url(data_url)
    safe_name = slugify_filename(filename)
    digest = hashlib.sha1(raw).hexdigest()[:10]
    target_dir = product_upload_dir(product_id) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{Path(safe_name).stem}-{digest}{Path(safe_name).suffix}"
    path.write_bytes(raw)
    return path


def upload_url_for_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    if str(path_value).startswith(("http://", "https://")):
        return str(path_value)
    try:
        path = Path(path_value)
        rel = path.resolve().relative_to(UPLOADS.resolve())
        return "/uploads/" + "/".join(urllib.parse.quote(part) for part in rel.parts)
    except Exception:
        return None


def parse_money(value) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = re.sub(r"[^0-9,.-]", "", text)
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


def csv_dialect_for_text(text: str) -> csv.Dialect:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    except csv.Error:
        return csv.excel


def read_csv_dict_rows(text: str) -> tuple[list[dict], bool]:
    def parse(candidate: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(candidate), dialect=csv_dialect_for_text(candidate)))

    rows = parse(text)
    if not rows:
        return rows, False

    headers = list(rows[0].keys())
    if len(headers) != 1 or "," not in str(headers[0]):
        return rows, False

    fixed_lines = []
    changed = 0
    for raw_row in csv.reader(io.StringIO(text)):
        if len(raw_row) == 1 and "," in raw_row[0]:
            fixed_lines.append(raw_row[0])
            changed += 1
        else:
            out = io.StringIO()
            csv.writer(out, lineterminator="").writerow(raw_row)
            fixed_lines.append(out.getvalue())

    if not changed:
        return rows, False

    fixed_rows = parse("\n".join(fixed_lines))
    if fixed_rows and len(list(fixed_rows[0].keys())) > 1:
        return fixed_rows, True
    return rows, False


def first_present(row: dict, names: list[str]) -> str:
    lookup = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_orientation(value: str) -> str:
    text = clean_text(value).lower()
    if not text:
        return ""
    if any(token in text for token in ["vertical", "portrait", "dikey"]):
        return "Vertical"
    if any(token in text for token in ["horizontal", "landscape", "yatay"]):
        return "Horizontal"
    if "square" in text or "kare" in text:
        return "Square"
    return clean_text(value)[:40]


def extract_orientation(row: dict, *values: str) -> str:
    explicit = first_present(row, ["Orientation", "Direction", "Layout", "Format", "Aspect", "Aspect ratio"])
    orientation = normalize_orientation(explicit)
    if orientation:
        return orientation
    for value in values:
        orientation = normalize_orientation(value)
        if orientation:
            return orientation
    return ""


def clean_size_label(size: str, orientation: str) -> str:
    label = clean_text(size)
    label = re.sub(r"(\d)\s*\?", r'\1"', label)
    if orientation:
        label = re.sub(rf"\s*[-–—|/]\s*{re.escape(orientation)}\s*$", "", label, flags=re.IGNORECASE)
        label = re.sub(rf"\s*\(?{re.escape(orientation)}\)?\s*$", "", label, flags=re.IGNORECASE)
    return clean_text(label)


def canonical_size_key(size: str) -> str:
    text = clean_text(size).lower().replace(",", ".").replace("×", "x")
    paper_size = re.match(r"^(a[0-3])\b", text)
    if paper_size:
        return paper_size.group(1)
    metric = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*cm\b", text)
    if not metric:
        return ""
    dimensions = sorted((float(metric.group(1)), float(metric.group(2))))

    def display_number(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")

    return f"{display_number(dimensions[0])}x{display_number(dimensions[1])}"


def fixed_variant_price(kind: str, size: str, settings: dict | None = None) -> float | None:
    if kind not in {"framed", "unframed"}:
        return None
    settings = settings or get_settings()
    if settings.get("pricing_formula") != "fixed_size_table":
        return None
    table = settings.get(f"fixed_{kind}_prices")
    if not isinstance(table, dict):
        return None
    value = table.get(canonical_size_key(size))
    if value is None:
        return None
    price = parse_money(value)
    return round(price, 2) if price > 0 else None


def resolved_variant_price(
    kind: str,
    size: str,
    cost_basis: float,
    percent: float,
    pricing_formula: str,
    retail_multiplier: float,
    settings: dict | None = None,
) -> float:
    locked_price = fixed_variant_price(kind, size, settings)
    if locked_price is not None:
        return locked_price
    return sale_from_cost(cost_basis, percent, pricing_formula, retail_multiplier)


def sale_from_cost(cost: float, percent: float, formula: str = "markup", retail_multiplier: float = 1.0) -> float:
    if formula == "margin":
        if not 0 <= percent < 100:
            raise ValueError("Kâr marjı 0 ile 100 arasında olmalı; 100 olamaz.")
        base_price = cost / (1 - percent / 100)
    else:
        base_price = cost * (1 + max(0, percent) / 100)
    return round(base_price * max(0.01, retail_multiplier), 2)


def profit_margin(cost: float, sale: float) -> float:
    if sale <= 0:
        return 0.0
    return round((sale - cost) / sale * 100, 2)


def variant_sku(product_id: str, kind: str, size: str, frame: str, row_idx: int) -> str:
    digest = hashlib.sha1(f"{product_id}|{kind}|{size}|{frame}|{row_idx}".encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{row_idx}"


def ensure_digital_variant(product_id: str) -> None:
    ts = now_iso()
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM variants WHERE product_id=? AND kind='digital'",
            (product_id,),
        ).fetchone()
        if row:
            return
        conn.execute(
            """
            INSERT INTO variants(id, product_id, kind, size_label, frame_label, orientation_label, sku, source_row,
                                 cost_usd, product_cost_usd, shipping_cost_usd, markup_percent,
                                 sale_price_usd, profit_usd, profit_margin_percent, quantity,
                                 visible, locked, created_at, updated_at)
            VALUES(?, ?, 'digital', 'DigitalDownload', '', '', ?, 0, 0, 0, 0, 0, 14, 14, 100, 999, 1, 1, ?, ?)
            """,
            (str(uuid.uuid4()), product_id, variant_sku(product_id, "digital", "DigitalDownload", "", 0), ts, ts),
        )


def parse_variants_csv(
    product_id: str,
    csv_path: Path,
    percent: float,
    upload_kind: str,
    include_shipping: bool,
    pricing_formula: str,
    retail_multiplier: float,
) -> dict:
    text = csv_path.read_text(encoding="utf-8-sig")
    rows, csv_was_normalized = read_csv_dict_rows(text)
    ts = now_iso()
    created = 0
    warnings = []
    if csv_was_normalized:
        warnings.append("CSV tek kolon gibi kaydedilmiş; satırlar otomatik düzeltildi.")

    upload_kind = upload_kind if upload_kind in {"framed", "unframed"} else "auto"
    settings = get_settings()
    eligible_rows = []
    for row in rows:
        frame = first_present(row, ["Frame", "Frame color", "Color", "Colour"])
        kind = upload_kind if upload_kind != "auto" else ("framed" if frame else "unframed")
        assembly = first_present(row, ["Assembly"]).strip().lower()
        if kind == "framed" and assembly and assembly != "ready-to-hang":
            continue
        eligible_rows.append(row)
    if len(eligible_rows) != len(rows):
        warnings.append(f"Ready-to-hang olmayan {len(rows) - len(eligible_rows)} satır atlandı.")
    rows = eligible_rows
    if not rows:
        raise ValueError("CSV dosyasında uygun varyasyon satırı yok. Framed için Ready-to-hang satırları gerekli.")

    ensure_digital_variant(product_id)
    with db() as conn:
        if upload_kind == "auto":
            conn.execute("DELETE FROM variants WHERE product_id=? AND kind!='digital'", (product_id,))
        else:
            conn.execute("DELETE FROM variants WHERE product_id=? AND kind=?", (product_id, upload_kind))
        for idx, row in enumerate(rows, start=1):
            size = first_present(row, ["Size", "Size (unframed)", "Variant", "Variant name"])
            frame = first_present(row, ["Frame", "Frame color", "Color", "Colour"])
            name_text = first_present(row, ["Name", "Title"])
            orientation = extract_orientation(row, size, frame, name_text)
            product_cost = parse_money(first_present(row, ["Product price", "Product cost", "Cost", "Base price"]))
            shipping = parse_money(first_present(row, ["Shipping price", "Shipping cost", "Shipping"]))
            total = parse_money(first_present(row, ["Total price", "Total cost", "Total"]))
            if total <= 0:
                total = round(product_cost + shipping, 2)
            if not size:
                size = name_text or f"Variant {idx}"
            size = clean_size_label(size, orientation)
            kind = upload_kind if upload_kind != "auto" else ("framed" if frame else "unframed")
            if kind == "unframed":
                frame = ""
            elif kind == "framed" and not frame:
                frame = "Default frame"
            basis = total if include_shipping else product_cost
            sale = resolved_variant_price(
                kind, size, basis, percent, pricing_formula, retail_multiplier, settings
            )
            profit = round(sale - total, 2)
            conn.execute(
                """
                INSERT INTO variants(id, product_id, kind, size_label, frame_label, orientation_label, sku, source_row,
                                     cost_usd, product_cost_usd, shipping_cost_usd, markup_percent,
                                     sale_price_usd, profit_usd, profit_margin_percent, quantity,
                                     visible, locked, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 999, 1, 0, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    product_id,
                    kind,
                    clean_text(size),
                    clean_text(frame),
                    orientation,
                    variant_sku(product_id, kind, size, frame, idx),
                    idx,
                    total,
                    product_cost,
                    shipping,
                    percent,
                    sale,
                    profit,
                    profit_margin(total, sale),
                    ts,
                    ts,
                ),
            )
            created += 1

    add_event(
        product_id,
        "info",
        f"{upload_kind} CSV varyasyonları hazırlandı: {created} satır.",
        "csv_variants",
        meta={
            "percent": percent,
            "include_shipping": include_shipping,
            "pricing_formula": pricing_formula,
            "gelato_retail_multiplier": retail_multiplier,
            "csv_was_normalized": csv_was_normalized,
        },
    )
    return {"created": created, "warnings": warnings}


def reprice_variants(
    product_id: str,
    percent: float,
    include_shipping: bool,
    pricing_formula: str,
    retail_multiplier: float,
    upload_kind: str = "all",
) -> None:
    ts = now_iso()
    settings = get_settings()
    with db() as conn:
        if upload_kind in {"framed", "unframed"}:
            rows = conn.execute(
                "SELECT * FROM variants WHERE product_id=? AND kind=?",
                (product_id, upload_kind),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM variants WHERE product_id=? AND kind!='digital'", (product_id,)).fetchall()
        for row in rows:
            total = float(row["cost_usd"] or 0)
            product_cost = float(row["product_cost_usd"] or 0)
            basis = total if include_shipping else product_cost
            sale = resolved_variant_price(
                row["kind"], row["size_label"], basis, percent, pricing_formula, retail_multiplier, settings
            )
            profit = round(sale - total, 2)
            conn.execute(
                """
                UPDATE variants
                SET markup_percent=?, sale_price_usd=?, profit_usd=?, profit_margin_percent=?, updated_at=?
                WHERE id=?
                """,
                (percent, sale, profit, profit_margin(total, sale), ts, row["id"]),
            )
    add_event(
        product_id,
        "info",
        f"Fiyatlar %{percent:g} ile güncellendi.",
        "pricing",
        meta={
            "include_shipping": include_shipping,
            "pricing_formula": pricing_formula,
            "gelato_retail_multiplier": retail_multiplier,
            "kind": upload_kind,
        },
    )


def apply_default_variant_csvs(product_id: str, settings: dict | None = None) -> dict:
    settings = settings or get_settings()
    results: dict[str, dict] = {}
    specs = [
        ("unframed", settings.get("default_unframed_csv_path"), float(settings.get("default_unframed_percent", 40))),
        ("framed", settings.get("default_framed_csv_path"), float(settings.get("default_framed_percent", 40))),
    ]
    for kind, path_value, percent in specs:
        path = Path(str(path_value or ""))
        if not path_value or not path.exists() or not path.is_file():
            if path_value:
                add_event(product_id, "warning", f"{kind} CSV dosyası bulunamadı. Gelişmiş ayarlardan yeniden yükleyin.", "csv_variants")
            continue
        try:
            results[kind] = parse_variants_csv(
                product_id,
                path,
                percent,
                kind,
                bool(settings.get("include_shipping_in_profit")),
                str(settings.get("pricing_formula") or "fixed_size_table"),
                float(settings.get("gelato_retail_multiplier") or 1),
            )
        except Exception as exc:
            add_event(
                product_id,
                "warning",
                f"{kind} CSV uygulanamadı: {readable_exception(exc)}",
                "csv_variants",
                meta={"error": readable_exception(exc), "path": str(path)},
            )
    if results:
        add_event(product_id, "info", "Varsayilan CSV varyasyonlari otomatik uygulandi.", "csv_variants", meta=results)
    return results


def add_event(product_id: str, kind: str, message: str, step_key=None, progress=None, meta=None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO events(product_id, kind, step_key, message, progress, meta_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (product_id, kind, step_key, message, progress, json.dumps(meta or {}, ensure_ascii=False), now_iso()),
        )


def update_product(product_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [product_id]
    with db() as conn:
        conn.execute(f"UPDATE products SET {sets} WHERE id=?", values)


def upsert_seo_output(product_id: str, seo_data: dict, settings: dict) -> None:
    ts = now_iso()
    warnings = seo_data.get("warnings") if isinstance(seo_data.get("warnings"), list) else []
    description = clean_multiline_text(seo_data.get("description") or seo_data.get("description_intro", ""))
    tail = clean_multiline_text(
        seo_data.get(
            "description_tail",
            "" if seo_data.get("description") else settings["default_description_tail"],
        )
    )
    with db() as conn:
        conn.execute(
            """
            INSERT INTO seo_outputs(product_id, title, description_intro, description_tail,
                                    tags_json, warnings_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                title=excluded.title,
                description_intro=excluded.description_intro,
                description_tail=excluded.description_tail,
                tags_json=excluded.tags_json,
                warnings_json=excluded.warnings_json,
                updated_at=excluded.updated_at
            """,
            (
                product_id,
                clean_text(seo_data.get("title", "")),
                description,
                tail,
                json.dumps(seo_data.get("tags", []), ensure_ascii=False),
                json.dumps(warnings, ensure_ascii=False),
                ts,
            ),
        )


def empty_seo_data() -> dict:
    return {
        "title": "",
        "description_intro": "",
        "description_tail": "",
        "description": "",
        "tags": [],
        "warnings": [],
    }


def etsy_primary_language_fields(product=None, seo_data: dict | None = None, settings: dict | None = None) -> dict:
    # Etsy requires primary-language copy when a draft is created. The seller
    # completes the real title, description and tags manually in Etsy.
    return {"title": "Poster", "description": "Poster", "tags": []}


def clear_assets(product_id: str, kind: str | None = None) -> None:
    with db() as conn:
        if kind:
            conn.execute("DELETE FROM assets WHERE product_id=? AND kind=?", (product_id, kind))
        else:
            conn.execute("DELETE FROM assets WHERE product_id=?", (product_id,))


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_asset(
    product_id: str,
    kind: str,
    label: str,
    path: Path | str,
    sort_order: int,
    artwork_option_id: str | None = None,
    visible: int = 1,
    *,
    protected: int = 0,
    role: str = "",
    content_sha256: str = "",
) -> str:
    asset_id = str(uuid.uuid4())
    ts = now_iso()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO assets(
                id, product_id, kind, label, path, sort_order, visible, artwork_option_id,
                protected, role, content_sha256, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id, product_id, kind, label, str(path), sort_order, int(bool(visible)),
                artwork_option_id, int(bool(protected)), clean_text(role), clean_text(content_sha256), ts, ts,
            ),
        )
    return asset_id


def update_asset_etsy_image(asset_id: str, listing_image_id, listing_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE assets SET etsy_image_id=?, etsy_listing_id=?, updated_at=? WHERE id=?",
            (str(listing_image_id), str(listing_id), now_iso(), asset_id),
        )


def asset_uploaded_to_listing(asset: sqlite3.Row, listing_id: str) -> bool:
    keys = set(asset.keys())
    if "etsy_image_id" not in keys or "etsy_listing_id" not in keys:
        return False
    image_id = clean_text(asset["etsy_image_id"] or "")
    uploaded_listing_id = clean_text(asset["etsy_listing_id"] or "")
    return bool(image_id and uploaded_listing_id == clean_text(listing_id))


def save_etsy_ready_static_image(source: Path, target: Path) -> None:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    max_side = 3000
    if max(image.size) > max_side:
        ratio = max_side / max(image.size)
        image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)

    target.parent.mkdir(parents=True, exist_ok=True)
    quality = 92
    while True:
        image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
        if target.stat().st_size <= 9 * 1024 * 1024 or quality <= 72:
            break
        quality -= 5


def canonical_static_listing_specs() -> list[dict]:
    specs = []
    for index, (label, source) in enumerate(STATIC_LISTING_IMAGES, start=1):
        specs.append(
            {
                "role": STATIC_LISTING_ROLES_BY_LABEL[label],
                "label": label,
                "source": Path(source),
                "sort_order": 700 + index,
                "index": index,
            }
        )
    return specs


def validate_static_listing_sources() -> list[dict]:
    specs = canonical_static_listing_specs()
    missing = [str(item["source"]) for item in specs if not item["source"].is_file() or item["source"].stat().st_size <= 0]
    if missing:
        raise FileNotFoundError("Korunan sabit Etsy görselleri eksik: " + " | ".join(missing))
    source_hashes = [file_sha256(item["source"]) for item in specs]
    if len(set(source_hashes)) != len(source_hashes):
        raise RuntimeError("Korunan sabit Etsy görsellerinden en az ikisi aynı dosya; işlem durduruldu.")
    for item, digest in zip(specs, source_hashes):
        item["source_sha256"] = digest
    return specs


def ensure_static_listing_images(product_id: str) -> int:
    specs = validate_static_listing_sources()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM assets WHERE product_id=? AND kind='static_listing_image' ORDER BY updated_at DESC",
            (product_id,),
        ).fetchall()
    previous: dict[str, sqlite3.Row] = {}
    duplicate_ids: list[str] = []
    for row in rows:
        role = clean_text(row["role"] if "role" in row.keys() else "") or STATIC_LISTING_ROLES_BY_LABEL.get(row["label"], "")
        if role in STATIC_LISTING_ROLES and role not in previous:
            previous[role] = row
        else:
            duplicate_ids.append(row["id"])

    target_dir = product_upload_dir(product_id) / "static_listing_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    kept_ids: set[str] = set()
    target_hashes: set[str] = set()
    for item in specs:
        target = target_dir / f"{item['index']:02d}-{slugify_filename(item['label'], 'listing-info')}.jpg"
        save_etsy_ready_static_image(item["source"], target)
        digest = file_sha256(target)
        if digest in target_hashes:
            raise RuntimeError("Korunan sabit Etsy görselleri JPEG hazırlığında aynı içeriğe dönüştü; işlem durduruldu.")
        target_hashes.add(digest)
        existing = previous.get(item["role"])
        if existing:
            kept_ids.add(existing["id"])
            with db() as conn:
                conn.execute(
                    """
                    UPDATE assets
                    SET label=?, path=?, sort_order=?, visible=1, protected=1, role=?, content_sha256=?, updated_at=?
                    WHERE id=?
                    """,
                    (item["label"], str(target), item["sort_order"], item["role"], digest, now_iso(), existing["id"]),
                )
        else:
            kept_ids.add(
                add_asset(
                    product_id,
                    "static_listing_image",
                    item["label"],
                    target,
                    item["sort_order"],
                    visible=1,
                    protected=1,
                    role=item["role"],
                    content_sha256=digest,
                )
            )

    stale_ids = set(duplicate_ids) | {row["id"] for row in rows if row["id"] not in kept_ids}
    if stale_ids:
        with db() as conn:
            conn.executemany("DELETE FROM assets WHERE id=?", [(asset_id,) for asset_id in stale_ids])
    return len(specs)


def protected_static_assets(product_id: str) -> list[sqlite3.Row]:
    ensure_static_listing_images(product_id)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM assets
            WHERE product_id=? AND kind='static_listing_image' AND protected=1 AND visible=1
            ORDER BY sort_order
            """,
            (product_id,),
        ).fetchall()
    roles = [clean_text(row["role"]) for row in rows]
    if tuple(roles) != STATIC_LISTING_ROLES:
        raise RuntimeError("Korunan dört Etsy bilgi görseli eksik veya sırası bozuk; işlem durduruldu.")
    return list(rows)


def ensure_main_listing_asset(product_id: str) -> sqlite3.Row:
    with db() as conn:
        product = conn.execute("SELECT source_image_path FROM products WHERE id=?", (product_id,)).fetchone()
        rows = conn.execute(
            "SELECT * FROM assets WHERE product_id=? AND kind='main_listing_image' ORDER BY updated_at DESC",
            (product_id,),
        ).fetchall()
    if not product:
        raise ValueError("Urun bulunamadi.")
    source = assert_artwork_source_safe(Path(clean_text(product["source_image_path"] or "")), product_id)
    digest = file_sha256(source)
    if rows:
        keep = rows[0]
        with db() as conn:
            conn.execute(
                """
                UPDATE assets
                SET label='Original main artwork', path=?, sort_order=600, visible=1,
                    protected=0, role='main_artwork', content_sha256=?, updated_at=?
                WHERE id=?
                """,
                (str(source), digest, now_iso(), keep["id"]),
            )
            if len(rows) > 1:
                conn.executemany("DELETE FROM assets WHERE id=?", [(row["id"],) for row in rows[1:]])
        asset_id = keep["id"]
    else:
        asset_id = add_asset(
            product_id,
            "main_listing_image",
            "Original main artwork",
            source,
            600,
            role="main_artwork",
            content_sha256=digest,
        )
    with db() as conn:
        return conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()


def assert_artwork_source_safe(source: Path | str, product_id: str = "") -> Path:
    path = Path(source).resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"Kaynak görsel bulunamadı: {path}")
    protected_specs = validate_static_listing_sources()
    protected_paths = {item["source"].resolve() for item in protected_specs}
    source_hashes = {clean_text(item["source_sha256"]) for item in protected_specs}
    if path in protected_paths:
        raise RuntimeError("Sabit bilgi görseli poster kaynağı olarak kullanılamaz.")
    path_hash = file_sha256(path)
    if path_hash in source_hashes:
        raise RuntimeError("Sabit bilgi görselinin kopyası poster kaynağı olarak kullanılamaz.")
    if product_id:
        static_dir = (product_upload_dir(product_id) / "static_listing_images").resolve()
        if path == static_dir or static_dir in path.parents:
            raise RuntimeError("Ürünün sabit bilgi görseli poster kaynağı olarak kullanılamaz.")
        with db() as conn:
            protected_hashes = {
                clean_text(row["content_sha256"])
                for row in conn.execute(
                    "SELECT content_sha256 FROM assets WHERE product_id=? AND protected=1",
                    (product_id,),
                ).fetchall()
                if clean_text(row["content_sha256"])
            }
        if protected_hashes and path_hash in protected_hashes:
            raise RuntimeError("Sabit bilgi görselinin kopyası poster kaynağı olarak kullanılamaz.")
    return path


def ensure_steps(product_id: str) -> None:
    with db() as conn:
        for key, label, target in STEP_DEFS:
            conn.execute(
                """
                INSERT OR IGNORE INTO steps(product_id, step_key, label, status, progress, updated_at)
                VALUES(?, ?, ?, 'pending', ?, ?)
                """,
                (product_id, key, label, 0 if target != 5 else 0, now_iso()),
            )
            conn.execute(
                "UPDATE steps SET label=?, updated_at=? WHERE product_id=? AND step_key=?",
                (label, now_iso(), product_id, key),
            )


def reset_steps_for_run(product_id: str) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE steps
            SET status='pending', progress=0, retry_count=0, error=NULL,
                started_at=NULL, completed_at=NULL, updated_at=?
            WHERE product_id=?
            """,
            (now_iso(), product_id),
        )
        conn.execute("UPDATE steps SET status='skipped', progress=100 WHERE product_id=? AND step_key IN ('digital_package', 'google_drive')", (product_id,))


def set_step(product_id: str, key: str, status: str, progress: int | None = None, error: str | None = None) -> None:
    fields = ["status=?", "updated_at=?"]
    values = [status, now_iso()]
    if progress is not None:
        fields.append("progress=?")
        values.append(max(0, min(100, int(progress))))
    if error is not None:
        fields.append("error=?")
        values.append(error)
    if status == "running":
        fields.append("started_at=COALESCE(started_at, ?)")
        values.append(now_iso())
    if status in {"done", "error", "stopped", "warning", "skipped"}:
        fields.append("completed_at=?")
        values.append(now_iso())
    values.extend([product_id, key])
    with db() as conn:
        conn.execute(f"UPDATE steps SET {', '.join(fields)} WHERE product_id=? AND step_key=?", values)


def increment_retry(product_id: str, key: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE steps SET retry_count=retry_count+1, updated_at=? WHERE product_id=? AND step_key=?",
            (now_iso(), product_id, key),
        )


def requested_stop(product_id: str) -> bool:
    with db() as conn:
        row = conn.execute("SELECT stop_requested FROM products WHERE id=?", (product_id,)).fetchone()
        return bool(row and row["stop_requested"])


class StopJob(Exception):
    pass


def check_stop(product_id: str) -> None:
    if requested_stop(product_id):
        raise StopJob()


def existing_queue_item_cancelled(item_id: str) -> bool:
    if not item_id:
        return False
    with db() as conn:
        row = conn.execute(
            "SELECT status FROM existing_mockup_queue WHERE id=?",
            (item_id,),
        ).fetchone()
    return not row or row["status"] in {"paused", "rejected"}


def sleep_progress(product_id: str, step_key: str, start: int, end: int, seconds: float) -> None:
    slices = max(3, int(seconds * 4))
    for idx in range(slices):
        check_stop(product_id)
        progress = start + int((end - start) * (idx + 1) / slices)
        step_progress = int((idx + 1) / slices * 100)
        set_step(product_id, step_key, "running", step_progress)
        update_product(product_id, overall_progress=progress, current_step=step_key)
        time.sleep(seconds / slices)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_multiline_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_etsy_listing_id(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    direct = re.fullmatch(r"\d{5,}", text)
    if direct:
        return direct.group(0)
    patterns = [
        r"/listing/(\d+)",
        r"[?&]listing_id=(\d+)",
        r"[?&]listing=(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def etsy_listing_url(listing_id: str) -> str:
    return f"https://www.etsy.com/listing/{urllib.parse.quote(str(listing_id))}"


def register_media_write_session(product_id: str, listing_id: str) -> None:
    product_id = clean_text(product_id)
    listing_id = clean_text(listing_id)
    if not product_id or not listing_id:
        return
    with media_write_lock:
        media_write_sessions.add((product_id, listing_id))


def media_write_session_exists(product_id: str, listing_id: str) -> bool:
    with media_write_lock:
        return (clean_text(product_id), clean_text(listing_id)) in media_write_sessions


def assert_etsy_listing_write_allowed(
    product_id: str,
    listing_id: str,
    settings: dict,
    operation: str,
    *,
    bypass_existing_guard: bool = False,
) -> None:
    listing_id = clean_text(listing_id)
    if not listing_id:
        raise RuntimeError(f"Etsy write guard: listing ID yok ({operation}).")
    if bypass_existing_guard:
        add_event(
            product_id,
            "warning",
            f"Existing listing write guard bypassed for controlled recovery: {operation}",
            "etsy_draft",
            meta={"listing_id": listing_id},
        )
        return
    if media_write_session_exists(product_id, listing_id):
        return
    with db() as conn:
        product = conn.execute(
            "SELECT listing_id, etsy_update_mode FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
    mode = clean_text(product["etsy_update_mode"] if product and "etsy_update_mode" in product.keys() else "")
    bound_listing_id = clean_text(product["listing_id"] if product and "listing_id" in product.keys() else "")
    raise RuntimeError(
        "Mevcut Etsy urun koruma kilidi: bu uygulama artik onceden var olan listinglere yazamaz. "
        f"operation={operation}, listing_id={listing_id}, product_listing_id={bound_listing_id}, mode={mode}. "
        "Sadece ayni oturumda yeni olusturulan draft listing guncellenebilir."
    )


def assert_etsy_media_write_allowed(
    product_id: str,
    listing_id: str,
    settings: dict,
    operation: str,
    *,
    bypass_media_guard: bool = False,
) -> None:
    if bypass_media_guard:
        add_event(
            product_id,
            "warning",
            f"Media safety guard bypassed for controlled recovery: {operation}",
            "etsy_draft",
            meta={"listing_id": listing_id},
        )
        return
    policy = clean_text(str(settings.get("etsy_media_write_policy") or "new_drafts_only"))
    if policy == "disabled":
        raise RuntimeError("Etsy media write safety guard: medya yukleme tamamen kapali.")
    assert_etsy_listing_write_allowed(
        product_id,
        listing_id,
        settings,
        operation,
        bypass_existing_guard=bypass_media_guard,
    )
    with db() as conn:
        product = conn.execute(
            "SELECT listing_id, etsy_update_mode FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
    if product and clean_text(product["etsy_update_mode"] if "etsy_update_mode" in product.keys() else "") == "inventory_only":
        raise RuntimeError("Etsy media write safety guard: inventory_only mevcut listing medyasina yazamaz.")
    if policy != "new_drafts_only":
        raise RuntimeError(f"Etsy media write safety guard: bilinmeyen policy {policy!r}.")
    if media_write_session_exists(product_id, listing_id):
        return
    raise RuntimeError(
        "Etsy media write safety guard: mevcut veya onceki oturumdan kalan listing medyasina yazma engellendi. "
        "Medya restore gerekiyorsa tools/restore_etsy_images.py dry-run ve --apply ile bilincli calistirilmalidir."
    )


def safe_tags(tags, prohibited) -> list[str]:
    out = []
    seen = set()
    for tag in tags or []:
        tag = clean_text(str(tag)).lower()
        tag = re.sub(r"[^a-z0-9 '\-]", "", tag)
        if not tag or any(term.lower() in tag for term in prohibited):
            continue
        tag = tag[:20].strip(" -'")
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
        if len(out) == 13:
            break
    fallback = [
        "poster print",
        "wall art",
        "room decor",
        "gift idea",
        "art print",
        "modern poster",
        "home decor",
        "gallery wall",
        "unframed print",
        "framed poster",
        "digital print",
        "statement art",
        "office decor",
    ]
    for tag in fallback:
        if len(out) == 13:
            break
        if tag not in seen:
            out.append(tag)
            seen.add(tag)
    return out[:13]


def remove_prohibited(text: str, prohibited: list[str]) -> str:
    cleaned = text or ""
    for term in prohibited:
        cleaned = re.sub(rf"\b{re.escape(term)}\b", "", cleaned, flags=re.IGNORECASE)
    return clean_text(cleaned)


def remove_prohibited_multiline(text: str, prohibited: list[str]) -> str:
    cleaned = text or ""
    for term in prohibited:
        cleaned = re.sub(rf"\b{re.escape(term)}\b", "", cleaned, flags=re.IGNORECASE)
    return clean_multiline_text(cleaned)


def base64_url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def oauth_redirect_uri() -> str:
    return f"http://{APP_PUBLIC_HOST}:{APP_PORT}/oauth/etsy/callback"


def etsy_api_headers(settings: dict, oauth: bool = True) -> dict:
    secrets = settings["_secrets"]
    headers = {"x-api-key": f"{secrets['etsy_keystring']}:{secrets['etsy_shared_secret']}"}
    if oauth:
        headers["Authorization"] = f"Bearer {secrets['etsy_access_token']}"
    return headers


def save_secret_updates(updates: dict) -> None:
    secrets = read_json_file(SECRETS_PATH, {})
    for key, value in updates.items():
        if value is None or value == "":
            secrets.pop(key, None)
        else:
            secrets[key] = value
    write_json_file(SECRETS_PATH, secrets)


def save_setting_updates(updates: dict) -> None:
    settings = read_json_file(SETTINGS_PATH, {})
    settings.update({key: value for key, value in updates.items() if key in DEFAULT_SETTINGS})
    write_json_file(SETTINGS_PATH, settings)


def validate_variant_csv_bytes(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV dosyasını UTF-8 CSV olarak kaydedip yeniden seçin.") from exc
    rows, _ = read_csv_dict_rows(text)
    rows = [row for row in rows if any(str(value or "").strip() for value in row.values())]
    if not rows:
        raise ValueError("CSV boş veya yalnızca başlık içeriyor; en az bir varyasyon satırı gerekli.")
    headers = {str(key).strip().lower() for key in rows[0]}
    sizes = {"size", "size (unframed)", "variant", "variant name", "name", "title"}
    costs = {"product price", "product cost", "cost", "base price", "total price", "total cost", "total"}
    if not headers.intersection(sizes) or not headers.intersection(costs):
        raise ValueError("CSV başlıkları tanınmadı. Size (veya Variant/Name) ile Product price (veya Cost/Total) sütunları gerekli.")
    return rows


def save_default_csv_setting(payload: dict, key: str, label: str) -> dict:
    # Accept the old panel's unsuffixed field as well as the canonical upload field.
    csv_file = payload.get(f"{key}_file", payload.get(key))
    if csv_file is None:
        return {}
    if not isinstance(csv_file, dict) or not csv_file.get("data_url"):
        raise ValueError(f"{label} CSV yüklemesi eksik; dosyayı yeniden seçin.")
    _mime, raw = decode_data_url(csv_file["data_url"])
    validate_variant_csv_bytes(raw)
    safe_name = slugify_filename(csv_file.get("filename") or f"{label}.csv", f"{label}.csv")
    target_dir = DATA / "default_csv" / key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{Path(safe_name).stem}-{hashlib.sha256(raw).hexdigest()[:16]}.csv"
    target.write_bytes(raw)
    return {
        f"{key}_path": str(target),
        f"{key}_name": safe_name,
    }


def start_etsy_oauth() -> dict:
    settings = get_settings()
    secrets = settings["_secrets"]
    if not secrets.get("etsy_keystring") or not secrets.get("etsy_shared_secret"):
        raise ValueError("Etsy keystring ve shared secret önce Ayarlar bölümüne kaydedilmeli.")
    verifier = base64_url(os.urandom(48))
    challenge = base64_url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = uuid.uuid4().hex
    payload = {
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": oauth_redirect_uri(),
        "created_at": now_iso(),
    }
    write_json_file(ETSY_OAUTH_PATH, payload)
    scopes = "listings_r listings_w shops_r shops_w"
    params = {
        "response_type": "code",
        "redirect_uri": payload["redirect_uri"],
        "scope": scopes,
        "client_id": secrets["etsy_keystring"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = "https://www.etsy.com/oauth/connect?" + urllib.parse.urlencode(params)
    return {"authorize_url": url, "redirect_uri": payload["redirect_uri"], "scopes": scopes}


def is_dns_resolution_error(exc: Exception) -> bool:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return (
        isinstance(reason, socket.gaierror)
        or getattr(reason, "errno", None) == 11001
        or "getaddrinfo failed" in str(reason).lower()
    )


def urlopen_with_dns_retry(request, *, timeout: int, attempts: int = 5):
    for attempt in range(1, attempts + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except Exception as exc:
            if not is_dns_resolution_error(exc) or attempt >= attempts:
                raise
            time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
    raise RuntimeError("Ag baglantisi kurulamadi.")


def request_json(url: str, method: str = "GET", headers: dict | None = None, payload=None, timeout: int = 60) -> dict:
    data = None
    if payload is not None:
        if isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        else:
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urlopen_with_dns_retry(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def request_form_json(url: str, fields: dict, headers: dict | None = None, timeout: int = 60) -> dict:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    with urlopen_with_dns_retry(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def readable_exception(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = clean_text(body)
        if body:
            try:
                parsed = json.loads(body)
                detail = clean_text(str(parsed.get("error") or parsed.get("message") or body))
            except Exception:
                pass
        base = f"HTTP Error {exc.code}: {exc.reason}"
        return f"{base} - {detail}" if detail else base
    return str(exc)


def etsy_listing_removed_error(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    return "is removed" in lowered or "could not find a listing" in lowered or "resource not found" in lowered


def exchange_etsy_oauth_code(code: str, state: str) -> dict:
    oauth_state = read_json_file(ETSY_OAUTH_PATH, {})
    if not oauth_state or oauth_state.get("state") != state:
        raise ValueError("Etsy OAuth state eşleşmedi; bağlantı yeniden başlatılmalı.")
    created = datetime.fromisoformat(oauth_state["created_at"])
    if (datetime.now(timezone.utc) - created).total_seconds() > 600:
        raise ValueError("Bağlantı isteğinin süresi doldu. Yeniden bağlanın.")
    write_json_file(ETSY_OAUTH_PATH, {})
    settings = get_settings()
    secrets = settings["_secrets"]
    token_data = request_form_json(
        "https://api.etsy.com/v3/public/oauth/token",
        {
            "grant_type": "authorization_code",
            "client_id": secrets["etsy_keystring"],
            "redirect_uri": oauth_state["redirect_uri"],
            "code": code,
            "code_verifier": oauth_state["code_verifier"],
        },
    )
    expires_in = int(token_data.get("expires_in") or 3600)
    save_secret_updates(
        {
            "etsy_access_token": token_data.get("access_token"),
            "etsy_refresh_token": token_data.get("refresh_token"),
            "etsy_token_expires_at": str(int(time.time()) + expires_in - 120),
            "etsy_shop_id": None,
            "etsy_shipping_profile_id": None,
            "etsy_readiness_state_id": None,
            "etsy_production_partner_id": None,
        }
    )
    settings = get_settings()
    discover_etsy_shop_settings(settings)
    return token_data


def refresh_etsy_token(settings: dict) -> dict:
    secrets = settings["_secrets"]
    refresh_token = secrets.get("etsy_refresh_token")
    if not refresh_token:
        return settings
    expires_at = int(float(secrets.get("etsy_token_expires_at") or 0))
    if expires_at and expires_at > int(time.time()) + 120:
        return settings
    token_data = request_form_json(
        "https://api.etsy.com/v3/public/oauth/token",
        {
            "grant_type": "refresh_token",
            "client_id": secrets["etsy_keystring"],
            "refresh_token": refresh_token,
        },
    )
    expires_in = int(token_data.get("expires_in") or 3600)
    save_secret_updates(
        {
            "etsy_access_token": token_data.get("access_token"),
            "etsy_refresh_token": token_data.get("refresh_token") or refresh_token,
            "etsy_token_expires_at": str(int(time.time()) + expires_in - 120),
        }
    )
    return get_settings()


def parse_results(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            return data["results"]
        if isinstance(data.get("shops"), list):
            return data["shops"]
    return []


def discover_shop_id(settings: dict) -> str | None:
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    if secrets.get("etsy_shop_id"):
        return str(secrets["etsy_shop_id"])
    if not secrets.get("etsy_access_token"):
        return None
    user_id = ""
    try:
        me = request_json(
            "https://api.etsy.com/v3/application/users/me",
            headers=etsy_api_headers(settings, oauth=True),
        )
        user_id = str(me.get("user_id") or me.get("id") or "")
    except Exception:
        token = secrets.get("etsy_access_token") or ""
        user_id = token.split(".", 1)[0] if "." in token else ""
    if not user_id:
        return None
    shop_data = request_json(
        f"https://api.etsy.com/v3/application/users/{urllib.parse.quote(user_id)}/shops",
        headers=etsy_api_headers(settings, oauth=True),
    )
    shops = parse_results(shop_data)
    shop = shops[0] if shops else (shop_data if isinstance(shop_data, dict) else {})
    shop_id = shop.get("shop_id") or shop.get("shopId") or shop.get("id")
    if shop_id:
        save_secret_updates({"etsy_shop_id": str(shop_id)})
        return str(shop_id)
    return None


def shipping_profile_is_free(settings: dict, shop_id: str, profile_id: str) -> bool:
    data = request_json(
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(shop_id))}/shipping-profiles/"
        f"{urllib.parse.quote(str(profile_id))}/destinations?limit=100",
        headers=etsy_api_headers(settings, oauth=True),
    )
    destinations = parse_results(data)
    return bool(destinations) and all(
        money_is_zero(item.get("primary_cost")) and money_is_zero(item.get("secondary_cost"))
        for item in destinations
    )


def shipping_profile_title(profile: dict) -> str:
    return clean_text(str(profile.get("title") or profile.get("name") or profile.get("shipping_profile_name") or ""))


def title_matches_required_shipping(profile: dict, settings: dict) -> bool:
    required = clean_text(str(settings.get("required_shipping_profile_name") or ""))
    if not required:
        return True
    return shipping_profile_title(profile).lower() == required.lower()


def shipping_profile_destinations_are_free(profile: dict) -> bool | None:
    destinations = profile.get("shipping_profile_destinations")
    if not isinstance(destinations, list) or not destinations:
        return None
    return all(
        money_is_zero(item.get("primary_cost")) and money_is_zero(item.get("secondary_cost"))
        for item in destinations
    )


def discover_shipping_profile(settings: dict, shop_id: str) -> str | None:
    secrets = settings["_secrets"]
    data = request_json(
        f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(str(shop_id))}/shipping-profiles",
        headers=etsy_api_headers(settings, oauth=True),
    )
    profiles = parse_results(data)
    required_name = clean_text(str(settings.get("required_shipping_profile_name") or ""))
    if secrets.get("etsy_shipping_profile_id"):
        existing_id = str(secrets["etsy_shipping_profile_id"])
        existing = next(
            (profile for profile in profiles if str(profile.get("shipping_profile_id") or profile.get("id")) == existing_id),
            None,
        )
        if existing and title_matches_required_shipping(existing, settings):
            free_status = shipping_profile_destinations_are_free(existing)
            if free_status is True or not settings.get("free_shipping_required"):
                return existing_id
            if free_status is None and shipping_profile_is_free(settings, shop_id, existing_id):
                return existing_id
        save_secret_updates({"etsy_shipping_profile_id": ""})

    for profile in profiles:
        profile_id = profile.get("shipping_profile_id") or profile.get("id")
        if not profile_id:
            continue
        if not title_matches_required_shipping(profile, settings):
            continue
        free_status = shipping_profile_destinations_are_free(profile)
        try:
            is_free = free_status if free_status is not None else shipping_profile_is_free(settings, shop_id, str(profile_id))
            if is_free or not settings.get("free_shipping_required"):
                save_secret_updates({"etsy_shipping_profile_id": str(profile_id)})
                return str(profile_id)
        except Exception:
            continue
    return None


def discover_readiness_state(settings: dict, shop_id: str) -> str | None:
    secrets = settings["_secrets"]
    if secrets.get("etsy_readiness_state_id"):
        return str(secrets["etsy_readiness_state_id"])
    data = request_json(
        f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(str(shop_id))}/readiness-state-definitions?limit=100",
        headers=etsy_api_headers(settings, oauth=True),
    )
    profiles = parse_results(data)
    chosen = None
    for profile in profiles:
        if str(profile.get("readiness_state") or "").lower() == "made_to_order":
            chosen = profile
            break
    chosen = chosen or (profiles[0] if profiles else None)
    if not chosen:
        return None
    readiness_id = chosen.get("readiness_state_id") or chosen.get("readiness_state_definition_id") or chosen.get("id")
    if readiness_id:
        save_secret_updates({"etsy_readiness_state_id": str(readiness_id)})
        return str(readiness_id)
    return None


def discover_production_partner(settings: dict, shop_id: str) -> str | None:
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    required_name = clean_text(str(settings.get("required_production_partner_name") or "Gelato")).lower()
    existing_id = clean_text(str(secrets.get("etsy_production_partner_id") or ""))
    data = request_json(
        f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(str(shop_id))}/production-partners",
        headers=etsy_api_headers(settings, oauth=True),
    )
    partners = parse_results(data)
    if existing_id:
        existing = next(
            (
                partner
                for partner in partners
                if str(partner.get("production_partner_id") or partner.get("id")) == existing_id
            ),
            None,
        )
        if existing:
            return existing_id
        save_secret_updates({"etsy_production_partner_id": ""})
    chosen = None
    for partner in partners:
        name = clean_text(str(partner.get("partner_name") or partner.get("name") or "")).lower()
        if required_name and required_name in name:
            chosen = partner
            break
    chosen = chosen or (partners[0] if partners else None)
    partner_id = chosen.get("production_partner_id") if chosen else None
    if partner_id:
        save_secret_updates({"etsy_production_partner_id": str(partner_id)})
        return str(partner_id)
    return None


def score_taxonomy_path(path: list[str]) -> int:
    text = " > ".join(path).lower()
    score = 0
    if "art" in text:
        score += 20
    if "prints" in text:
        score += 50
    if "poster" in text:
        score += 90
    if path and path[-1].lower() in {"posters", "poster"}:
        score += 120
    return score


def discover_poster_taxonomy(settings: dict) -> int | None:
    if int(settings.get("default_taxonomy_id") or 0) > 0:
        return int(settings["default_taxonomy_id"])
    data = request_json(
        "https://api.etsy.com/v3/application/seller-taxonomy/nodes",
        headers=etsy_api_headers(settings, oauth=False),
    )
    nodes = parse_results(data)
    best = {"score": 0, "id": None, "path": []}

    def walk(items, path):
        for item in items or []:
            name = clean_text(str(item.get("name") or ""))
            current_path = path + [name]
            node_id = item.get("id") or item.get("taxonomy_id")
            score = score_taxonomy_path(current_path)
            if node_id and score > best["score"]:
                best.update({"score": score, "id": int(node_id), "path": current_path})
            children = item.get("children") or item.get("nodes") or []
            walk(children, current_path)

    walk(nodes, [])
    if best["id"]:
        save_setting_updates({"default_taxonomy_id": int(best["id"])})
        return int(best["id"])
    return None


def discover_etsy_shop_settings(settings: dict | None = None) -> dict:
    settings = refresh_etsy_token(settings or get_settings())
    try:
        shop_id = discover_shop_id(settings)
    except Exception:
        shop_id = None
    settings = get_settings()
    if shop_id:
        try:
            discover_shipping_profile(settings, shop_id)
        except Exception:
            pass
        try:
            discover_readiness_state(get_settings(), shop_id)
        except Exception:
            pass
        try:
            discover_production_partner(get_settings(), shop_id)
        except Exception:
            pass
    try:
        discover_poster_taxonomy(get_settings())
    except Exception:
        pass
    return public_settings()


def etsy_ready(settings: dict) -> tuple[bool, list[str]]:
    secrets = settings.get("_secrets", {})
    required = {
        "etsy_keystring": secrets.get("etsy_keystring"),
        "etsy_shared_secret": secrets.get("etsy_shared_secret"),
        "etsy_access_token": secrets.get("etsy_access_token"),
        "etsy_shop_id": secrets.get("etsy_shop_id"),
        "etsy_shipping_profile_id": secrets.get("etsy_shipping_profile_id"),
        "etsy_readiness_state_id": secrets.get("etsy_readiness_state_id"),
    }
    if clean_text(str(settings.get("required_production_partner_name") or "")):
        required["etsy_production_partner_id"] = secrets.get("etsy_production_partner_id")
    missing = [key for key, value in required.items() if not value]
    if int(settings.get("default_taxonomy_id") or 0) <= 0:
        missing.append("default_taxonomy_id")
    return len(missing) == 0, missing


def money_is_zero(value: dict | None) -> bool:
    if not isinstance(value, dict):
        return False
    return int(value.get("amount") or 0) == 0


def verify_free_shipping_profile(settings: dict) -> tuple[bool, str]:
    if not settings.get("free_shipping_required"):
        return True, "free shipping validation disabled"
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    required_name = clean_text(str(settings.get("required_shipping_profile_name") or ""))
    if required_name:
        try:
            profiles_data = request_json(
                f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(str(secrets['etsy_shop_id']))}/shipping-profiles",
                headers=etsy_api_headers(settings, oauth=True),
            )
            profile_id = str(secrets["etsy_shipping_profile_id"])
            selected = next(
                (
                    profile
                    for profile in parse_results(profiles_data)
                    if str(profile.get("shipping_profile_id") or profile.get("id")) == profile_id
                ),
                None,
            )
            if not selected:
                return False, f"Seçili shipping profile Etsy mağazasında bulunamadı: {profile_id}"
            if not title_matches_required_shipping(selected, settings):
                return False, (
                    f"Secili shipping profile '{shipping_profile_title(selected)}'; "
                    f"zorunlu profil '{required_name}' olmali."
                )
        except Exception as exc:
            return False, f"Shipping profile adi dogrulanamadi: {exc}"
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/shipping-profiles/"
        f"{urllib.parse.quote(str(secrets['etsy_shipping_profile_id']))}/destinations?limit=100"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers=etsy_api_headers(settings, oauth=True),
    )
    with urlopen_with_dns_retry(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    destinations = data.get("results") or []
    if not destinations:
        return False, "Shipping profile destination bulunamadı."
    non_zero = [
        item
        for item in destinations
        if not money_is_zero(item.get("primary_cost")) or not money_is_zero(item.get("secondary_cost"))
    ]
    if non_zero:
        return False, "Seçili Etsy shipping profile ücretsiz değil; primary/secondary cost sıfır olmalı."
    return True, "Shipping profile ücretsiz kargo için uygun."


def create_etsy_draft(product_id: str, product, seo_data: dict, settings: dict) -> dict:
    with db() as conn:
        existing_product = conn.execute(
            "SELECT listing_id FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
    existing_listing_id = clean_text(existing_product["listing_id"] if existing_product else "")
    if existing_listing_id:
        raise RuntimeError(
            "Mevcut Etsy urun koruma kilidi: listing ID bagli bir urun icin yeni draft/guncelleme baslatilamaz. "
            f"listing_id={existing_listing_id}"
        )
    settings = refresh_etsy_token(settings)
    try:
        discover_etsy_shop_settings(settings)
        settings = get_settings()
    except Exception as exc:
        add_event(product_id, "warning", "Etsy ayar kesfi tamamlanamadi.", "etsy_draft", meta={"error": readable_exception(exc)})
    ok, missing = etsy_ready(settings)
    if not ok:
        return {"_mock": True, "missing": missing}
    secrets = settings["_secrets"]
    free_ok, free_message = verify_free_shipping_profile(settings)
    if not free_ok:
        return {"_mock": True, "free_shipping_failed": True, "message": free_message}
    primary_fields = etsy_primary_language_fields(product, seo_data, settings)
    with db() as conn:
        row = conn.execute(
            "SELECT MIN(sale_price_usd) AS min_price FROM variants WHERE product_id=? AND visible=1",
            (product_id,),
        ).fetchone()
    min_price = float(row["min_price"] or settings["default_price_usd"] or 14)
    form = {
        "quantity": str(int(settings["default_quantity"])),
        "title": primary_fields["title"],
        "description": primary_fields["description"],
        "price": str(min_price),
        "who_made": settings["default_who_made"],
        "when_made": settings["default_when_made"],
        "taxonomy_id": str(int(settings["default_taxonomy_id"])),
        "shipping_profile_id": str(secrets["etsy_shipping_profile_id"]),
        "type": clean_text(str(settings.get("default_listing_type") or "physical")),
        "is_supply": "false",
        "should_auto_renew": "true" if bool(settings.get("etsy_should_auto_renew")) else "false",
    }
    selection_name = clean_text(product["selection_name"] if product and "selection_name" in product.keys() else "")
    shop_section_id = clean_text(product["etsy_shop_section_id"] if product and "etsy_shop_section_id" in product.keys() else "")
    if selection_name and not shop_section_id:
        shop_section_id = resolve_shop_section_id(settings, selection_name)
        if shop_section_id:
            update_product(product_id, etsy_shop_section_id=shop_section_id)
    if shop_section_id:
        form["shop_section_id"] = shop_section_id
    elif selection_name:
        add_event(
            product_id,
            "warning",
            f"'{selection_name}' Etsy mağaza bölümünde bulunamadı; draft bölümsüz oluşturulacak.",
            "etsy_draft",
        )
    if secrets.get("etsy_readiness_state_id"):
        form["readiness_state_id"] = str(secrets["etsy_readiness_state_id"])
    if secrets.get("etsy_production_partner_id"):
        form["production_partner_ids"] = [str(secrets["etsy_production_partner_id"])]
    body = urllib.parse.urlencode(form, doseq=True).encode("utf-8")
    url = f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            **etsy_api_headers(settings, oauth=True),
        },
    )
    with urlopen_with_dns_retry(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    listing_id = data.get("listing_id")
    if listing_id:
        register_media_write_session(product_id, str(listing_id))
        update_product(
            product_id,
            listing_id=str(listing_id),
            etsy_listing_state=clean_text(str(data.get("state") or "draft")).lower(),
        )
    return data


def update_etsy_listing_metadata(product_id: str, listing_id: str, seo_data: dict, settings: dict) -> dict:
    assert_etsy_listing_write_allowed(product_id, listing_id, settings, "etsy.updateListingMetadata")
    settings = refresh_etsy_token(settings)
    try:
        discover_etsy_shop_settings(settings)
        settings = get_settings()
    except Exception as exc:
        add_event(product_id, "warning", "Etsy ayar kesfi tamamlanamadi.", "etsy_draft", meta={"error": readable_exception(exc)})
    secrets = settings["_secrets"]
    primary_fields = etsy_primary_language_fields(None, seo_data, settings)
    form = {
        "title": primary_fields["title"],
        "description": primary_fields["description"],
        "taxonomy_id": str(int(settings["default_taxonomy_id"])),
        "who_made": settings["default_who_made"],
        "when_made": settings["default_when_made"],
        "type": clean_text(str(settings.get("default_listing_type") or "physical")),
        "is_supply": "false",
        "should_auto_renew": "true" if bool(settings.get("etsy_should_auto_renew")) else "false",
    }
    if secrets.get("etsy_shipping_profile_id"):
        form["shipping_profile_id"] = str(secrets["etsy_shipping_profile_id"])
    if secrets.get("etsy_production_partner_id"):
        form["production_partner_ids"] = [str(secrets["etsy_production_partner_id"])]
    body = urllib.parse.urlencode(form, doseq=True).encode("utf-8")
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/"
        f"{urllib.parse.quote(str(listing_id))}"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            **etsy_api_headers(settings, oauth=True),
        },
    )
    with urlopen_with_dns_retry(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    add_event(product_id, "info", "Etsy draft başlık/açıklama güncellendi.", "etsy_draft", meta={"listing_id": str(listing_id), "title_length": len(form["title"])})
    return data


def etsy_variation_value(value: str, fallback: str) -> str:
    text = clean_text(value) or fallback
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return clean_text(text)[:255] or fallback


def canonical_etsy_size_label(value: str) -> str:
    text = etsy_variation_value(value, "Size")
    text = (
        text.replace("″", '"')
        .replace("“", '"')
        .replace("”", '"')
        .replace("''", '"')
        .replace("×", "x")
    )
    text = clean_text(text)
    a_match = re.match(r"^(A[0-4])\b", text, flags=re.IGNORECASE)
    if a_match:
        a_map = {
            "A4": "A4 (21 x 29.7 cm)",
            "A3": "A3 (29.7 x 42 cm)",
            "A2": "A2 (42 x 59.4 cm)",
            "A1": "A1 (59.4 x 84.1 cm)",
            "A0": "A0 (84.1 x 118.9 cm)",
        }
        return a_map.get(a_match.group(1).upper(), text)
    return text


def available_size_lines(product_id: str | None = None) -> list[str]:
    fallback = [
        "Digital Download (+9K)",
        '13x18 cm / 5x7"',
        '15x20 cm / 6x8"',
        '21x29.7 cm / 8x12"',
        '28x43 cm / XL (11x17")',
        "A3 (29.7 x 42 cm)",
        '30x40 cm / 12x16"',
        '30x45 cm / 12x18"',
        '40x60 cm / 16x24"',
        "A2 (42 x 59.4 cm)",
        '45x60 cm / 18x24"',
        '50x70 cm / 20x28"',
        "A1 (59.4 x 84.1 cm)",
        '60x80 cm / 24x32"',
        '60x90 cm / 24x36"',
        '70x100 cm / 28x40"',
        '75x100 cm / 30x40"',
        "A0 (84.1 x 118.9 cm)",
    ]
    if not product_id:
        return fallback
    with db() as conn:
        rows = conn.execute(
            """
            SELECT kind, size_label, MIN(sale_price_usd) AS min_price
            FROM variants
            WHERE product_id=? AND visible=1
            GROUP BY kind, size_label
            ORDER BY CASE kind WHEN 'digital' THEN 0 ELSE 1 END, min_price, size_label
            """,
            (product_id,),
        ).fetchall()
    if not rows:
        return fallback
    sizes = []
    if any(row["kind"] == "digital" for row in rows):
        sizes.append("Digital Download (+9K)")
    seen = set()
    for row in rows:
        if row["kind"] == "digital":
            continue
        label = canonical_etsy_size_label(row["size_label"])
        if label not in seen:
            seen.add(label)
            sizes.append(label)
    return sizes or fallback


FRAMED_PRODUCT_DETAILS = """Framed Poster Details
Our sturdy, durable wooden framed posters come ready to hang. Enjoy silky, high-quality art on lightweight, classic semi-gloss paper.
• Ready-to-hang: Includes hanging kit, ready to hang directly on the wall.
• Frame Material: Durable pine wood.
• Frame Color: Black, white smooth finish, natural wood, and dark brown wood with visible grain.
• Frame Measurements: 20-25mm (0.79"-0.98") thick, 10-14mm (0.4"-0.6") wide.
• Paper Weight: 170 gsm (65 lb), thickness: 0.19 mm (7.5 mils).
• Paper Finishing: Semi-glossy, enhances colors with a subtle shine.
• Protection: Shatterproof plexiglass protects the poster.
• Sustainable Paper: FSC-certified materials or equivalent.
• No minimum orders, printed and shipped on demand."""


def format_size_section(product_id: str | None = None) -> str:
    return "Available Sizes\n" + "\n".join(f"• {line}" for line in available_size_lines(product_id))


def build_description_template(product_id: str | None, creative_body: str, search_phrases: list[str]) -> str:
    body = clean_multiline_text(creative_body)
    phrases = [clean_text(str(item)) for item in search_phrases if clean_text(str(item))]
    if not phrases:
        phrases = [
            "statement wall art",
            "modern poster print",
            "sports room decor",
            "fan gift artwork",
            "gallery wall poster",
            "black white wall art",
        ]
    search_block = "Perfect for those searching for:\n" + "\n".join(f"• {phrase}" for phrase in phrases[:8])
    details = """Premium Product Details
Crafted for collectors of meaningful, display-ready wall art:
• Paper Finish: Semi-glossy with enhanced contrast
• Paper Weight: 170 gsm (65 lb), thickness 0.19 mm
• Print Quality: High-resolution with sharp details and deep tonal range
• Sustainability: FSC-certified or equivalent eco-conscious paper
• Production: Print-on-demand, no mass production"""
    packaging = """Packaging & Delivery
• Securely shipped in durable protective packaging
• Crease-free, damage-resistant packaging
• Dispatched within 24 hours
• Estimated delivery: 2-5 business days after dispatch"""
    notes = """Important Notes
• This listing includes unframed poster, framed poster, and digital download options where available
• Frames and decorative items shown in mockups are not included unless a framed option is selected
• For personal use only, not licensed for commercial reproduction

All Rights Reserved"""
    return clean_multiline_text(
        "\n\n".join([body, search_block, format_size_section(product_id), details, FRAMED_PRODUCT_DETAILS, packaging, notes])
    )


ETSY_CLEAN_SIZE_LABELS = {
    "13x18": '5 x 7 in (13 x 18 cm)',
    "15x20": '6 x 8 in (15 x 20 cm)',
    "20x25": '8 x 10 in (20 x 25 cm)',
    "21x29.7": '8 x 12 in (21 x 29.7 cm)',
    "27x35": '11 x 14 in (27 x 35 cm)',
    "28x43": '11 x 17 in (28 x 43 cm)',
    "a3": 'A3 (29.7 x 42 cm)',
    "30x40": '12 x 16 in (30 x 40 cm)',
    "30x45": '12 x 18 in (30 x 45 cm)',
    "40x50": '16 x 20 in (40 x 50 cm)',
    "40x60": '16 x 24 in (40 x 60 cm)',
    "a2": 'A2 (42 x 59.4 cm)',
    "45x60": '18 x 24 in (45 x 60 cm)',
    "50x70": '20 x 28 in (50 x 70 cm)',
    "a1": 'A1 (59.4 x 84.1 cm)',
    "60x80": '24 x 32 in (60 x 80 cm)',
    "60x90": '24 x 36 in (60 x 90 cm)',
    "70x100": '28 x 40 in (70 x 100 cm)',
    "75x100": '30 x 40 in (75 x 100 cm)',
    "a0": 'A0 (84.1 x 118.9 cm)',
}
ETSY_CLEAN_SIZE_ORDER = {
    label: index
    for index, label in enumerate(
        [
            "Digital File",
            ETSY_CLEAN_SIZE_LABELS["13x18"],
            ETSY_CLEAN_SIZE_LABELS["15x20"],
            ETSY_CLEAN_SIZE_LABELS["20x25"],
            ETSY_CLEAN_SIZE_LABELS["21x29.7"],
            ETSY_CLEAN_SIZE_LABELS["27x35"],
            ETSY_CLEAN_SIZE_LABELS["28x43"],
            ETSY_CLEAN_SIZE_LABELS["30x40"],
            ETSY_CLEAN_SIZE_LABELS["a3"],
            ETSY_CLEAN_SIZE_LABELS["30x45"],
            ETSY_CLEAN_SIZE_LABELS["40x50"],
            ETSY_CLEAN_SIZE_LABELS["40x60"],
            ETSY_CLEAN_SIZE_LABELS["a2"],
            ETSY_CLEAN_SIZE_LABELS["45x60"],
            ETSY_CLEAN_SIZE_LABELS["50x70"],
            ETSY_CLEAN_SIZE_LABELS["a1"],
            ETSY_CLEAN_SIZE_LABELS["60x80"],
            ETSY_CLEAN_SIZE_LABELS["60x90"],
            ETSY_CLEAN_SIZE_LABELS["70x100"],
            ETSY_CLEAN_SIZE_LABELS["75x100"],
            ETSY_CLEAN_SIZE_LABELS["a0"],
        ]
    )
}


def etsy_format_value(row: sqlite3.Row, clean_layout: bool = False) -> str:
    kind = row["kind"]
    if kind == "digital":
        return "Digital Download" if clean_layout else "DigitalDownload"
    if kind == "unframed":
        return "Unframed Print" if clean_layout else "No Frame"
    frame = etsy_variation_value(row["frame_label"], "Frame")
    lowered = frame.lower()
    if clean_layout:
        if "white" in lowered:
            return "White Wood Frame"
        if "dark" in lowered and "wood" in lowered:
            return "Dark Wood Frame"
        if "black" in lowered:
            return "Black Wood Frame"
        if "metal" in lowered:
            return "Metal Frame"
        if "wood" in lowered or "natural" in lowered:
            return "Natural Wood Frame"
        return f"{frame} Frame"
    if "framed" in lowered:
        return frame
    if "frame" in lowered:
        return re.sub(r"\bframe\b", "Framed", frame, flags=re.IGNORECASE)
    frame_map = {
        "white": "White Wooden Framed",
        "wood": "Wood Wooden Framed",
        "dark wood": "Dark Wood Wooden Framed",
        "black": "Black Wooden Framed",
        "metal": "Metal Framed",
    }
    mapped = frame_map.get(lowered)
    if mapped:
        return mapped
    if "wood" in lowered:
        return f"{frame} Wooden Framed"
    return f"{frame} Framed"


def etsy_size_value(
    row: sqlite3.Row,
    orientations_by_size: dict[str, set[str]] | None = None,
    clean_layout: bool = False,
) -> str:
    if row["kind"] == "digital":
        return "Digital File" if clean_layout else "DigitalDownload"
    size = canonical_etsy_size_label(row["size_label"])
    if clean_layout:
        size = ETSY_CLEAN_SIZE_LABELS.get(canonical_size_key(size), size)
    orientation = clean_text(row["orientation_label"] if "orientation_label" in row.keys() else "")
    if orientations_by_size and orientation and len(orientations_by_size.get(size, set())) > 1:
        return f"{size} - {orientation}"
    return size


def build_etsy_inventory_payload(
    product_id: str,
    settings: dict,
    artwork_mode: str = "separate",
    layout: str = "legacy",
) -> dict:
    secrets = settings["_secrets"]
    readiness_id = secrets.get("etsy_readiness_state_id")
    if not readiness_id:
        raise ValueError("Etsy readiness_state_id yok; Ayarlar > Etsy ayar keşfet çalıştırılmalı.")
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM variants
            WHERE product_id=? AND visible=1
            ORDER BY
                CASE kind WHEN 'digital' THEN 0 WHEN 'framed' THEN 1 WHEN 'unframed' THEN 2 ELSE 3 END,
                sale_price_usd ASC,
                size_label, orientation_label, frame_label, source_row
            """,
            (product_id,),
        ).fetchall()
    if not rows:
        raise ValueError("Etsy inventory için görünür varyasyon bulunamadı.")

    orientations_by_size: dict[str, set[str]] = {}
    for row in rows:
        if row["kind"] == "digital":
            continue
        size = canonical_etsy_size_label(row["size_label"])
        orientation = clean_text(row["orientation_label"] if "orientation_label" in row.keys() else "")
        orientations_by_size.setdefault(size, set())
        if orientation:
            orientations_by_size[size].add(orientation)

    clean_layout = layout == "format_first_clean"

    def variant_key(row: sqlite3.Row) -> tuple[str, str]:
        return (
            etsy_size_value(row, orientations_by_size, clean_layout),
            etsy_format_value(row, clean_layout),
        )

    def frame_option_rank(value: str) -> tuple[int, str]:
        lowered = value.lower()
        if lowered in {"digitaldownload", "digital download"}:
            return (0, lowered)
        if lowered in {"no frame", "unframed print"}:
            return (1, lowered)
        if lowered.startswith("black"):
            return (2, lowered)
        if lowered == "no frame":
            return (1, lowered)
        if lowered.startswith("white"):
            return (3, lowered)
        if lowered.startswith("wood") or lowered.startswith("natural"):
            return (4, lowered)
        if lowered.startswith("dark wood"):
            return (5, lowered)
        if lowered.startswith("metal"):
            return (6, lowered)
        return (50, lowered)

    size_values = []
    format_values = []
    by_key = {}
    size_sort_price = {}
    for row in rows:
        size_value, format_value = variant_key(row)
        if size_value not in size_values:
            size_values.append(size_value)
        if format_value not in format_values:
            format_values.append(format_value)
        by_key[(size_value, format_value)] = row
        price = float(row["sale_price_usd"] or 0)
        if price > 0:
            size_sort_price[size_value] = min(size_sort_price.get(size_value, price), price)

    if clean_layout:
        size_values.sort(key=lambda value: (ETSY_CLEAN_SIZE_ORDER.get(value, 999), value.lower()))
    else:
        size_values.sort(
            key=lambda value: (
                0 if value == "DigitalDownload" else 1,
                size_sort_price.get(value, 0),
                value.lower(),
            )
        )
    format_values.sort(key=frame_option_rank)

    enabled_prices = [float(row["sale_price_usd"] or 0) for row in rows if float(row["sale_price_usd"] or 0) > 0]
    disabled_price = round(min(enabled_prices) if enabled_prices else float(settings["default_price_usd"]), 2)
    products = []
    enabled_count = 0
    for size_value in size_values:
        for format_value in format_values:
            row = by_key.get((size_value, format_value))
            is_enabled = row is not None
            if is_enabled:
                enabled_count += 1
            sku_source = row["sku"] if row else f"disabled-{product_id}-{size_value}-{format_value}"
            sku = row["sku"] if row else "OFF-" + hashlib.sha1(sku_source.encode("utf-8")).hexdigest()[:12]
            size_property = {
                "property_id": ETSY_SIZE_PROPERTY_ID,
                "property_name": "Size",
                "scale_id": None,
                "value_ids": [],
                "values": [size_value],
            }
            format_property = {
                "property_id": ETSY_FORMAT_PROPERTY_ID,
                "property_name": "Format" if clean_layout else "Frame Option",
                "scale_id": None,
                "value_ids": [],
                "values": [format_value],
            }
            products.append(
                {
                    "sku": sku,
                    "offerings": [
                        {
                            "quantity": int(row["quantity"] or settings["default_quantity"]) if row else 0,
                            "is_enabled": bool(is_enabled),
                            "price": round(float(row["sale_price_usd"] or 0), 2) if row else disabled_price,
                            "readiness_state_id": int(readiness_id),
                        }
                    ],
                    "property_values": (
                        [format_property, size_property]
                        if clean_layout
                        else [size_property, format_property]
                    ),
                }
            )

    on_properties = (
        [ETSY_FORMAT_PROPERTY_ID, ETSY_SIZE_PROPERTY_ID]
        if clean_layout
        else [ETSY_SIZE_PROPERTY_ID, ETSY_FORMAT_PROPERTY_ID]
    )

    return {
        "products": products,
        "_enabled_products_count": enabled_count,
        "price_on_property": on_properties,
        "quantity_on_property": on_properties,
        "sku_on_property": on_properties,
        "readiness_state_on_property": [],
    }


def update_etsy_inventory(
    product_id: str,
    listing_id: str,
    settings: dict,
    *,
    allow_existing: bool = False,
) -> dict:
    assert_etsy_listing_write_allowed(
        product_id,
        listing_id,
        settings,
        "etsy.updateListingInventory",
        bypass_existing_guard=allow_existing,
    )
    settings = refresh_etsy_token(settings)
    payload = build_etsy_inventory_payload(product_id, settings, layout="format_first_clean")

    def send_inventory(current_payload: dict) -> dict:
        api_payload = {key: value for key, value in current_payload.items() if not key.startswith("_")}
        url = f"https://api.etsy.com/v3/application/listings/{urllib.parse.quote(str(listing_id))}/inventory"
        return request_json(
            url,
            method="PUT",
            headers=etsy_api_headers(settings, oauth=True),
            payload=api_payload,
            timeout=90,
        )

    try:
        data = send_inventory(payload)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(readable_exception(exc)) from exc
        error_text = readable_exception(exc)
        lowered = error_text.lower()
        if (
            payload.get("_artwork_mode") == "separate"
            and (
                "third variation" in lowered
                or "unsupported number of variations" in lowered
                or "custom variation" in lowered
                or "custom values" in lowered
                or "max_variations_supported" in lowered
            )
        ):
            add_event(
                product_id,
                "warning",
                "Etsy üçüncü custom Artwork Option değerini reddetti; Frame Option içinde Artwork fallback kullanılacak.",
                "etsy_draft",
                meta={"error": error_text},
            )
            payload = build_etsy_inventory_payload(product_id, settings, "combined")
            data = send_inventory(payload)
        else:
            raise RuntimeError(error_text) from exc
    api_payload = {key: value for key, value in payload.items() if not key.startswith("_")}
    return {
        "listing_id": str(listing_id),
        "products_count": len(data.get("products") or api_payload["products"]),
        "enabled_products_count": int(payload.get("_enabled_products_count") or 0),
        "price_on_property": data.get("price_on_property", payload["price_on_property"]),
        "quantity_on_property": data.get("quantity_on_property", payload["quantity_on_property"]),
        "sku_on_property": data.get("sku_on_property", payload["sku_on_property"]),
    }


def etsy_draft_listing_exists(listing_id: str, settings: dict) -> bool:
    listing_id = clean_text(listing_id)
    if not listing_id:
        return False
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings?state=draft&limit=100"
    )
    try:
        data = request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60)
    except Exception:
        return False
    return any(str(item.get("listing_id")) == listing_id for item in parse_results(data))


def fetch_etsy_listing_summary(listing_id: str, settings: dict) -> dict:
    settings = refresh_etsy_token(settings)
    url = f"https://api.etsy.com/v3/application/listings/{urllib.parse.quote(str(listing_id))}"
    return request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60)


def fetch_etsy_listing_inventory(listing_id: str, settings: dict) -> dict:
    settings = refresh_etsy_token(settings)
    url = f"https://api.etsy.com/v3/application/listings/{urllib.parse.quote(str(listing_id))}/inventory"
    return request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60)


def etsy_money_to_float(value) -> float:
    if isinstance(value, dict):
        amount = value.get("amount")
        divisor = value.get("divisor") or 100
        try:
            return round(float(amount or 0) / float(divisor or 100), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    return parse_money(value)


def inventory_property_value(product: dict, property_id: int | None = None, names: tuple[str, ...] = ()) -> str:
    for prop in product.get("property_values") or []:
        pid = prop.get("property_id")
        prop_name = clean_text(str(prop.get("property_name") or "")).lower()
        if property_id is not None and str(pid) == str(property_id):
            values = prop.get("values") or []
            return clean_text(str(values[0] if values else ""))
        if names and any(name in prop_name for name in names):
            values = prop.get("values") or []
            return clean_text(str(values[0] if values else ""))
    return ""


def normalize_imported_frame_label(value: str) -> str:
    text = clean_text(value)
    lowered = text.lower()
    if not lowered or lowered in {"no frame", "unframed", "digitaldownload", "digital download"}:
        return ""
    if "white" in lowered:
        return "White Wooden Framed"
    if "dark" in lowered and "wood" in lowered:
        return "Dark Wood Wooden Framed"
    if "black" in lowered:
        return "Black Wooden Framed"
    if "metal" in lowered:
        return "Metal Framed"
    if "wood" in lowered or "natural" in lowered:
        return "Wood Wooden Framed"
    return text


def ensure_variants_from_existing_etsy_listing(product_id: str, listing_id: str, settings: dict) -> dict:
    with db() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM variants WHERE product_id=? AND kind!='digital'",
            (product_id,),
        ).fetchone()
    if existing and int(existing["c"] or 0) > 0:
        return {"created": 0, "skipped": True, "reason": "local_variants_exist"}

    try:
        inventory = fetch_etsy_listing_inventory(listing_id, settings)
    except Exception as exc:
        add_event(product_id, "warning", "Mevcut Etsy ürünün varyasyonları okunamadı.", "etsy_draft", meta={"error": readable_exception(exc)})
        return {"created": 0, "skipped": True, "reason": readable_exception(exc)}

    sizes: dict[tuple[str, str], dict] = {}
    framed_prices: dict[tuple[str, str, str], float] = {}
    for product in inventory.get("products") or []:
        if product.get("is_deleted"):
            continue
        size_raw = inventory_property_value(product, ETSY_SIZE_PROPERTY_ID, ("size", "boyut"))
        frame_raw = inventory_property_value(product, ETSY_FORMAT_PROPERTY_ID, ("frame", "format"))
        haystack = f"{size_raw} {frame_raw}".lower()
        if "digitaldownload" in haystack or "digital download" in haystack:
            continue
        if not size_raw:
            continue
        orientation = extract_orientation({}, size_raw, frame_raw)
        size = clean_size_label(size_raw, orientation)
        if not size:
            continue
        offerings = [item for item in (product.get("offerings") or []) if not item.get("is_deleted")]
        offering = next((item for item in offerings if item.get("is_enabled")), offerings[0] if offerings else {})
        price = etsy_money_to_float(offering.get("price")) if offering else 0.0
        key = (canonical_etsy_size_label(size), orientation)
        current = sizes.get(key)
        if not current or (price and price < current["price"]):
            sizes[key] = {"size": canonical_etsy_size_label(size), "orientation": orientation, "price": price}
        frame_label = normalize_imported_frame_label(frame_raw)
        if frame_label:
            framed_prices[(key[0], key[1], frame_label)] = price

    if not sizes:
        add_event(product_id, "warning", "Mevcut Etsy ürününden boyut okunamadı; CSV yüklenmeli.", "etsy_draft")
        return {"created": 0, "skipped": True, "reason": "no_sizes"}

    ts = now_iso()
    created = 0
    ensure_digital_variant(product_id)
    with db() as conn:
        conn.execute("DELETE FROM variants WHERE product_id=? AND kind!='digital'", (product_id,))
        row_idx = 1
        for (_size_key, _orientation), data in sorted(sizes.items(), key=lambda item: (item[1]["price"], item[1]["size"].lower(), item[1]["orientation"])):
            size = data["size"]
            orientation = data["orientation"]
            base_price = float(data["price"] or settings.get("default_price_usd") or 14)
            for kind, frame in [("unframed", "")] + [("framed", frame) for frame in DEFAULT_FRAME_OPTIONS]:
                sale = framed_prices.get((size, orientation, frame), base_price) if kind == "framed" else base_price
                conn.execute(
                    """
                    INSERT INTO variants(id, product_id, kind, size_label, frame_label, orientation_label, sku, source_row,
                                         cost_usd, product_cost_usd, shipping_cost_usd, markup_percent,
                                         sale_price_usd, profit_usd, profit_margin_percent, quantity,
                                         visible, locked, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?, 100, ?, 1, 0, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        product_id,
                        kind,
                        size,
                        frame,
                        orientation,
                        variant_sku(product_id, kind, size, frame, row_idx),
                        row_idx,
                        round(float(sale or base_price), 2),
                        round(float(sale or base_price), 2),
                        int(settings["default_quantity"]),
                        ts,
                        ts,
                    ),
                )
                row_idx += 1
                created += 1
    add_event(
        product_id,
        "info",
        f"CSV yokken mevcut Etsy ürününden {len(sizes)} boyut çekildi ve frame seçenekleri eklendi.",
        "etsy_draft",
        meta={"listing_id": listing_id, "created_variants": created},
    )
    return {"created": created, "sizes": len(sizes), "skipped": False}


def import_existing_etsy_listing(payload: dict) -> dict:
    listing_input = clean_text(payload.get("listing_url") or payload.get("listing_id") or "")
    listing_id = extract_etsy_listing_id(listing_input)
    if not listing_id:
        raise ValueError("Etsy listing linkinden listing ID okunamadi.")

    with db() as conn:
        existing = conn.execute("SELECT id FROM products WHERE listing_id=?", (listing_id,)).fetchone()
    if existing:
        update_product(existing["id"], etsy_update_mode="inventory_only")
        ensure_variants_from_existing_etsy_listing(existing["id"], listing_id, get_settings())
        add_event(existing["id"], "info", "Mevcut Etsy listing panelde zaten bağlı.", "etsy_draft", meta={"listing_id": listing_id})
        return product_payload(existing["id"])

    settings = get_settings()
    title = f"Etsy listing {listing_id}"
    selection_name = ""
    shop_section_id = ""
    fetch_error = ""
    try:
        listing = fetch_etsy_listing_summary(listing_id, settings)
        title = clean_text(listing.get("title") or title)
        selection_name, shop_section_id = selection_from_listing(listing, etsy_shop_sections_by_id(settings))
    except Exception as exc:
        fetch_error = readable_exception(exc)

    product_id = str(uuid.uuid4())
    ts = now_iso()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO products(
                id, name, source_image_path, status, listing_id, selection_name,
                etsy_shop_section_id, etsy_update_mode, created_at, updated_at
            )
            VALUES(?, ?, '', 'idle', ?, ?, ?, 'inventory_only', ?, ?)
            """,
            (product_id, title[:180] or f"Etsy listing {listing_id}", listing_id, selection_name, shop_section_id, ts, ts),
        )
    ensure_steps(product_id)
    ensure_digital_variant(product_id)
    ensure_static_listing_images(product_id)
    if selection_name:
        ensure_selection_folder(selection_name)
    ensure_variants_from_existing_etsy_listing(product_id, listing_id, settings)
    add_event(
        product_id,
        "created",
        "Mevcut Etsy listing bağlandı; bu kayıt sadece varyasyon inventory günceller.",
        "etsy_draft",
        meta={"listing_id": listing_id, "listing_url": etsy_listing_url(listing_id)},
    )
    if fetch_error:
        add_event(product_id, "warning", "Listing başlığı Etsy API'den okunamadı; ID ile kayıt açıldı.", "etsy_draft", meta={"error": fetch_error})
    return product_payload(product_id)


def bulk_inventory_ready(settings: dict) -> tuple[bool, list[str]]:
    secrets = settings.get("_secrets", {})
    required = {
        "etsy_keystring": secrets.get("etsy_keystring"),
        "etsy_shared_secret": secrets.get("etsy_shared_secret"),
        "etsy_access_token": secrets.get("etsy_access_token"),
        "etsy_shop_id": secrets.get("etsy_shop_id"),
        "etsy_readiness_state_id": secrets.get("etsy_readiness_state_id"),
    }
    missing = [key for key, value in required.items() if not value]
    return len(missing) == 0, missing


def bulk_listing_ready(settings: dict) -> tuple[bool, list[str]]:
    secrets = settings.get("_secrets", {})
    required = {
        "etsy_keystring": secrets.get("etsy_keystring"),
        "etsy_shared_secret": secrets.get("etsy_shared_secret"),
        "etsy_access_token": secrets.get("etsy_access_token"),
        "etsy_shop_id": secrets.get("etsy_shop_id"),
    }
    missing = [key for key, value in required.items() if not value]
    return len(missing) == 0, missing


def normalize_selection_key(value: str) -> str:
    decoded = html.unescape(clean_text(value)).replace("’", "'")
    return re.sub(r"[^a-z0-9]+", "", decoded.casefold())


def canonical_selection_name(value: str) -> str:
    decoded = html.unescape(clean_text(value)).replace("’", "'")
    if not decoded:
        return ""
    for name in SELECTION_NAMES:
        if decoded.casefold() == name.casefold():
            return name
    key = normalize_selection_key(decoded)
    for name in SELECTION_NAMES:
        if normalize_selection_key(name) == key:
            return name
    return decoded


def listing_shop_section_id(listing: dict) -> str:
    return clean_text(str(listing.get("shop_section_id") or listing.get("shopSectionId") or ""))


def fetch_etsy_shop_sections(settings: dict) -> list[dict]:
    settings = refresh_etsy_token(settings)
    shop_id = clean_text(str(settings.get("_secrets", {}).get("etsy_shop_id") or ""))
    if not shop_id:
        return []
    url = f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(shop_id)}/sections"
    return parse_results(request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60))


def etsy_shop_sections_by_id(settings: dict) -> dict[str, str]:
    return {
        clean_text(str(item.get("shop_section_id") or "")): canonical_selection_name(str(item.get("title") or ""))
        for item in fetch_etsy_shop_sections(settings)
        if clean_text(str(item.get("shop_section_id") or ""))
    }


def selection_from_listing(listing: dict, sections_by_id: dict[str, str] | None = None) -> tuple[str, str]:
    section_id = listing_shop_section_id(listing)
    direct_title = clean_text(
        str(listing.get("shop_section_title") or listing.get("section_title") or listing.get("shopSectionTitle") or "")
    )
    title = direct_title or (sections_by_id or {}).get(section_id, "")
    return canonical_selection_name(title), section_id


def resolve_shop_section_id(settings: dict, selection_name: str) -> str:
    wanted = normalize_selection_key(selection_name)
    if not wanted:
        return ""
    for section_id, title in etsy_shop_sections_by_id(settings).items():
        if normalize_selection_key(title) == wanted:
            return section_id
    return ""


def listing_id_from_etsy_row(row: dict) -> str:
    return clean_text(str(row.get("listing_id") or row.get("listingId") or row.get("id") or ""))


def listing_title_from_etsy_row(row: dict, listing_id: str) -> str:
    title = clean_text(str(row.get("title") or row.get("name") or ""))
    return (title or f"Etsy listing {listing_id}")[:180]


def fetch_shop_listings_for_bulk(settings: dict, states: list[str]) -> tuple[list[dict], list[str]]:
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    shop_id = clean_text(str(secrets.get("etsy_shop_id") or ""))
    if not shop_id:
        raise ValueError("Etsy shop_id yok. Once Etsy ayar kesfini calistir.")
    states = [clean_text(state).lower() for state in states if clean_text(state)] or ["active"]
    listings: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for state in states:
        offset = 0
        limit = 100
        while True:
            params = urllib.parse.urlencode({"state": state, "limit": limit, "offset": offset, "includes": "Images"})
            url = f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(shop_id)}/listings?{params}"
            try:
                data = request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=90)
            except Exception as exc:
                fallback_params = urllib.parse.urlencode({"state": state, "limit": limit, "offset": offset})
                fallback_url = f"https://api.etsy.com/v3/application/shops/{urllib.parse.quote(shop_id)}/listings?{fallback_params}"
                try:
                    data = request_json(fallback_url, headers=etsy_api_headers(settings, oauth=True), timeout=90)
                except Exception:
                    errors.append(f"{state}: {readable_exception(exc)}")
                    break
            rows = parse_results(data)
            for row in rows:
                listing_id = listing_id_from_etsy_row(row)
                if listing_id and listing_id not in seen:
                    row["_panel_listing_state"] = state
                    seen.add(listing_id)
                    listings.append(row)
            total = int(data.get("count") or 0) if isinstance(data, dict) else 0
            if not rows or len(rows) < limit or (total and offset + limit >= total):
                break
            offset += limit
    return listings, errors


def best_etsy_image_url(image: dict) -> str:
    for key in ("url_fullxfull", "url_570xN", "url_300x300", "url_170x135", "url_75x75", "url"):
        value = clean_text(str(image.get(key) or ""))
        if value.startswith(("http://", "https://")):
            return value
    return ""


def best_etsy_video_url(video: dict) -> str:
    for key in ("video_url", "url", "src", "file_url"):
        value = clean_text(str(video.get(key) or ""))
        if value.startswith(("http://", "https://")):
            return value
    return ""


def listing_images_from_row(row: dict) -> list[dict]:
    images: list[dict] = []
    for key in ("Images", "images", "listing_images"):
        value = row.get(key)
        if isinstance(value, list):
            images.extend([item for item in value if isinstance(item, dict)])
    for key in ("MainImage", "main_image", "image"):
        value = row.get(key)
        if isinstance(value, dict):
            images.insert(0, value)
    return images


def fetch_etsy_listing_images(listing_id: str, settings: dict) -> list[dict]:
    settings = refresh_etsy_token(settings)
    url = f"https://api.etsy.com/v3/application/listings/{urllib.parse.quote(str(listing_id))}/images"
    return parse_results(request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60))


def fetch_etsy_listing_videos(listing_id: str, settings: dict) -> list[dict]:
    settings = refresh_etsy_token(settings)
    url = f"https://api.etsy.com/v3/application/listings/{urllib.parse.quote(str(listing_id))}/videos"
    return parse_results(request_json(url, headers=etsy_api_headers(settings, oauth=True), timeout=60))


def etsy_video_signature(video: dict) -> str:
    video_id = clean_text(str(video.get("id") or video.get("video_id") or ""))
    if video_id:
        return f"id:{video_id}"
    video_url = clean_text(str(video.get("url") or best_etsy_video_url(video) or ""))
    return f"url:{video_url}" if video_url else ""


def sync_etsy_listing_media(product_id: str, listing_id: str, settings: dict, listing: dict | None = None, fetch_remote: bool = False) -> dict:
    images = listing_images_from_row(listing or {})
    image_error = ""
    video_error = ""
    videos: list[dict] = []
    if fetch_remote or not images:
        try:
            images = fetch_etsy_listing_images(listing_id, settings)
        except Exception as exc:
            image_error = readable_exception(exc)
    if fetch_remote:
        try:
            videos = fetch_etsy_listing_videos(listing_id, settings)
        except Exception as exc:
            video_error = readable_exception(exc)

    if images:
        clear_assets(product_id, "etsy_listing_image")
        for idx, image in enumerate(images, start=1):
            url = best_etsy_image_url(image)
            if url:
                add_asset(product_id, "etsy_listing_image", f"Etsy image {idx}", url, idx, visible=1)
    if videos:
        clear_assets(product_id, "etsy_listing_video")
        for idx, video in enumerate(videos, start=1):
            url = best_etsy_video_url(video)
            if url:
                add_asset(product_id, "etsy_listing_video", f"Etsy video {idx}", url, idx, visible=1)
    return {"images": len(images), "videos": len(videos), "image_error": image_error, "video_error": video_error}


def upsert_bulk_inventory_product(listing: dict, sections_by_id: dict[str, str] | None = None) -> tuple[str, bool]:
    listing_id = listing_id_from_etsy_row(listing)
    if not listing_id:
        raise ValueError("Etsy listing ID okunamadi.")
    title = listing_title_from_etsy_row(listing, listing_id)
    listing_state = clean_text(
        str(listing.get("_panel_listing_state") or listing.get("state") or "")
    ).lower()
    selection_name, shop_section_id = selection_from_listing(listing, sections_by_id)
    ts = now_iso()
    with db() as conn:
        existing = conn.execute("SELECT id FROM products WHERE listing_id=?", (listing_id,)).fetchone()
        if existing:
            if sections_by_id is not None:
                conn.execute(
                    """
                    UPDATE products
                    SET name=?, etsy_listing_state=?, selection_name=?, etsy_shop_section_id=?,
                        etsy_update_mode='inventory_only', updated_at=?
                    WHERE id=?
                    """,
                    (title, listing_state, selection_name, shop_section_id, ts, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE products
                    SET name=?, etsy_listing_state=?, etsy_update_mode='inventory_only', updated_at=?
                    WHERE id=?
                    """,
                    (title, listing_state, ts, existing["id"]),
                )
            product_id = existing["id"]
            created = False
        else:
            product_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO products(
                    id, name, source_image_path, status, listing_id, etsy_listing_state, selection_name,
                    etsy_shop_section_id, etsy_update_mode, created_at, updated_at
                )
                VALUES(?, ?, '', 'idle', ?, ?, ?, ?, 'inventory_only', ?, ?)
                """,
                (product_id, title, listing_id, listing_state, selection_name, shop_section_id, ts, ts),
            )
            created = True
    ensure_steps(product_id)
    ensure_digital_variant(product_id)
    if selection_name:
        ensure_selection_folder(selection_name)
    return product_id, created


def save_bulk_csv_file(csv_file: dict, run_id: str, label: str) -> Path:
    if not isinstance(csv_file, dict) or not csv_file.get("data_url"):
        raise ValueError(f"{label} CSV dosyasi secilmedi.")
    filename = slugify_filename(csv_file.get("filename") or f"{label}.csv")
    target_dir = DATA / "bulk_csv" / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    _mime, raw = decode_data_url(csv_file["data_url"])
    target.write_bytes(raw)
    return target


def bulk_update_shop_variations(payload: dict) -> dict:
    raise RuntimeError(
        "Mevcut Etsy urun koruma kilidi aktif: toplu varyasyon/fiyat guncellemesi Etsy'ye yazamaz."
    )
    settings = get_settings()
    discover_etsy_shop_settings(settings)
    settings = get_settings()
    ok, missing = bulk_inventory_ready(settings)
    if not ok:
        raise ValueError("Toplu inventory icin eksik Etsy ayari: " + ", ".join(missing))

    framed_percent = float(payload.get("framed_percent") if payload.get("framed_percent") is not None else 51)
    unframed_percent = float(payload.get("unframed_percent") if payload.get("unframed_percent") is not None else 80)
    include_shipping = bool(payload.get("include_shipping_in_profit", settings["include_shipping_in_profit"]))
    pricing_formula = payload.get("pricing_formula") or settings["pricing_formula"]
    retail_multiplier = float(payload.get("gelato_retail_multiplier") or settings["gelato_retail_multiplier"] or 1)
    states = payload.get("states") if isinstance(payload.get("states"), list) else ["active"]
    states = [clean_text(str(item)).lower() for item in states if clean_text(str(item))] or ["active"]

    run_id = uuid.uuid4().hex
    framed_csv = save_bulk_csv_file(payload.get("framed_csv") or {}, run_id, "framed")
    unframed_csv = save_bulk_csv_file(payload.get("unframed_csv") or {}, run_id, "unframed")

    listings, listing_errors = fetch_shop_listings_for_bulk(settings, states)
    if not listings:
        raise ValueError("Etsy magazasinda guncellenecek listing bulunamadi. " + " | ".join(listing_errors[:3]))

    results = []
    created_products = 0
    updated_products = 0
    failed = 0
    for index, listing in enumerate(listings, start=1):
        listing_id = listing_id_from_etsy_row(listing)
        title = listing_title_from_etsy_row(listing, listing_id)
        try:
            product_id, created = upsert_bulk_inventory_product(listing)
            created_products += 1 if created else 0
            updated_products += 0 if created else 1
            update_product(product_id, status="running", current_step="etsy_draft", overall_progress=5, stop_requested=0)
            set_step(product_id, "etsy_draft", "running", 50)
            add_event(
                product_id,
                "info",
                f"Toplu varyasyon guncelleme basladi: {index}/{len(listings)}",
                "etsy_draft",
                meta={"listing_id": listing_id, "title": title},
            )
            parse_variants_csv(product_id, framed_csv, framed_percent, "framed", include_shipping, pricing_formula, retail_multiplier)
            parse_variants_csv(product_id, unframed_csv, unframed_percent, "unframed", include_shipping, pricing_formula, retail_multiplier)
            inventory = with_retry(
                product_id,
                "etsy_draft",
                settings,
                "etsy.bulkUpdateListingInventory.only",
                lambda pid=product_id, lid=listing_id: update_etsy_inventory(pid, lid, get_settings()),
            )
            add_event(
                product_id,
                "info",
                f"Toplu varyasyon/fiyat Etsy'ye yazildi: {inventory['enabled_products_count']} aktif / {inventory['products_count']} kombinasyon.",
                "etsy_draft",
                meta=inventory,
            )
            set_step(product_id, "etsy_draft", "done", 100)
            update_product(product_id, status="done", current_step="etsy_draft", overall_progress=100, etsy_fee_estimate_usd=0)
            results.append({"listing_id": listing_id, "title": title, "ok": True, "inventory": inventory})
        except Exception as exc:
            failed += 1
            error_text = readable_exception(exc)
            if listing_id:
                try:
                    product_id, _created = upsert_bulk_inventory_product(listing)
                    add_event(product_id, "error", error_text, "etsy_draft", meta={"listing_id": listing_id})
                    set_step(product_id, "etsy_draft", "error", error=error_text)
                    update_product(product_id, status="error", current_step="etsy_draft")
                except Exception:
                    pass
            results.append({"listing_id": listing_id, "title": title, "ok": False, "error": error_text})

    return {
        "ok": failed == 0,
        "total": len(listings),
        "success": len(listings) - failed,
        "failed": failed,
        "created_products": created_products,
        "updated_products": updated_products,
        "listing_errors": listing_errors,
        "results": results,
    }


def bulk_products_payload(page: int = 1, page_size: int = 4, search: str = "") -> dict:
    page_size = max(1, min(int(page_size or 4), 24))
    page = max(1, int(page or 1))
    search = clean_text(search)
    where = "WHERE COALESCE(p.listing_id, '') != '' AND LOWER(COALESCE(p.etsy_listing_state, ''))='active'"
    params: list[object] = []
    if search:
        where += " AND (p.name LIKE ? OR p.listing_id LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])
    with db() as conn:
        count_row = conn.execute(f"SELECT COUNT(*) AS count FROM products p {where}", params).fetchone()
        total = int(count_row["count"] or 0) if count_row else 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT p.*,
                   (SELECT path FROM assets a WHERE a.product_id=p.id AND a.kind='etsy_listing_image' ORDER BY sort_order LIMIT 1) AS thumb_path,
                   (SELECT COUNT(*) FROM variants v WHERE v.product_id=p.id) AS variant_count,
                   (SELECT COUNT(*) FROM assets a WHERE a.product_id=p.id AND a.kind='etsy_listing_image') AS image_count,
                   (SELECT COUNT(*) FROM assets a WHERE a.product_id=p.id AND a.kind='etsy_listing_video') AS video_count
            FROM products p
            {where}
            ORDER BY p.updated_at DESC, p.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    products = []
    for row in rows:
        item = row_to_dict(row)
        item["thumb_url"] = upload_url_for_path(item.pop("thumb_path", ""))
        item["etsy_listing_url"] = etsy_listing_url(str(item.get("listing_id") or ""))
        item["has_local_source"] = bool(item.get("source_image_path") and Path(str(item["source_image_path"])).exists())
        products.append(item)
    return {
        "products": products,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


def hydrate_bulk_product_cards(payload: dict) -> dict:
    """Fetch thumbnails only for the four visible cards that are not cached yet."""
    products = payload.get("products") or []
    targets = [
        item for item in products
        if item.get("listing_id") and not clean_text(str(item.get("thumb_url") or ""))
    ]
    if not targets:
        return payload

    settings = get_settings()

    def fetch_card(item: dict) -> tuple[str, list[dict], str]:
        try:
            return item["id"], fetch_etsy_listing_images(str(item["listing_id"]), settings), ""
        except Exception as exc:
            return item["id"], [], readable_exception(exc)

    fetched: dict[str, tuple[list[dict], str]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(targets)), thread_name_prefix="etsy-card") as pool:
        futures = [pool.submit(fetch_card, item) for item in targets]
        for future in as_completed(futures):
            product_id, images, error = future.result()
            fetched[product_id] = (images, error)

    for item in targets:
        images, error = fetched.get(item["id"], ([], ""))
        if images:
            clear_assets(item["id"], "etsy_listing_image")
            for index, image in enumerate(images, start=1):
                url = best_etsy_image_url(image)
                if url:
                    add_asset(item["id"], "etsy_listing_image", f"Etsy image {index}", url, index, visible=1)
                    if not item.get("thumb_url"):
                        item["thumb_url"] = url
            item["image_count"] = len(images)
        elif error:
            item["media_read_error"] = error
    return payload


def refresh_bulk_products(payload: dict) -> dict:
    settings = get_settings()
    discover_etsy_shop_settings(settings)
    settings = get_settings()
    ok, missing = bulk_listing_ready(settings)
    if not ok:
        raise ValueError("Etsy urunlerini cekmek icin eksik ayar: " + ", ".join(missing))
    # This workspace is intentionally limited to live listings. Ignoring caller
    # states prevents an inactive duplicate from becoming an edit target.
    states = ["active"]
    try:
        sections_by_id: dict[str, str] | None = etsy_shop_sections_by_id(settings)
    except Exception as exc:
        sections_by_id = None
        section_error = readable_exception(exc)
    else:
        section_error = ""
    listings, errors = fetch_shop_listings_for_bulk(settings, states)
    if section_error:
        errors.append("shop sections: " + section_error)
    created = 0
    updated = 0
    for listing in listings:
        product_id, was_created = upsert_bulk_inventory_product(listing, sections_by_id)
        created += 1 if was_created else 0
        updated += 0 if was_created else 1
        listing_id = clean_text(str(listing_id_from_etsy_row(listing)))
        try:
            sync_etsy_listing_media(product_id, listing_id, settings, listing=listing, fetch_remote=False)
        except Exception as exc:
            add_event(product_id, "warning", "Etsy urun gorseli okunamadi.", "etsy_draft", meta={"error": readable_exception(exc)})
    if not errors:
        active_listing_ids = {
            clean_text(str(listing_id_from_etsy_row(listing)))
            for listing in listings
            if clean_text(str(listing_id_from_etsy_row(listing)))
        }
        with db() as conn:
            if active_listing_ids:
                placeholders = ",".join("?" for _ in active_listing_ids)
                conn.execute(
                    f"""
                    UPDATE products
                    SET etsy_listing_state='inactive', updated_at=?
                    WHERE COALESCE(listing_id, '') != ''
                      AND listing_id NOT IN ({placeholders})
                    """,
                    [now_iso(), *sorted(active_listing_ids)],
                )
            else:
                conn.execute(
                    """
                    UPDATE products
                    SET etsy_listing_state='inactive', updated_at=?
                    WHERE COALESCE(listing_id, '') != ''
                    """,
                    (now_iso(),),
                )
    payload_out = bulk_products_payload()
    payload_out.update({"created": created, "updated": updated, "seen": len(listings), "errors": errors})
    return payload_out


def bulk_product_detail(product_id: str, refresh_remote: bool = True) -> dict:
    settings = get_settings()
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Urun bulunamadi.")
    if clean_text(product["etsy_listing_state"] or "").lower() != "active":
        raise ValueError("Bu Etsy ilani active degil; mevcut urunler panelinde duzenlenemez.")
    listing_id = clean_text(product["listing_id"] or "")
    listing_summary = {"state": product["etsy_listing_state"]}
    if listing_id and refresh_remote:
        listing_summary = fetch_etsy_listing_summary(listing_id, settings)
        remote_state = clean_text(str(listing_summary.get("state") or "")).lower()
        if remote_state != "active":
            update_product(product_id, etsy_listing_state=remote_state or "inactive")
            raise ValueError("Bu Etsy ilani artik active degil. Liste yenilendiginde panelden kaldirilacak.")
        try:
            selection_name, shop_section_id = selection_from_listing(listing_summary, etsy_shop_sections_by_id(settings))
            update_product(
                product_id,
                selection_name=selection_name,
                etsy_shop_section_id=shop_section_id,
            )
            if selection_name:
                ensure_selection_folder(selection_name)
        except Exception as exc:
            add_event(product_id, "warning", "Etsy selection kategorisi okunamadı.", "etsy_draft", meta={"error": readable_exception(exc)})
        sync_etsy_listing_media(product_id, listing_id, settings, fetch_remote=True)
        ensure_variants_from_existing_etsy_listing(product_id, listing_id, settings)
    payload = product_payload(product_id)
    if payload.get("products"):
        payload["products"][0]["etsy_listing"] = listing_summary
    return payload


def selection_mockup_root(settings: dict | None = None) -> Path:
    settings = settings or get_settings()
    return Path(clean_text(str(settings.get("selection_mockup_root") or DEFAULT_SETTINGS["selection_mockup_root"])))


def ensure_selection_library(settings: dict | None = None) -> Path:
    root = selection_mockup_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    for name in SELECTION_NAMES:
        folder = root / name
        (folder / "mockups").mkdir(parents=True, exist_ok=True)
        (folder / "video").mkdir(parents=True, exist_ok=True)
    guide = root / "KLASOR-KULLANIMI.txt"
    if not guide.exists():
        guide.write_text(
            "Her koleksiyonun mockups klasorune Photoshop PSD mockuplarini koyun.\n"
            "Video PSD dosyasini video klasorune koyun. Etsy bir listing icin tek video kullanir.\n"
            "Panel klasoru secince yalnizca o klasordeki sablonlari calistirir.\n",
            encoding="utf-8",
        )
    return root


def ensure_selection_folder(selection_name: str, settings: dict | None = None) -> Path:
    name = canonical_selection_name(selection_name)
    if not name or name in {".", ".."} or any(char in name for char in "\\/\0"):
        raise ValueError("Selection adı klasör için güvenli değil.")
    root = selection_mockup_root(settings).resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = (root / name).resolve()
    if root not in folder.parents:
        raise ValueError("Selection klasörü güvenli kökün dışında olamaz.")
    (folder / "mockups").mkdir(parents=True, exist_ok=True)
    (folder / "video").mkdir(parents=True, exist_ok=True)
    return folder


def mockup_order_key(value: str | Path) -> tuple[int, str]:
    return 0, Path(str(value)).stem.lower()


def is_primary_thumbnail_mockup(value: str | Path) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", Path(str(value)).stem.lower())
    expected = re.sub(r"[^a-z0-9]+", "", ETSY_PRIMARY_THUMBNAIL_STEM.lower())
    return expected in compact


def validate_primary_thumbnail_image(path: Path | str) -> None:
    from PIL import Image

    image_path = Path(path)
    if not image_path.is_file() or image_path.stat().st_size <= 0:
        raise RuntimeError("Etsy ana thumbnail gorseli eksik veya bos.")
    with Image.open(image_path) as image:
        width, height = image.size
    if width <= 0 or height <= 0:
        raise RuntimeError("Etsy ana thumbnail gorselinin boyutlari okunamadi.")



def selection_template_info(selection_name: str, settings: dict | None = None) -> dict:
    root = ensure_selection_library(settings)
    available = {path.name: path for path in root.iterdir() if path.is_dir()}
    folder = available.get(clean_text(selection_name))
    if not folder:
        raise ValueError("Selection klasoru bulunamadi.")

    mockup_subfolder = folder / "mockups"
    subfolder_psds = sorted(mockup_subfolder.glob("*.psd"), key=mockup_order_key) if mockup_subfolder.is_dir() else []
    mockup_folder = mockup_subfolder if subfolder_psds else folder
    static_psds = subfolder_psds or sorted(folder.glob("*.psd"), key=mockup_order_key)
    video_folder = folder / "video"
    video_psds = sorted(video_folder.glob("*.psd"), key=lambda path: path.name.lower()) if video_folder.is_dir() else []
    if not video_psds:
        video_psds = sorted(
            [path for path in folder.glob("*.psd") if re.search(r"video|vertical", path.stem, re.IGNORECASE)],
            key=lambda path: path.name.lower(),
        )
    if not video_psds:
        shared_video_psd = root.parent / "vertical.psd"
        if shared_video_psd.is_file() and shared_video_psd.stat().st_size > 0:
            video_psds = [shared_video_psd]
    video_psd = video_psds[0] if video_psds else None
    if mockup_folder == folder and video_psd:
        static_psds = [path for path in static_psds if path.resolve() != video_psd.resolve()]
    ready_videos = sorted(
        [path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in {".mp4", ".mov"}],
        key=lambda path: path.name.lower(),
    )
    return {
        "name": folder.name,
        "folder": str(folder),
        "mockup_folder": str(mockup_folder),
        "static_psds": [str(path) for path in static_psds],
        "video_psd": str(video_psd) if video_psd else "",
        "ready_videos": [str(path) for path in ready_videos],
        "ready": bool(static_psds),
    }


def selection_catalog_payload() -> dict:
    root = ensure_selection_library()
    names = list(SELECTION_NAMES)
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.is_dir() and not path.name.startswith('.') and path.name not in names:
            names.append(path.name)
    selections = []
    for name in names:
        info = selection_template_info(name)
        selections.append(
            {
                "name": name,
                "folder": info["folder"],
                "mockup_count": len(info["static_psds"]),
                "video_count": (1 if info["video_psd"] else 0) + len(info["ready_videos"]),
                "ready": info["ready"],
            }
        )
    return {"root": str(root), "selections": selections}


def open_selection_folder(selection_name: str) -> dict:
    info = selection_template_info(selection_name)
    folder = Path(info["folder"]).resolve()
    root = selection_mockup_root().resolve()
    if folder != root and root not in folder.parents:
        raise RuntimeError("Selection klasoru guvenli kok klasorunun disinda.")
    if os.name == "nt":
        os.startfile(str(folder))
    else:
        subprocess.Popen(["xdg-open", str(folder)])
    return {"opened": True, "name": info["name"], "folder": str(folder)}


def update_media_replacement_job(job_id: str, **fields) -> None:
    allowed = {
        "status", "stage", "progress", "source_path", "preview_json", "backup_json",
        "approval_token", "error", "applied_at",
    }
    fields = {key: value for key, value in fields.items() if key in allowed}
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{key}=?" for key in fields)
    with db() as conn:
        conn.execute(
            f"UPDATE media_replacement_jobs SET {sets} WHERE id=?",
            [*fields.values(), job_id],
        )


def media_replacement_job_payload(job_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM media_replacement_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("Medya onizleme isi bulunamadi.")
    item = row_to_dict(row)
    for key in ("preview_json", "backup_json"):
        try:
            item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
        except Exception:
            item[key.removesuffix("_json")] = {}
    preview = item.get("preview") or {}
    stale_preview = item.get("status") == "stale"
    if item.get("status") == "ready" and preview.get("manifest_version") != MEDIA_REPLACEMENT_MANIFEST_VERSION:
        stale_error = "Bu onizleme eski medya kurallariyla uretildi. Etsy'ye gonderilemez; yeniden uretmelisin."
        update_media_replacement_job(
            job_id,
            status="stale",
            stage="Onizleme eski - yeniden uret",
            progress=0,
            error=stale_error,
        )
        item.update(status="stale", stage="Onizleme eski - yeniden uret", progress=0, error=stale_error)
        stale_preview = True
    if stale_preview:
        item["preview"] = {}
        preview = {}
    for kind in ("images", "videos"):
        for asset in preview.get(kind) or []:
            asset["url"] = upload_url_for_path(asset.get("path"))
    if item.get("status") not in {"ready", "applying", "done"}:
        item.pop("approval_token", None)
    item["confirmation_text"] = f"{MEDIA_REPLACEMENT_CONFIRMATION_PREFIX} {item['listing_id']}"
    return item


def latest_media_replacement_job(product_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM media_replacement_jobs WHERE product_id=? ORDER BY created_at DESC LIMIT 1",
            (product_id,),
        ).fetchone()
    return media_replacement_job_payload(row["id"]) if row else None


def update_existing_mockup_queue_item(item_id: str, **fields) -> None:
    allowed = {
        "selection_name", "source_etsy_url", "source_rank", "extracted_path", "confidence",
        "status", "media_job_id", "error",
    }
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    values["updated_at"] = now_iso()
    sets = ", ".join(f"{key}=?" for key in values)
    with db() as conn:
        conn.execute(
            f"UPDATE existing_mockup_queue SET {sets} WHERE id=?",
            [*values.values(), item_id],
        )


def existing_mockup_queue_payload(batch_id: str = "", section: str = "") -> dict:
    where = []
    params: list[object] = []
    if batch_id:
        where.append("q.batch_id=?")
        params.append(batch_id)
    section_statuses = {
        "source": (
            "analyzing", "awaiting_source_approval", "source_approved",
            "producing", "paused", "error",
        ),
        "ready": ("ready_to_send", "applying"),
        "done": ("done",),
    }
    statuses = section_statuses.get(section)
    if statuses:
        where.append("q.status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT q.*,
                   (
                     SELECT a.path FROM assets a
                     WHERE a.product_id=q.product_id AND a.kind='etsy_listing_image'
                     ORDER BY a.sort_order, a.created_at LIMIT 1
                   ) AS current_thumb
            FROM existing_mockup_queue q
            {clause}
            ORDER BY q.created_at, q.id
            """,
            params,
        ).fetchall()
        counts = {
            row["status"]: int(row["count"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM existing_mockup_queue GROUP BY status"
            ).fetchall()
        }
    items = []
    for row in rows:
        item = row_to_dict(row)
        item["extracted_url"] = upload_url_for_path(item.get("extracted_path"))
        item["current_thumb_url"] = upload_url_for_path(item.pop("current_thumb", ""))
        media_job_id = clean_text(item.get("media_job_id") or "")
        if media_job_id:
            try:
                item["media_job"] = media_replacement_job_payload(media_job_id)
            except Exception:
                item["media_job"] = None
        items.append(item)
    return {"items": items, "counts": counts}


def _order_quad_points(points):
    import numpy as np

    points = np.asarray(points, dtype="float32").reshape(4, 2)
    ordered = np.zeros((4, 2), dtype="float32")
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[sums.argmin()]
    ordered[2] = points[sums.argmax()]
    ordered[1] = points[differences.argmin()]
    ordered[3] = points[differences.argmax()]
    return ordered


def _inset_quad(points, amount: float = 0.018):
    center = points.mean(axis=0)
    return points + (center - points) * amount


def _extract_vertical_frame_candidate(image, raw_edges, scale: float):
    import cv2
    import numpy as np

    height, width = raw_edges.shape[:2]
    raw_lines = cv2.HoughLinesP(
        raw_edges,
        1,
        np.pi / 360,
        threshold=45,
        minLineLength=max(120, int(min(width, height) * 0.1)),
        maxLineGap=max(24, int(min(width, height) * 0.03)),
    )
    verticals = []
    for line in ([] if raw_lines is None else raw_lines):
        x1, y1, x2, y2 = [float(value) for value in np.asarray(line).reshape(-1)[:4]]
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        length = float(np.hypot(x2 - x1, y2 - y1))
        if angle > 78 and length > height * 0.28:
            verticals.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2), length))
    if len(verticals) < 2:
        return None

    gray = cv2.cvtColor(
        cv2.resize(
            image,
            (width, height),
            interpolation=cv2.INTER_AREA,
        ),
        cv2.COLOR_BGR2GRAY,
    )
    image_area = float(width * height)
    candidates = []
    for left in verticals:
        for right in verticals:
            if left[0] >= right[0]:
                continue
            x_left, x_right = left[0], right[0]
            rect_width = x_right - x_left
            if rect_width < width * 0.18 or rect_width > width * 0.58:
                continue
            overlap = min(left[2], right[2]) - max(left[1], right[1])
            union = max(left[2], right[2]) - min(left[1], right[1])
            if union <= 0 or overlap < union * 0.62:
                continue
            y_top = min(left[1], right[1])
            y_bottom = max(left[2], right[2])
            rect_height = y_bottom - y_top
            ratio = rect_width / max(1.0, rect_height)
            area_ratio = rect_width * rect_height / image_area
            if ratio < 0.4 or ratio > 1.05 or area_ratio < 0.06 or area_ratio > 0.45:
                continue
            endpoint_score = max(
                0.0,
                1.0 - (abs(left[1] - right[1]) + abs(left[2] - right[2])) / (height * 0.35),
            )
            center_distance = np.linalg.norm(
                np.array([(x_left + x_right) / 2, (y_top + y_bottom) / 2])
                - np.array([width / 2, height / 2])
            )
            center_score = max(0.0, 1.0 - center_distance / np.linalg.norm([width / 2, height / 2]))
            ratio_score = max(0.0, 1.0 - abs(ratio - 0.72) / 0.38)
            roi_edges = raw_edges[
                max(0, int(y_top)):min(height, int(y_bottom)),
                max(0, int(x_left)):min(width, int(x_right)),
            ]
            roi_gray = gray[
                max(0, int(y_top)):min(height, int(y_bottom)),
                max(0, int(x_left)):min(width, int(x_right)),
            ]
            if not roi_edges.size or not roi_gray.size:
                continue
            texture_score = min(1.0, float(np.mean(roi_edges > 0)) / 0.13)
            variance_score = min(1.0, float(np.std(roi_gray)) / 65.0)
            score = (
                (overlap / union) * 18
                + endpoint_score * 12
                + center_score * 10
                + ratio_score * 17
                + texture_score * 22
                + variance_score * 12
                + area_ratio * 45
            )
            candidates.append(
                {
                    "score": float(score),
                    "area_ratio": float(area_ratio),
                    "box": (x_left, y_top, x_right, y_bottom),
                    "ratio": float(ratio),
                }
            )
    if not candidates:
        return None

    best = max(candidates, key=lambda item: item["score"])
    if best["score"] < 72:
        return None
    best_box = best["box"]
    best_center = np.array(
        [(best_box[0] + best_box[2]) / 2, (best_box[1] + best_box[3]) / 2],
        dtype="float32",
    )
    related = []
    for candidate in candidates:
        if candidate["score"] < best["score"] - 5:
            continue
        box = candidate["box"]
        center = np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], dtype="float32")
        if np.linalg.norm(center - best_center) > np.linalg.norm([width, height]) * 0.12:
            continue
        intersection_width = max(0.0, min(box[2], best_box[2]) - max(box[0], best_box[0]))
        intersection_height = max(0.0, min(box[3], best_box[3]) - max(box[1], best_box[1]))
        intersection = intersection_width * intersection_height
        best_area = (best_box[2] - best_box[0]) * (best_box[3] - best_box[1])
        if intersection / max(1.0, best_area) >= 0.5:
            related.append(candidate)
    if not related:
        related = [best]

    x_left = min(item["box"][0] for item in related)
    y_top = min(item["box"][1] for item in related)
    x_right = max(item["box"][2] for item in related)
    y_bottom = max(item["box"][3] for item in related)
    rect_width = x_right - x_left
    rect_height = y_bottom - y_top
    x_left += rect_width * 0.018
    x_right -= rect_width * 0.018
    y_top += rect_height * 0.018
    y_bottom -= rect_height * 0.052

    original_height, original_width = image.shape[:2]
    x1 = max(0, int(x_left / scale))
    y1 = max(0, int(y_top / scale))
    x2 = min(original_width, int(x_right / scale))
    y2 = min(original_height, int(y_bottom / scale))
    if x2 - x1 < 240 or y2 - y1 < 320:
        return None
    artwork = image[y1:y2, x1:x2]
    confidence = max(72.0, min(96.0, best["score"]))
    return artwork, confidence, {
        "method": "vertical_frame",
        "area_ratio": round((x_right - x_left) * (y_bottom - y_top) / image_area, 4),
        "ratio": round((x_right - x_left) / max(1.0, y_bottom - y_top), 4),
    }


def extract_artwork_from_mockup(source: Path, target: Path) -> tuple[float, dict]:
    import cv2
    import numpy as np

    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Etsy görseli açılamadı: {source.name}")
    original_height, original_width = image.shape[:2]
    scale = min(1.0, 1600.0 / max(original_width, original_height))
    working = cv2.resize(
        image,
        (max(1, int(original_width * scale)), max(1, int(original_height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    height, width = working.shape[:2]
    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    raw_edges = cv2.Canny(gray, 35, 120)
    frame_candidate = _extract_vertical_frame_candidate(image, raw_edges, scale)
    if frame_candidate:
        artwork, confidence, details = frame_candidate
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), artwork, [cv2.IMWRITE_PNG_COMPRESSION, 2]):
            raise RuntimeError("Cikarilan ana gorsel kaydedilemedi.")
        return confidence, details
    edges = raw_edges
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=2,
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(width * height)
    candidates = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        polygon = cv2.approxPolyDP(contour, 0.018 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        area = abs(cv2.contourArea(polygon))
        area_ratio = area / image_area
        if area_ratio < 0.055 or area_ratio > 0.82:
            continue
        points = _order_quad_points(polygon.reshape(4, 2))
        top = np.linalg.norm(points[1] - points[0])
        bottom = np.linalg.norm(points[2] - points[3])
        left = np.linalg.norm(points[3] - points[0])
        right = np.linalg.norm(points[2] - points[1])
        quad_width = max(top, bottom)
        quad_height = max(left, right)
        if min(quad_width, quad_height) < 150:
            continue
        ratio = quad_width / max(1.0, quad_height)
        if ratio < 0.35 or ratio > 2.6:
            continue
        rectangle_area = max(1.0, quad_width * quad_height)
        rectangularity = min(1.0, area / rectangle_area)
        center = points.mean(axis=0)
        center_distance = np.linalg.norm(center - np.array([width / 2, height / 2]))
        center_score = max(0.0, 1.0 - center_distance / np.linalg.norm([width / 2, height / 2]))
        border_gap = min(
            points[:, 0].min(),
            width - points[:, 0].max(),
            points[:, 1].min(),
            height - points[:, 1].max(),
        )
        whole_image_penalty = 0.25 if border_gap < min(width, height) * 0.018 else 0.0
        poster_ratio_score = max(0.0, 1.0 - abs(ratio - 0.72) / 0.5)
        score = (
            area_ratio * 52
            + rectangularity * 24
            + center_score * 16
            + poster_ratio_score * 12
            - whole_image_penalty * 100
        )
        candidates.append((score, points, area_ratio, ratio))

    if candidates:
        score, points, area_ratio, ratio = max(candidates, key=lambda item: item[0])
        points = _inset_quad(points, 0.025) / scale
        top_left, top_right, bottom_right, bottom_left = points
        out_width = int(max(np.linalg.norm(top_right - top_left), np.linalg.norm(bottom_right - bottom_left)))
        out_height = int(max(np.linalg.norm(bottom_left - top_left), np.linalg.norm(bottom_right - top_right)))
        destination = np.array(
            [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
            dtype="float32",
        )
        matrix = cv2.getPerspectiveTransform(points.astype("float32"), destination)
        artwork = cv2.warpPerspective(image, matrix, (out_width, out_height), flags=cv2.INTER_CUBIC)
        confidence = max(35.0, min(98.0, score))
        details = {"method": "perspective", "area_ratio": round(area_ratio, 4), "ratio": round(ratio, 4)}
    else:
        raw_lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold=max(55, int(min(width, height) * 0.055)),
            minLineLength=max(120, int(min(width, height) * 0.18)),
            maxLineGap=max(24, int(min(width, height) * 0.025)),
        )
        verticals = []
        horizontals = []
        for line in ([] if raw_lines is None else raw_lines):
            x1, y1, x2, y2 = [float(value) for value in np.asarray(line).reshape(-1)[:4]]
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            length = float(np.hypot(x2 - x1, y2 - y1))
            if angle > 78:
                verticals.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2), length))
            elif angle < 12:
                horizontals.append(((y1 + y2) / 2, min(x1, x2), max(x1, x2), length))

        def strongest_by_position(rows):
            buckets = {}
            for row in rows:
                bucket = int(row[0] // 14)
                if bucket not in buckets or row[3] > buckets[bucket][3]:
                    buckets[bucket] = row
            return sorted(buckets.values(), key=lambda row: row[3], reverse=True)[:22]

        verticals = strongest_by_position(verticals)
        horizontals = strongest_by_position(horizontals)
        best_line_candidate = None
        for left in verticals:
            for right in verticals:
                x_left, x_right = sorted((left[0], right[0]))
                rect_width = x_right - x_left
                if rect_width < width * 0.16 or rect_width > width * 0.72:
                    continue
                for top in horizontals:
                    for bottom in horizontals:
                        y_top, y_bottom = sorted((top[0], bottom[0]))
                        rect_height = y_bottom - y_top
                        if rect_height < height * 0.22 or rect_height > height * 0.9:
                            continue
                        area_ratio = rect_width * rect_height / image_area
                        ratio = rect_width / max(1.0, rect_height)
                        if area_ratio < 0.055 or area_ratio > 0.72 or ratio < 0.35 or ratio > 2.6:
                            continue
                        vertical_coverage = min(left[3], right[3]) / rect_height
                        horizontal_coverage = min(top[3], bottom[3]) / rect_width
                        if vertical_coverage < 0.3 or horizontal_coverage < 0.3:
                            continue
                        center_distance = np.linalg.norm(
                            np.array([(x_left + x_right) / 2, (y_top + y_bottom) / 2])
                            - np.array([width / 2, height / 2])
                        )
                        center_score = max(0.0, 1.0 - center_distance / np.linalg.norm([width / 2, height / 2]))
                        coverage_score = min(1.0, vertical_coverage) + min(1.0, horizontal_coverage)
                        poster_ratio_score = max(0.0, 1.0 - abs(ratio - 0.72) / 0.5)
                        score = area_ratio * 41 + center_score * 22 + coverage_score * 15 + poster_ratio_score * 14
                        candidate = (
                            score,
                            np.array([[x_left, y_top], [x_right, y_top], [x_right, y_bottom], [x_left, y_bottom]], dtype="float32"),
                            area_ratio,
                            ratio,
                        )
                        if best_line_candidate is None or candidate[0] > best_line_candidate[0]:
                            best_line_candidate = candidate
        if best_line_candidate:
            score, points, area_ratio, ratio = best_line_candidate
            points = _inset_quad(points, 0.03) / scale
            x_left, y_top = points[0]
            x_right, y_bottom = points[2]
            artwork = image[
                max(0, int(y_top)):min(original_height, int(y_bottom)),
                max(0, int(x_left)):min(original_width, int(x_right)),
            ]
            confidence = max(38.0, min(88.0, score))
            details = {"method": "line_rectangle", "area_ratio": round(area_ratio, 4), "ratio": round(ratio, 4)}
        else:
            ratio = original_width / max(1, original_height)
            if 0.38 <= ratio <= 2.5:
                artwork = image.copy()
            else:
                crop_width = min(original_width, int(original_height * 0.75))
                left = max(0, (original_width - crop_width) // 2)
                artwork = image[:, left:left + crop_width]
            confidence = 22.0
            details = {"method": "fallback", "area_ratio": 1.0, "ratio": round(ratio, 4)}
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), artwork, [cv2.IMWRITE_PNG_COMPRESSION, 2]):
        raise RuntimeError("Çıkarılan ana görsel kaydedilemedi.")
    return confidence, details


def extract_direct_artwork_candidate(source: Path, target: Path) -> tuple[float, dict] | None:
    import cv2
    import numpy as np

    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Etsy gorseli acilamadi: {source.name}")
    original_height, original_width = image.shape[:2]
    source_ratio = original_width / max(1.0, original_height)

    if 0.42 <= source_ratio <= 0.92:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), image, [cv2.IMWRITE_PNG_COMPRESSION, 2]):
            raise RuntimeError("Dogrudan ana gorsel kaydedilemedi.")
        return 96.0, {
            "method": "direct_portrait",
            "area_ratio": 1.0,
            "ratio": round(source_ratio, 4),
        }

    scale = min(1.0, 1600.0 / max(original_width, original_height))
    working = cv2.resize(
        image,
        (max(1, int(original_width * scale)), max(1, int(original_height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    height, width = working.shape[:2]
    patch = max(12, int(min(width, height) * 0.055))
    corner_blocks = [
        working[:patch, :patch],
        working[:patch, -patch:],
        working[-patch:, :patch],
        working[-patch:, -patch:],
    ]
    corner_medians = np.asarray(
        [np.median(block.reshape(-1, 3), axis=0) for block in corner_blocks],
        dtype=np.float32,
    )
    corner_pixels = np.concatenate([block.reshape(-1, 3) for block in corner_blocks], axis=0)
    corner_spread = float(np.max(np.linalg.norm(corner_medians - corner_medians.mean(axis=0), axis=1)))
    corner_noise = float(np.mean(corner_pixels.std(axis=0)))
    if corner_spread > 18.0 or corner_noise > 18.0:
        return None

    lab = cv2.cvtColor(working, cv2.COLOR_BGR2LAB).astype(np.float32)
    background_lab = np.median(
        np.concatenate(
            [
                lab[:patch, :patch].reshape(-1, 3),
                lab[:patch, -patch:].reshape(-1, 3),
                lab[-patch:, :patch].reshape(-1, 3),
                lab[-patch:, -patch:].reshape(-1, 3),
            ],
            axis=0,
        ),
        axis=0,
    )
    color_distance = np.linalg.norm(lab - background_lab, axis=2)
    mask = (color_distance > 14.0).astype(np.uint8) * 255
    kernel_size = max(7, int(min(width, height) * 0.012))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(width * height)
    candidates = []
    for contour in contours:
        contour_area = abs(cv2.contourArea(contour))
        x, y, rect_width, rect_height = cv2.boundingRect(contour)
        box_area = float(rect_width * rect_height)
        area_ratio = box_area / image_area
        ratio = rect_width / max(1.0, rect_height)
        if area_ratio < 0.2 or area_ratio > 0.9:
            continue
        if ratio < 0.38 or ratio > 1.08:
            continue
        fill_ratio = contour_area / max(1.0, box_area)
        if fill_ratio < 0.45:
            continue
        center_distance = np.linalg.norm(
            np.array([x + rect_width / 2, y + rect_height / 2])
            - np.array([width / 2, height / 2])
        )
        center_score = max(0.0, 1.0 - center_distance / np.linalg.norm([width / 2, height / 2]))
        ratio_score = max(0.0, 1.0 - abs(ratio - 0.72) / 0.42)
        score = area_ratio * 45 + fill_ratio * 20 + center_score * 20 + ratio_score * 15
        candidates.append((score, x, y, rect_width, rect_height, area_ratio, ratio))
    if not candidates:
        return None

    score, x, y, rect_width, rect_height, area_ratio, ratio = max(candidates, key=lambda row: row[0])
    margin = max(1, int(min(rect_width, rect_height) * 0.004))
    x1 = max(0, int((x + margin) / scale))
    y1 = max(0, int((y + margin) / scale))
    x2 = min(original_width, int((x + rect_width - margin) / scale))
    y2 = min(original_height, int((y + rect_height - margin) / scale))
    if x2 - x1 < 240 or y2 - y1 < 240:
        return None
    artwork = image[y1:y2, x1:x2]
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), artwork, [cv2.IMWRITE_PNG_COMPRESSION, 2]):
        raise RuntimeError("Dogrudan ana gorsel kaydedilemedi.")
    confidence = max(88.0, min(98.0, score))
    return confidence, {
        "method": "direct_centered_poster",
        "area_ratio": round(area_ratio, 4),
        "ratio": round(ratio, 4),
        "corner_noise": round(corner_noise, 2),
    }


def analyze_existing_mockup_item(item_id: str) -> None:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item or item["status"] != "analyzing":
        return
    while not bulk_analysis_semaphore.acquire(timeout=0.5):
        if existing_queue_item_cancelled(item_id):
            return
    try:
        settings = refresh_etsy_token(get_settings())
        images: list[dict] = []
        for attempt in range(1, 5):
            if existing_queue_item_cancelled(item_id):
                return
            try:
                images = sorted(
                    fetch_etsy_listing_images(item["listing_id"], settings),
                    key=lambda row: int(row.get("rank") or 0),
                )
                break
            except Exception as exc:
                error_text = readable_exception(exc).lower()
                if attempt >= 4 or not any(
                    marker in error_text
                    for marker in ("http error 409", "http error 429", "too many requests", "being edited by another process")
                ):
                    raise
                time.sleep(attempt * 3)
        if not images:
            raise RuntimeError("Etsy ürününde incelenecek görsel bulunamadı.")
        item_root = product_upload_dir(item["product_id"]) / "bulk_mockups" / item["batch_id"] / item_id
        selected: tuple[float, str, int, Path, dict] | None = None

        # Rank 2 is usually the clean poster. It is accepted only when the
        # poster can be isolated from a uniform outer background.
        if len(images) >= 2:
            image = images[1]
            url = best_etsy_image_url(image)
            if url:
                rank = int(image.get("rank") or 2)
                source = item_root / "etsy" / f"{rank:02d}.jpg"
                extracted = item_root / "candidates" / f"{rank:02d}-direct.png"
                download_remote_file(url, source)
                direct_result = extract_direct_artwork_candidate(source, extracted)
                if direct_result:
                    confidence, details = direct_result
                    selected = (confidence, url, rank, extracted, details)

        # If rank 2 is another room mockup, inspect only the frontal frame in
        # rank 1. Later room mockups must never win by an accidental rectangle.
        if selected is None:
            image = images[0]
            url = best_etsy_image_url(image)
            if not url:
                raise RuntimeError("Etsy birinci gorsel URL'si bulunamadi.")
            rank = int(image.get("rank") or 1)
            source = item_root / "etsy" / f"{rank:02d}.jpg"
            extracted = item_root / "candidates" / f"{rank:02d}-frame.png"
            download_remote_file(url, source)
            confidence, details = extract_artwork_from_mockup(source, extracted)
            if details.get("method") == "fallback" or confidence < 38:
                raise RuntimeError(
                    "Ikinci gorselde dogrudan poster, birinci gorselde guvenilir cerceve siniri bulunamadi."
                )
            selected = (confidence, url, rank, extracted, details)
        if selected is None:
            raise RuntimeError("Mockuplardan ana görsel çıkarılamadı.")
        confidence, url, rank, extracted, _details = selected
        final_path = item_root / "approved-source.png"
        shutil.copy2(extracted, final_path)
        with db() as conn:
            current = conn.execute(
                "SELECT status FROM existing_mockup_queue WHERE id=?",
                (item_id,),
            ).fetchone()
        if not current or current["status"] != "analyzing":
            return
        update_existing_mockup_queue_item(
            item_id,
            source_etsy_url=url,
            source_rank=rank,
            extracted_path=str(final_path.resolve()),
            confidence=round(confidence, 1),
            status="awaiting_source_approval",
            error=None,
        )
    except Exception as exc:
        with db() as conn:
            current = conn.execute(
                "SELECT status FROM existing_mockup_queue WHERE id=?",
                (item_id,),
            ).fetchone()
        if not current or current["status"] != "analyzing":
            return
        update_existing_mockup_queue_item(
            item_id,
            status="error",
            error=readable_exception(exc),
        )
    finally:
        bulk_analysis_semaphore.release()


def analyze_existing_mockup_batch(batch_id: str) -> None:
    with db() as conn:
        item_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM existing_mockup_queue WHERE batch_id=? AND status='analyzing' ORDER BY created_at",
                (batch_id,),
            ).fetchall()
        ]
    for item_id in item_ids:
        analyze_existing_mockup_item(item_id)


def start_existing_mockup_batch(payload: dict) -> dict:
    product_ids = payload.get("product_ids")
    if not isinstance(product_ids, list):
        raise ValueError("Toplu işlem için ürün seçmelisin.")
    product_ids = list(dict.fromkeys(clean_text(str(item)) for item in product_ids if clean_text(str(item))))
    if not product_ids:
        raise ValueError("En az bir ürün seçmelisin.")
    selection_name = canonical_selection_name(clean_text(payload.get("selection_name") or ""))
    template = selection_template_info(selection_name)
    if not template["ready"]:
        raise ValueError(f"{selection_name} klasöründe PSD bulunamadı.")
    placeholders = ",".join("?" for _ in product_ids)
    with db() as conn:
        products = conn.execute(
            f"""
            SELECT id, listing_id, name, etsy_listing_state
            FROM products WHERE id IN ({placeholders})
            """,
            product_ids,
        ).fetchall()
    by_id = {row["id"]: row for row in products}
    missing = [item for item in product_ids if item not in by_id]
    if missing:
        raise ValueError("Seçilen ürünlerden biri panelde bulunamadı.")
    inactive = [row["name"] for row in products if clean_text(row["etsy_listing_state"]).lower() != "active"]
    if inactive:
        raise ValueError("Yalnızca active Etsy ürünleri toplu işleme alınabilir.")
    batch_id = uuid.uuid4().hex
    ts = now_iso()
    with db() as conn:
        for product_id in product_ids:
            row = by_id[product_id]
            conn.execute(
                """
                INSERT INTO existing_mockup_queue(
                    id, batch_id, product_id, listing_id, product_name, selection_name,
                    status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, 'analyzing', ?, ?)
                """,
                (
                    uuid.uuid4().hex, batch_id, product_id, clean_text(row["listing_id"]),
                    clean_text(row["name"]), selection_name, ts, ts,
                ),
            )
    threading.Thread(
        target=analyze_existing_mockup_batch,
        args=(batch_id,),
        daemon=True,
        name=f"bulk-analyze-{batch_id[:8]}",
    ).start()
    return existing_mockup_queue_payload(batch_id=batch_id)


def review_existing_mockup_source(item_id: str, payload: dict) -> dict:
    action = clean_text(payload.get("action") or "").lower()
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Toplu mockup ürünü bulunamadı.")
    if item["status"] != "awaiting_source_approval":
        raise ValueError("Bu ürün ana görsel onayı beklemiyor.")
    if action == "approve":
        source = assert_artwork_source_safe(item["extracted_path"], item["product_id"])
        if not source:
            raise RuntimeError("Çıkarılan ana görsel bulunamadı.")
        update_existing_mockup_queue_item(item_id, status="source_approved", error=None)
        ensure_bulk_mockup_worker()
    elif action == "reject":
        update_existing_mockup_queue_item(item_id, status="rejected", error=None)
    elif action != "hold":
        raise ValueError("Geçersiz ana görsel onayı.")
    return existing_mockup_queue_payload(batch_id=item["batch_id"])


def stop_media_job_for_queue_item(item: sqlite3.Row, reason: str) -> None:
    media_job_id = clean_text(item["media_job_id"] or "")
    if not media_job_id:
        return
    with db() as conn:
        media_job = conn.execute(
            "SELECT status FROM media_replacement_jobs WHERE id=?",
            (media_job_id,),
        ).fetchone()
    if media_job and media_job["status"] in {"queued", "running"}:
        update_media_replacement_job(
            media_job_id,
            status="error",
            stage="Kullanıcı tarafından durduruldu",
            error=reason,
        )


def pause_existing_mockup_queue_item(item_id: str) -> dict:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Toplu mockup ürünü bulunamadı.")
    if item["status"] in {"applying", "done"}:
        raise RuntimeError("Etsy aktarımı başlamış veya tamamlanmış ürün durdurulamaz.")
    was_producing = item["status"] == "producing"
    stop_media_job_for_queue_item(item, "Ürün üretimi kullanıcı tarafından durduruldu.")
    update_existing_mockup_queue_item(item_id, status="paused", error=None)
    if was_producing:
        terminate_photoshop_processes()
    return existing_mockup_queue_payload(batch_id=item["batch_id"])


def resume_existing_mockup_queue_item(item_id: str) -> dict:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
        media_job = conn.execute(
            "SELECT status, preview_json FROM media_replacement_jobs WHERE id=?",
            (clean_text(item["media_job_id"] or "") if item else "",),
        ).fetchone() if item else None
    if not item:
        raise ValueError("Toplu mockup ürünü bulunamadı.")
    if item["status"] not in {"paused", "error"}:
        raise ValueError("Yalnızca durdurulmuş veya hata alan ürün devam ettirilebilir.")

    preview = {}
    if media_job:
        try:
            preview = json.loads(media_job["preview_json"] or "{}")
        except Exception:
            preview = {}
    transient_apply_error = any(
        marker in clean_text(item["error"] or "").lower()
        for marker in ("http error 409", "http error 429", "too many requests", "being edited by another process")
    )
    if transient_apply_error and preview.get("images") and preview.get("approved_image_ids"):
        update_media_replacement_job(
            clean_text(item["media_job_id"]),
            status="ready",
            stage="Geçici Etsy hatası sonrası yeniden onay bekleniyor",
            progress=100,
            error=None,
        )
        update_existing_mockup_queue_item(item_id, status="ready_to_send", error=None)
    elif clean_text(item["extracted_path"] or "") and Path(item["extracted_path"]).is_file():
        update_existing_mockup_queue_item(
            item_id,
            status="source_approved",
            media_job_id="",
            error=None,
        )
        ensure_bulk_mockup_worker()
    else:
        update_existing_mockup_queue_item(item_id, status="analyzing", media_job_id="", error=None)
        threading.Thread(
            target=analyze_existing_mockup_item,
            args=(item_id,),
            daemon=True,
            name=f"bulk-analyze-retry-{item_id[:8]}",
        ).start()
    return existing_mockup_queue_payload(batch_id=item["batch_id"])


def replace_existing_mockup_source(item_id: str, payload: dict) -> dict:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Toplu mockup ürünü bulunamadı.")
    if item["status"] in {"applying", "done"}:
        raise RuntimeError("Etsy aktarımı başlamış veya tamamlanmış üründe kaynak değiştirilemez.")

    selection_name = canonical_selection_name(
        clean_text(payload.get("selection_name") or item["selection_name"] or "")
    )
    template = selection_template_info(selection_name)
    if not template["ready"]:
        raise ValueError(f"{selection_name} klasöründe PSD bulunamadı.")
    image_file = payload.get("image_file") or {}
    if not isinstance(image_file, dict) or not image_file.get("data_url"):
        raise ValueError("Yeni ana görsel dosyası seçilmelidir.")

    stop_media_job_for_queue_item(item, "Ana görsel kullanıcı tarafından değiştirildi.")
    if item["status"] == "producing":
        terminate_photoshop_processes()
    saved = save_uploaded_data(
        item["product_id"],
        image_file.get("filename") or "manual-source.png",
        image_file["data_url"],
        f"bulk_mockups/{item['batch_id']}/{item_id}/manual",
    )
    source = assert_artwork_source_safe(saved, item["product_id"])
    update_existing_mockup_queue_item(
        item_id,
        selection_name=selection_name,
        source_etsy_url="",
        source_rank=0,
        extracted_path=str(source),
        confidence=100,
        status="awaiting_source_approval",
        media_job_id="",
        error=None,
    )
    return existing_mockup_queue_payload(batch_id=item["batch_id"])


def delete_existing_mockup_queue_item(item_id: str) -> dict:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        return {"ok": True}
    if item["status"] in {"applying", "done"}:
        raise RuntimeError("Etsy aktarımı başlamış veya tamamlanmış kayıt panelden silinemez.")
    stop_media_job_for_queue_item(item, "Ürün toplu işlem listesinden silindi.")
    if item["status"] == "producing":
        terminate_photoshop_processes()
    with db() as conn:
        conn.execute("DELETE FROM existing_mockup_queue WHERE id=?", (item_id,))
    return {"ok": True, "batch_id": item["batch_id"]}


def pause_all_existing_mockups() -> dict:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM existing_mockup_queue
            WHERE status IN ('analyzing', 'source_approved', 'producing')
            """
        ).fetchall()
    should_terminate = any(row["status"] == "producing" for row in rows)
    for row in rows:
        stop_media_job_for_queue_item(row, "Toplu üretim kullanıcı tarafından durduruldu.")
        update_existing_mockup_queue_item(row["id"], status="paused", error=None)
    if should_terminate:
        terminate_photoshop_processes()
    return existing_mockup_queue_payload()


def resume_all_existing_mockups() -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM existing_mockup_queue WHERE status='paused' ORDER BY created_at, id"
        ).fetchall()
    for row in rows:
        next_status = (
            "source_approved"
            if clean_text(row["extracted_path"] or "") and Path(row["extracted_path"]).is_file()
            else "analyzing"
        )
        update_existing_mockup_queue_item(
            row["id"],
            status=next_status,
            media_job_id="",
            error=None,
        )
        if next_status == "analyzing":
            threading.Thread(
                target=analyze_existing_mockup_item,
                args=(row["id"],),
                daemon=True,
                name=f"bulk-analyze-resume-{row['id'][:8]}",
            ).start()
    ensure_bulk_mockup_worker()
    return existing_mockup_queue_payload()


def bulk_mockup_worker() -> None:
    global bulk_mockup_thread
    retry_counts: dict[str, int] = {}
    try:
        while True:
            with db() as conn:
                item = conn.execute(
                    """
                    SELECT * FROM existing_mockup_queue
                    WHERE status='source_approved'
                    ORDER BY created_at, id LIMIT 1
                    """
                ).fetchone()
            if not item:
                return
            item_id = item["id"]
            try:
                with db() as conn:
                    claimed = conn.execute(
                        """
                        UPDATE existing_mockup_queue
                        SET status='producing', error=NULL, updated_at=?
                        WHERE id=? AND status='source_approved'
                        """,
                        (now_iso(), item_id),
                    ).rowcount
                if not claimed:
                    continue
                media_job = start_existing_media_preview(
                    item["product_id"],
                    {
                        "selection_name": item["selection_name"],
                        "video_policy": "preserve_or_create",
                        "skip_inventory_update": True,
                        "skip_digital_delivery": True,
                        "bulk_queue_item_id": item_id,
                    },
                    trusted_source_path=Path(item["extracted_path"]),
                )
                update_existing_mockup_queue_item(item_id, media_job_id=media_job["id"])
                while True:
                    current = media_replacement_job_payload(media_job["id"])
                    if current["status"] == "ready":
                        update_existing_mockup_queue_item(item_id, status="ready_to_send", error=None)
                        retry_counts.pop(item_id, None)
                        break
                    if current["status"] in {"error", "stale"}:
                        raise RuntimeError(current.get("error") or "Photoshop önizlemesi tamamlanamadı.")
                    time.sleep(2)
            except Exception as exc:
                with db() as conn:
                    current_item = conn.execute(
                        "SELECT status FROM existing_mockup_queue WHERE id=?",
                        (item_id,),
                    ).fetchone()
                if not current_item or current_item["status"] in {"paused", "rejected"}:
                    retry_counts.pop(item_id, None)
                    continue
                attempt = retry_counts.get(item_id, 0) + 1
                retry_counts[item_id] = attempt
                error_text = readable_exception(exc)
                transient_error = any(
                    marker in error_text.lower()
                    for marker in (
                        "http error 409",
                        "http error 429",
                        "too many requests",
                        "being edited by another process",
                        "getaddrinfo failed",
                    )
                )
                if transient_error and attempt < 3:
                    update_existing_mockup_queue_item(
                        item_id,
                        status="source_approved",
                        media_job_id="",
                        error=f"Geçici hata; otomatik deneme {attempt + 1}/3 hazırlanıyor: {error_text}",
                    )
                    time.sleep(min(30, attempt * 8))
                else:
                    update_existing_mockup_queue_item(item_id, status="error", error=error_text)
    finally:
        with bulk_mockup_lock:
            bulk_mockup_thread = None


def ensure_bulk_mockup_worker() -> None:
    global bulk_mockup_thread
    with bulk_mockup_lock:
        if bulk_mockup_thread and bulk_mockup_thread.is_alive():
            return
        bulk_mockup_thread = threading.Thread(
            target=bulk_mockup_worker,
            daemon=True,
            name="bulk-existing-mockup-worker",
        )
        bulk_mockup_thread.start()


def apply_existing_mockup_queue_item(item_id: str) -> dict:
    with db() as conn:
        item = conn.execute("SELECT * FROM existing_mockup_queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Hazır ürün bulunamadı.")
    if item["status"] != "ready_to_send" or not clean_text(item["media_job_id"]):
        raise ValueError("Yalnızca Etsy onayı bekleyen hazır ürün gönderilebilir.")
    media_job = media_replacement_job_payload(item["media_job_id"])
    assets = [*(media_job.get("preview", {}).get("images") or []), *(media_job.get("preview", {}).get("videos") or [])]
    selected_ids = [clean_text(str(asset.get("id") or "")) for asset in assets if clean_text(str(asset.get("id") or ""))]
    result = begin_existing_media_apply(
        item["product_id"],
        item["media_job_id"],
        {
            "approval_token": media_job["approval_token"],
            "confirmation": media_job["confirmation_text"],
            "selected_asset_ids": selected_ids,
        },
    )
    update_existing_mockup_queue_item(item_id, status="applying", error=None)
    return result


def resume_existing_mockup_queue() -> None:
    with db() as conn:
        producing = conn.execute(
            "SELECT id, media_job_id FROM existing_mockup_queue WHERE status='producing'"
        ).fetchall()
        ready_items = conn.execute(
            "SELECT id, media_job_id FROM existing_mockup_queue WHERE status='ready_to_send'"
        ).fetchall()
        analyzing_batches = [
            row["batch_id"]
            for row in conn.execute(
                "SELECT DISTINCT batch_id FROM existing_mockup_queue WHERE status='analyzing'"
            ).fetchall()
        ]
    for row in ready_items:
        media_job_id = clean_text(row["media_job_id"] or "")
        try:
            media_job = media_replacement_job_payload(media_job_id) if media_job_id else None
        except Exception:
            media_job = None
        if not media_job or media_job.get("status") != "ready":
            update_existing_mockup_queue_item(
                row["id"],
                status="source_approved",
                media_job_id="",
                error="Eski onizleme otomatik olarak video ve medya uretim sirasina geri alindi.",
            )
    for row in producing:
        media_job_id = clean_text(row["media_job_id"] or "")
        if media_job_id:
            try:
                media_job = media_replacement_job_payload(media_job_id)
                if media_job["status"] == "ready":
                    update_existing_mockup_queue_item(row["id"], status="ready_to_send")
                    continue
                if media_job["status"] in {"queued", "running"}:
                    update_media_replacement_job(
                        media_job_id,
                        status="error",
                        stage="Sunucu yeniden başladı - toplu kuyruk yeniden üretecek",
                        error="Yarım kalan Photoshop önizlemesi güvenli biçimde yeniden sıraya alındı.",
                    )
            except Exception:
                pass
        update_existing_mockup_queue_item(row["id"], status="source_approved")
    for batch_id in analyzing_batches:
        threading.Thread(
            target=analyze_existing_mockup_batch,
            args=(batch_id,),
            daemon=True,
            name=f"bulk-analyze-resume-{batch_id[:8]}",
        ).start()
    ensure_bulk_mockup_worker()


def image_fingerprint(path: Path | str) -> str:
    from PIL import Image, ImageOps

    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(image.getdata())
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{bits:016x}"


def fingerprint_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def build_existing_media_preview(
    product_id: str,
    job_root: Path,
    mockup_paths: list[str],
    video_paths: list[str],
    main_source_path: str | Path,
) -> dict:
    fixed_assets = protected_static_assets(product_id)
    fixed_hashes = {clean_text(row["content_sha256"]) for row in fixed_assets}
    fixed_fingerprints = {image_fingerprint(Path(row["path"])) for row in fixed_assets}
    generated_limit = ETSY_MAX_IMAGE_COUNT - len(fixed_assets) - 1
    images: list[dict] = []
    seen_hashes = set(fixed_hashes)
    seen_fingerprints: list[str] = []

    for path_value in sorted(mockup_paths, key=mockup_order_key):
        if len(images) >= generated_limit:
            break
        path = Path(path_value).resolve()
        if not path.is_file() or path.stat().st_size <= 0 or job_root.resolve() not in path.parents:
            raise RuntimeError("Photoshop çıktısı güvenli önizleme klasörünün dışında veya boş.")
        digest = file_sha256(path)
        fingerprint = image_fingerprint(path)
        if digest in seen_hashes:
            continue
        if any(fingerprint_distance(fingerprint, fixed) <= 3 for fixed in fixed_fingerprints):
            raise RuntimeError("Photoshop çıktılarından biri korunan sabit bilgi görseliyle aynı; işlem durduruldu.")
        if any(fingerprint_distance(fingerprint, seen) <= 1 for seen in seen_fingerprints):
            continue
        seen_hashes.add(digest)
        seen_fingerprints.append(fingerprint)
        primary_thumbnail = not images
        if primary_thumbnail:
            validate_primary_thumbnail_image(path)
        images.append(
            {
                "id": f"mockup-{digest[:16]}",
                "label": path.stem,
                "path": str(path),
                "selected": True,
                "protected": False,
                "required": primary_thumbnail,
                "role": "primary_thumbnail" if primary_thumbnail else "mockup",
                "sha256": digest,
                "fingerprint": fingerprint,
            }
        )
    if not images:
        raise RuntimeError("Photoshop önizlemesi geçerli mockup üretmedi; Etsy'ye hiçbir şey gönderilmedi.")

    primary_thumbnails = [item for item in images if item.get("role") == "primary_thumbnail"]
    if len(primary_thumbnails) != 1 or images[0] is not primary_thumbnails[0]:
        raise RuntimeError(
            f"{ETSY_PRIMARY_THUMBNAIL_STEM}.psd ciktisi bulunamadi veya ilk sirada degil; "
            "Etsy thumbnail yazmasi durduruldu."
        )

    source = assert_artwork_source_safe(Path(main_source_path), product_id)
    main_dir = job_root / "preview" / "main"
    main_dir.mkdir(parents=True, exist_ok=True)
    main_target = main_dir / f"main-artwork{source.suffix.lower() or '.png'}"
    shutil.copy2(source, main_target)
    main_digest = file_sha256(main_target)
    if main_digest in seen_hashes:
        raise RuntimeError("Ana gorsel mockup veya sabit bilgi gorseliyle ayni dosya olamaz.")
    images.append(
        {
            "id": f"main-{main_digest[:16]}",
            "label": "Original main artwork",
            "path": str(main_target.resolve()),
            "selected": True,
            "protected": False,
            "required": True,
            "role": "main_artwork",
            "sha256": main_digest,
            "fingerprint": image_fingerprint(main_target),
        }
    )

    fixed_dir = job_root / "preview" / "fixed"
    fixed_dir.mkdir(parents=True, exist_ok=True)
    for row in fixed_assets:
        role = clean_text(row["role"])
        source = Path(row["path"])
        target = fixed_dir / f"{role}{source.suffix.lower() or '.jpg'}"
        shutil.copy2(source, target)
        digest = file_sha256(target)
        images.append(
            {
                "id": f"fixed-{role}",
                "label": row["label"],
                "path": str(target.resolve()),
                "selected": True,
                "protected": True,
                "role": role,
                "sha256": digest,
                "fingerprint": image_fingerprint(target),
            }
        )

    videos = []
    for path_value in video_paths[:1]:
        path = Path(path_value).resolve()
        if not path.is_file() or path.stat().st_size <= 0 or job_root.resolve() not in path.parents:
            raise RuntimeError("Video çıktısı güvenli önizleme klasörünün dışında veya boş.")
        if not video_file_is_valid(path):
            raise RuntimeError("Photoshop video çıktısı tamamlanmamış veya geçerli bir MP4 değil.")
        digest = file_sha256(path)
        videos.append(
            {
                "id": f"video-{digest[:16]}",
                "label": path.stem,
                "path": str(path),
                "selected": True,
                "protected": False,
                "role": "video",
                "sha256": digest,
            }
        )
    return {"images": images, "videos": videos}


def validate_existing_media_preview(product_id: str, preview: dict, job_root: Path) -> None:
    images = preview.get("images") if isinstance(preview.get("images"), list) else []
    videos = preview.get("videos") if isinstance(preview.get("videos"), list) else []
    if not images or len(images) > ETSY_MAX_IMAGE_COUNT or len(videos) > 1:
        raise RuntimeError("Medya manifestindeki görsel/video sayısı güvenli sınırın dışında.")
    ids = [clean_text(str(item.get("id") or "")) for item in [*images, *videos]]
    if not all(ids) or len(ids) != len(set(ids)):
        raise RuntimeError("Medya manifestinde eksik veya yinelenen dosya kimliği var.")

    fixed = [item for item in images if bool(item.get("protected"))]
    generated = [item for item in images if not bool(item.get("protected"))]
    if not generated:
        raise RuntimeError("En az bir Photoshop mockup görseli zorunludur.")
    if (
        clean_text(str(images[0].get("role") or "")) != "primary_thumbnail"
        or not bool(images[0].get("required"))
    ):
        raise RuntimeError("Etsy ana thumbnail gorseli ilk sirada ve zorunlu olmalidir.")
    validate_primary_thumbnail_image(Path(clean_text(str(images[0].get("path") or ""))))
    main_images = [item for item in images if clean_text(str(item.get("role") or "")) == "main_artwork"]
    if len(main_images) != 1 or images[-len(fixed) - 1] is not main_images[0]:
        raise RuntimeError("Ana gorsel mockuplardan sonra ve sabit bilgi gorsellerinden once tam bir kez bulunmalidir.")
    if [clean_text(str(item.get("role") or "")) for item in fixed] != list(STATIC_LISTING_ROLES):
        raise RuntimeError("Dört korunan bilgi görseli eksik, fazla veya sırası bozuk.")
    if fixed and images[-len(fixed):] != fixed:
        raise RuntimeError("Korunan bilgi görselleri listenin sonunda olmalıdır.")

    expected_fixed = {clean_text(row["role"]): clean_text(row["content_sha256"]) for row in protected_static_assets(product_id)}
    hashes: set[str] = set()
    root = job_root.resolve()
    for item in [*images, *videos]:
        path = Path(clean_text(str(item.get("path") or ""))).resolve()
        if not path.is_file() or path.stat().st_size <= 0 or root not in path.parents:
            raise RuntimeError("Manifest dosyası güvenli iş klasörünün dışında, eksik veya boş.")
        digest = file_sha256(path)
        if digest != clean_text(str(item.get("sha256") or "")):
            raise RuntimeError(f"Manifest dosyası önizlemeden sonra değişmiş: {path.name}")
        if item in images and digest in hashes:
            raise RuntimeError("Medya manifestinde aynı içerik birden fazla kez bulunuyor.")
        if item in images:
            hashes.add(digest)
        if bool(item.get("protected")) and expected_fixed.get(clean_text(str(item.get("role") or ""))) != digest:
            raise RuntimeError("Korunan sabit görselin içeriği değişmiş; Etsy işlemi durduruldu.")


def start_existing_media_preview(
    product_id: str,
    payload: dict,
    *,
    trusted_source_path: Path | None = None,
) -> dict:
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        active_job = conn.execute(
            """
            SELECT id FROM media_replacement_jobs
            WHERE product_id=? AND status IN ('queued', 'running', 'applying')
            ORDER BY created_at DESC LIMIT 1
            """,
            (product_id,),
        ).fetchone()
    if not product:
        raise ValueError("Urun bulunamadi.")
    if active_job:
        raise RuntimeError("Bu ürün için devam eden medya işlemi var; aynı anda ikinci işlem başlatılamaz.")
    listing_id = clean_text(product["listing_id"] or "")
    if not listing_id:
        raise ValueError("Bu kayit mevcut bir Etsy listingine bagli degil.")

    selection_name = canonical_selection_name(
        str(payload.get("selection_name") or product["selection_name"] or "")
    )
    template_info = selection_template_info(selection_name)
    if not template_info["ready"]:
        raise ValueError(f"{selection_name} klasorunde mockups altinda PSD bulunamadi.")

    job_id = uuid.uuid4().hex
    image_file = payload.get("image_file") or {}
    if trusted_source_path is not None:
        trusted_source = Path(trusted_source_path).resolve()
        allowed_root = (product_upload_dir(product_id) / "bulk_mockups").resolve()
        if allowed_root not in trusted_source.parents:
            raise RuntimeError("Toplu mockup kaynağı güvenli ürün klasörünün dışında.")
        source_path = trusted_source
    elif isinstance(image_file, dict) and image_file.get("data_url"):
        source_path = save_uploaded_data(
            product_id,
            image_file.get("filename") or "artwork.png",
            image_file["data_url"],
            f"media_replacements/{job_id}/source",
        )
    else:
        source_path = Path(clean_text(product["source_image_path"] or ""))
        if not source_path.exists():
            raise ValueError("Bu urunun yerel ana tasarimi yok. Mockup icin orijinal gorseli secmelisin.")
    source_path = assert_artwork_source_safe(source_path, product_id)

    ts = now_iso()
    approval_token = uuid.uuid4().hex + uuid.uuid4().hex
    preview_options = {
        "video_policy": clean_text(payload.get("video_policy") or "preserve_or_create"),
        "skip_inventory_update": bool(payload.get("skip_inventory_update")),
        "skip_digital_delivery": bool(payload.get("skip_digital_delivery")),
        "bulk_queue_item_id": clean_text(payload.get("bulk_queue_item_id") or ""),
    }
    with db() as conn:
        conn.execute(
            """
            INSERT INTO media_replacement_jobs(
                id, product_id, listing_id, selection_name, status, stage, progress,
                source_path, preview_json, backup_json, approval_token, created_at, updated_at
            ) VALUES(?, ?, ?, ?, 'queued', 'Onizleme sirada', 2, ?, ?, '{}', ?, ?, ?)
            """,
            (
                job_id,
                product_id,
                listing_id,
                selection_name,
                str(source_path),
                json.dumps(preview_options),
                approval_token,
                ts,
                ts,
            ),
        )

    thread = threading.Thread(
        target=run_existing_media_preview_job,
        args=(job_id,),
        daemon=True,
        name=f"media-preview-{job_id[:8]}",
    )
    with media_replacement_lock:
        media_replacement_threads[job_id] = thread
    thread.start()
    return media_replacement_job_payload(job_id)


def run_existing_media_preview_job(job_id: str) -> None:
    try:
        with db() as conn:
            job = conn.execute("SELECT * FROM media_replacement_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return
        product_id = job["product_id"]
        try:
            preview_options = json.loads(job["preview_json"] or "{}")
        except Exception:
            preview_options = {}
        queue_item_id = clean_text(preview_options.get("bulk_queue_item_id") or "")
        settings = refresh_etsy_token(get_settings())
        template_info = selection_template_info(job["selection_name"], settings)
        static_psds = [Path(path) for path in template_info["static_psds"]]
        existing_videos = fetch_etsy_listing_videos(clean_text(job["listing_id"]), settings)
        existing_video_signatures = sorted(etsy_video_signature(item) for item in existing_videos)
        if any(not signature for signature in existing_video_signatures):
            raise RuntimeError("Etsy video kimligi okunamadi; mevcut videoya dokunmamak icin islem durduruldu.")
        video_policy = clean_text(preview_options.get("video_policy") or "preserve_or_create")
        if video_policy == "preserve_only":
            video_action = "preserve" if existing_videos else "none"
        else:
            video_action = "preserve" if existing_videos else "create"
        include_video = video_action == "create"
        video_psd = Path(template_info["video_psd"]) if include_video and template_info["video_psd"] else None
        if include_video and video_psd is None and not template_info["ready_videos"]:
            raise RuntimeError("Videosuz Etsy urunu icin selection klasorunde video PSD veya hazir video bulunamadi.")
        render_video = include_video and video_psd is not None
        job_root = product_upload_dir(product_id) / "media_replacements" / job_id
        preview_dir = job_root / "preview"

        update_media_replacement_job(job_id, status="running", stage="Tasarim Photoshop icin hazirlaniyor", progress=12, error=None)
        with photoshop_automation_lock:
            prepared = run_photoshop_prepare(
                product_id,
                job["source_path"],
                settings,
                target_suffix=f"replace-{job_id[:8]}",
                step_key="media_replace_preview",
                check_product_stop=False,
                queue_item_id=queue_item_id,
            )
            digital_dir = preview_dir / "digital"
            digital_dir.mkdir(parents=True, exist_ok=True)
            digital_source = digital_dir / f"{slugify_filename(digital_download_sku(product_id), product_id)}{prepared.suffix.lower() or '.png'}"
            shutil.copy2(prepared, digital_source)
            update_media_replacement_job(job_id, stage="Selection mockuplari uretiliyor", progress=35)
            result = run_external_mockup_script(
                product_id,
                prepared,
                settings,
                only_psd_stems=[path.stem for path in static_psds],
                include_video=render_video,
                clear_existing=False,
                psd_folder=Path(template_info["mockup_folder"]),
                video_psd=video_psd,
                preview_output_dir=preview_dir,
                track_product_progress=False,
                check_product_stop=False,
                queue_item_id=queue_item_id,
            )

        copied_paths = result.get("paths") or {"mockups": [], "videos": []}
        if include_video and not copied_paths.get("videos") and template_info["ready_videos"]:
            target_dir = preview_dir / "videos"
            target_dir.mkdir(parents=True, exist_ok=True)
            source_video = Path(template_info["ready_videos"][0])
            target_video = target_dir / f"01-{slugify_filename(source_video.name, 'video.mp4')}"
            shutil.copy2(source_video, target_video)
            copied_paths["videos"] = [str(target_video)]
        media = build_existing_media_preview(
            product_id,
            job_root,
            list(copied_paths.get("mockups") or []),
            list(copied_paths.get("videos") or []) if include_video else [],
            job["source_path"],
        )
        images = media["images"]
        videos = media["videos"]
        if include_video and len(videos) != 1:
            raise RuntimeError("Videosuz Etsy urunu icin tam bir video uretilemedi.")
        for video in videos:
            video["required"] = True
        preview = {
            "images": images,
            "videos": videos,
            "video_action": video_action,
            "existing_video_signatures": existing_video_signatures,
            "selection_name": job["selection_name"],
            "template_count": len(static_psds),
            "digital_source_path": str(digital_source),
            "manifest_version": MEDIA_REPLACEMENT_MANIFEST_VERSION,
            "protected_roles": list(STATIC_LISTING_ROLES),
            "skip_inventory_update": bool(preview_options.get("skip_inventory_update")),
            "skip_digital_delivery": bool(preview_options.get("skip_digital_delivery")),
            "bulk_queue_item_id": clean_text(preview_options.get("bulk_queue_item_id") or ""),
        }
        validate_existing_media_preview(product_id, preview, job_root)
        manifest_path = job_root / "manifest.json"
        manifest_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
        update_media_replacement_job(
            job_id,
            status="ready",
            stage="Onizleme hazir - Etsy onayi bekleniyor",
            progress=100,
            preview_json=json.dumps(preview, ensure_ascii=False),
        )
        add_event(
            product_id,
            "info",
            f"Mevcut urun icin medya onizlemesi hazir: {len(images)} gorsel, {len(videos)} video.",
            "media_replace_preview",
            meta={"job_id": job_id, "listing_id": job["listing_id"], "selection": job["selection_name"]},
        )
    except Exception as exc:
        update_media_replacement_job(
            job_id,
            status="error",
            stage="Onizleme uretilemedi",
            error=readable_exception(exc),
        )
    finally:
        with media_replacement_lock:
            media_replacement_threads.pop(job_id, None)


def download_remote_file(url: str, target: Path) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Yedeklenecek medya URL'i gecersiz.")
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "EtsyMediaSafetyBackup/1.0"})
    with urlopen_with_dns_retry(req, timeout=180) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"Medya yedegi bos olustu: {target.name}")


def backup_existing_listing_media(job: sqlite3.Row, settings: dict) -> dict:
    listing_id = clean_text(job["listing_id"])
    backup_dir = product_upload_dir(job["product_id"]) / "media_replacements" / job["id"] / "backup"
    images = fetch_etsy_listing_images(listing_id, settings)
    videos = fetch_etsy_listing_videos(listing_id, settings)
    if not images:
        raise RuntimeError("Mevcut Etsy listing görselsiz görünüyor; güvenli medya değişimi başlatılmadı.")
    manifest = {"listing_id": listing_id, "images": [], "videos": [], "created_at": now_iso()}

    for index, image in enumerate(sorted(images, key=lambda item: int(item.get("rank") or 0)), start=1):
        url = best_etsy_image_url(image)
        image_id = clean_text(str(image.get("listing_image_id") or image.get("image_id") or ""))
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
        target = backup_dir / "images" / f"{index:02d}-{image_id or 'image'}{suffix}"
        download_remote_file(url, target)
        manifest["images"].append(
            {
                "id": image_id,
                "rank": int(image.get("rank") or index),
                "url": url,
                "path": str(target),
                "sha256": file_sha256(target),
            }
        )

    for index, video in enumerate(videos, start=1):
        url = best_etsy_video_url(video)
        video_id = clean_text(str(video.get("video_id") or ""))
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".mp4"
        target = backup_dir / "videos" / f"{index:02d}-{video_id or 'video'}{suffix}"
        download_remote_file(url, target)
        manifest["videos"].append({"id": video_id, "url": url, "path": str(target), "sha256": file_sha256(target)})

    if images and len(manifest["images"]) != len(images):
        raise RuntimeError("Tum mevcut Etsy gorselleri yedeklenemedi; islem iptal edildi.")
    if videos and len(manifest["videos"]) != len(videos):
        raise RuntimeError("Mevcut Etsy videosu yedeklenemedi; islem iptal edildi.")
    update_media_replacement_job(job["id"], backup_json=json.dumps(manifest, ensure_ascii=False))
    return manifest


def upload_replacement_image(path: Path, product_id: str, listing_id: str, rank: int, settings: dict) -> dict:
    content_type = mimetypes.guess_type(str(path))[0] or "image/png"
    body, content_type_header = multipart_form_data(
        {"rank": rank, "overwrite": "true", "is_watermarked": "false", "alt_text": f"Listing artwork preview {rank}"},
        [("image", path.name, content_type, path.read_bytes())],
    )
    secrets = settings["_secrets"]
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/{urllib.parse.quote(listing_id)}/images"
    )
    return request_json(
        url,
        method="POST",
        headers={"Content-Type": content_type_header, **etsy_api_headers(settings, oauth=True)},
        payload=body,
        timeout=180,
    )


def upload_replacement_video(path: Path, listing_id: str, settings: dict) -> dict:
    if fetch_etsy_listing_videos(listing_id, settings):
        raise RuntimeError("Mevcut Etsy videosu bulundu; ayni video korunacak ve yeni video yuklenmeyecek.")
    content_type = mimetypes.guess_type(str(path))[0] or "video/mp4"
    body, content_type_header = multipart_form_data(
        {"name": path.name},
        [("video", path.name, content_type, path.read_bytes())],
    )
    secrets = settings["_secrets"]
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/{urllib.parse.quote(listing_id)}/videos"
    )
    return request_json(
        url,
        method="POST",
        headers={"Content-Type": content_type_header, **etsy_api_headers(settings, oauth=True)},
        payload=body,
        timeout=300,
    )


def delete_etsy_listing_media(listing_id: str, media_id: str, kind: str, settings: dict) -> None:
    if not media_id:
        return
    if kind != "image":
        raise RuntimeError("Mevcut Etsy urunlerinin videosu silinemez.")
    secrets = settings["_secrets"]
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/{urllib.parse.quote(listing_id)}/"
        f"images/{urllib.parse.quote(str(media_id))}"
    )
    request_json(url, method="DELETE", headers=etsy_api_headers(settings, oauth=True), timeout=120)


def restore_listing_media_from_backup(
    product_id: str,
    listing_id: str,
    backup: dict,
    settings: dict,
) -> list[str]:
    errors = []
    for item in (backup.get("images") or []):
        path = Path(clean_text(str(item.get("path") or "")))
        expected_hash = clean_text(str(item.get("sha256") or ""))
        if not path.is_file() or path.stat().st_size <= 0 or not expected_hash or file_sha256(path) != expected_hash:
            return [f"Yedek bütünlük kontrolü başarısız; mevcut medya silinmedi: {path.name or 'dosya'}"]
    backup_images = list(backup.get("images") or [])
    try:
        if not backup_images:
            raise RuntimeError("Geri yukleme yedeginde gorsel yok; mevcut gorseller korunuyor.")

        # Never empty an existing listing first. Replace each rank from the verified
        # backup, confirm every upload, and only then remove surplus images.
        restored_ids: set[str] = set()
        for rank, item in enumerate(backup_images, start=1):
            response = upload_replacement_image(Path(item["path"]), product_id, listing_id, rank, settings)
            image_id = clean_text(str(response.get("listing_image_id") or ""))
            if not image_id:
                raise RuntimeError(f"Yedekten yuklenen {rank}. gorsel icin Etsy image ID dondurmedi.")
            restored_ids.add(image_id)
        if len(restored_ids) != len(backup_images):
            raise RuntimeError("Yedek gorsel yuklemeleri benzersiz Etsy image ID dondurmedi.")

        current_images = fetch_etsy_listing_images(listing_id, settings)
        for image in current_images:
            image_id = clean_text(str(image.get("listing_image_id") or ""))
            if image_id and image_id not in restored_ids:
                try:
                    delete_etsy_listing_media(listing_id, image_id, "image", settings)
                except Exception as exc:
                    errors.append(f"Fazla gorsel {image_id} silinemedi: {readable_exception(exc)}")

        verified = False
        last_images: list[dict] = []
        for _attempt in range(6):
            last_images = fetch_etsy_listing_images(listing_id, settings)
            current_ids = {
                clean_text(str(item.get("listing_image_id") or ""))
                for item in last_images
            }
            if len(last_images) == len(backup_images) and restored_ids.issubset(current_ids):
                verified = True
                break
            time.sleep(2)
        if not verified:
            errors.append(
                f"Gorsel geri yukleme dogrulanamadi: beklenen {len(backup_images)}, okunan {len(last_images)}."
            )
    except Exception as exc:
        errors.append("Gorsel geri yukleme: " + readable_exception(exc))
    return errors


def export_updated_digital_artwork(product_id: str, preview: dict) -> Path:
    source = Path(clean_text(str(preview.get("digital_source_path") or "")))
    if not source.exists() or not source.is_file() or source.stat().st_size <= 0:
        raise RuntimeError("DigitalDownload ana gorseli is klasorunde bulunamadi.")
    export_dir = DATA / "digital-artwork"
    export_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower() or ".png"
    target = export_dir / f"{slugify_filename(digital_download_sku(product_id), product_id)}{suffix}"
    temp = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, temp)
    temp.replace(target)
    return target


def canva_redirect_uri() -> str:
    # Canva allows 127.0.0.1 for local integrations but does not accept localhost.
    return f"http://127.0.0.1:{APP_PORT}/oauth/canva/callback"


def start_canva_oauth() -> dict:
    settings = get_settings()
    secrets = settings["_secrets"]
    client_id = clean_text(secrets.get("canva_client_id") or "")
    client_secret = clean_text(secrets.get("canva_client_secret") or "")
    if not client_id or not client_secret:
        raise ValueError("Canva client ID ve client secret Ayarlar alaninda kaydedilmelidir.")
    verifier = base64.urlsafe_b64encode(os.urandom(72)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    state = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode("ascii")
    scopes = "asset:read asset:write design:content:write design:content:read"
    oauth_state = {
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": canva_redirect_uri(),
        "scopes": scopes,
        "created_at": now_iso(),
    }
    write_json_file(CANVA_OAUTH_PATH, oauth_state)
    params = {
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": scopes,
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "redirect_uri": oauth_state["redirect_uri"],
    }
    return {
        "authorize_url": "https://www.canva.com/api/oauth/authorize?" + urllib.parse.urlencode(params),
        "redirect_uri": oauth_state["redirect_uri"],
        "scopes": scopes,
    }


def canva_basic_auth(secrets: dict) -> str:
    credentials = f"{secrets.get('canva_client_id', '')}:{secrets.get('canva_client_secret', '')}"
    return "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("ascii")


def exchange_canva_oauth_code(code: str, state: str) -> dict:
    oauth_state = read_json_file(CANVA_OAUTH_PATH, {})
    expected_state = clean_text(oauth_state.get("state") or "")
    if not expected_state or not hmac.compare_digest(expected_state, clean_text(state)):
        raise RuntimeError("Canva OAuth state dogrulamasi basarisiz.")
    settings = get_settings()
    secrets = settings["_secrets"]
    token = request_form_json(
        "https://api.canva.com/rest/v1/oauth/token",
        {
            "grant_type": "authorization_code",
            "code_verifier": oauth_state["code_verifier"],
            "code": code,
            "redirect_uri": oauth_state["redirect_uri"],
        },
        headers={"Authorization": canva_basic_auth(secrets)},
    )
    stored = read_json_file(SECRETS_PATH, {})
    stored["canva_access_token"] = clean_text(token.get("access_token") or "")
    stored["canva_refresh_token"] = clean_text(token.get("refresh_token") or stored.get("canva_refresh_token") or "")
    stored["canva_token_expires_at"] = time.time() + int(token.get("expires_in") or 14400) - 90
    stored["canva_scope"] = clean_text(token.get("scope") or oauth_state.get("scopes") or "")
    write_json_file(SECRETS_PATH, stored)
    CANVA_OAUTH_PATH.unlink(missing_ok=True)
    return {"connected": bool(stored["canva_access_token"]), "scope": stored["canva_scope"]}


def canva_access_token(settings: dict | None = None, force_refresh: bool = False) -> str:
    settings = settings or get_settings()
    secrets = settings["_secrets"]
    granted_scopes = {
        item for item in re.split(r"[\s,]+", clean_text(secrets.get("canva_scope") or "")) if item
    }
    missing_scopes = sorted(CANVA_REQUIRED_SCOPES - granted_scopes)
    if missing_scopes:
        raise RuntimeError(
            "Canva izinleri eksik: " + ", ".join(missing_scopes) + ". Ayarlar > Canva'yi bagla ile yeniden izin verin."
        )
    token = clean_text(secrets.get("canva_access_token") or "")
    expires_at = float(secrets.get("canva_token_expires_at") or 0)
    if not force_refresh and token and expires_at > time.time() + 30:
        return token
    refresh_token = clean_text(secrets.get("canva_refresh_token") or "")
    if not refresh_token:
        raise RuntimeError("Canva baglantisi yok. Ayarlar > Canva bagla adimini tamamla.")
    refreshed = request_form_json(
        "https://api.canva.com/rest/v1/oauth/token",
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Authorization": canva_basic_auth(secrets)},
    )
    token = clean_text(refreshed.get("access_token") or "")
    if not token:
        raise RuntimeError("Canva access token yenilenemedi.")
    stored = read_json_file(SECRETS_PATH, {})
    stored["canva_access_token"] = token
    stored["canva_refresh_token"] = clean_text(refreshed.get("refresh_token") or refresh_token)
    stored["canva_token_expires_at"] = time.time() + int(refreshed.get("expires_in") or 14400) - 90
    if refreshed.get("scope"):
        stored["canva_scope"] = clean_text(refreshed.get("scope") or "")
    write_json_file(SECRETS_PATH, stored)
    return token


def canva_headers(settings: dict | None = None, force_refresh: bool = False) -> dict:
    return {"Authorization": f"Bearer {canva_access_token(settings, force_refresh=force_refresh)}"}


def canva_request_json(
    url: str,
    *,
    settings: dict,
    method: str = "GET",
    headers: dict | None = None,
    payload=None,
    timeout: int = 120,
) -> dict:
    def send(force_refresh: bool) -> dict:
        return request_json(
            url,
            method=method,
            headers={**(headers or {}), **canva_headers(settings, force_refresh=force_refresh)},
            payload=payload,
            timeout=timeout,
        )

    try:
        return send(False)
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        return send(True)


def wait_for_canva_job(resource: str, response: dict, settings: dict, timeout: int = 300) -> dict:
    job = response.get("job") if isinstance(response, dict) else None
    if not isinstance(job, dict):
        raise RuntimeError("Canva job cevabi okunamadi.")
    job_id = clean_text(job.get("id") or "")
    deadline = time.time() + max(10, timeout)
    while clean_text(job.get("status") or "").lower() == "in_progress":
        if not job_id or time.time() >= deadline:
            raise TimeoutError(f"Canva {resource} islemi zaman asimina ugradi.")
        time.sleep(1.5)
        response = canva_request_json(
            f"https://api.canva.com/rest/v1/{resource}/{urllib.parse.quote(job_id)}",
            settings=settings,
            timeout=90,
        )
        job = response.get("job") if isinstance(response, dict) else None
        if not isinstance(job, dict):
            raise RuntimeError("Canva job durumu okunamadi.")
    if clean_text(job.get("status") or "").lower() != "success":
        error = job.get("error") if isinstance(job.get("error"), dict) else {}
        raise RuntimeError("Canva islemi basarisiz: " + clean_text(error.get("message") or error.get("code") or "bilinmeyen hata"))
    return job


def canva_upload_asset(source: Path, sku: str, settings: dict) -> dict:
    if source.stat().st_size > 50 * 1024 * 1024:
        raise RuntimeError("Canva gorsel yukleme siniri 50 MB; kaynak dosya daha buyuk.")
    asset_name = f"{sku}{source.suffix.lower()}"[:50]
    metadata = {"name_base64": base64.b64encode(asset_name.encode("utf-8")).decode("ascii")}
    response = canva_request_json(
        "https://api.canva.com/rest/v1/asset-uploads",
        settings=settings,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "Asset-Upload-Metadata": json.dumps(metadata, ensure_ascii=True),
        },
        payload=source.read_bytes(),
        timeout=600,
    )
    job = wait_for_canva_job("asset-uploads", response, settings, timeout=600)
    asset = job.get("asset") if isinstance(job.get("asset"), dict) else {}
    if not clean_text(asset.get("id") or ""):
        raise RuntimeError("Canva yuklenen gorsel icin asset ID dondurmedi.")
    return asset


def canva_design_dimensions(source: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(source) as image:
        width, height = image.size
    scale = min(1.0, 8000 / max(1, width), 8000 / max(1, height), (25_000_000 / max(1, width * height)) ** 0.5)
    return max(40, int(round(width * scale))), max(40, int(round(height * scale)))


def canva_create_design(source: Path, asset_id: str, sku: str, settings: dict) -> dict:
    width, height = canva_design_dimensions(source)
    response = canva_request_json(
        "https://api.canva.com/rest/v1/designs",
        settings=settings,
        method="POST",
        payload={
            "type": "type_and_asset",
            "design_type": {"type": "custom", "width": width, "height": height},
            "asset_id": asset_id,
            "title": sku[:255],
        },
        timeout=120,
    )
    design = response.get("design") if isinstance(response, dict) else None
    if not isinstance(design, dict) or not clean_text(design.get("id") or ""):
        raise RuntimeError("Canva tasarim ID dondurmedi.")
    return design


def download_canva_export(url: str, target: Path, wanted_suffix: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "EtsyPosterPanel/1.0"})
    with urlopen_with_dns_retry(request, timeout=600) as response:
        content_type = clean_text(response.headers.get("Content-Type") or "").lower()
        data = response.read()
    if "zip" in content_type or data.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(wanted_suffix.lower())]
            if not names:
                raise RuntimeError(f"Canva ZIP icinde {wanted_suffix} bulunamadi.")
            data = archive.read(names[0])
    target.write_bytes(data)
    if target.stat().st_size <= 0:
        raise RuntimeError(f"Canva cikti dosyasi bos: {target.name}")


def canva_export_design(design_id: str, export_format: dict, target: Path, settings: dict) -> dict:
    response = canva_request_json(
        "https://api.canva.com/rest/v1/exports",
        settings=settings,
        method="POST",
        payload={"design_id": design_id, "format": export_format},
        timeout=120,
    )
    job = wait_for_canva_job("exports", response, settings, timeout=600)
    urls = job.get("urls") if isinstance(job.get("urls"), list) else []
    if not urls:
        raise RuntimeError(f"Canva {target.suffix} export URL dondurmedi.")
    download_canva_export(clean_text(str(urls[0])), target, target.suffix)
    return job


def validate_canva_print_cmyk_pdf(path: Path) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("CMYK PDF dogrulamasi icin pypdf eksik. Uygulamayi yeniden baslatin.") from exc

    reader = PdfReader(path)
    output_intents = reader.trailer["/Root"].get("/OutputIntents") or []
    if not output_intents:
        raise RuntimeError("CMYK PDF baski renk profili icermiyor.")
    output_intent = output_intents[0].get_object()
    profile_ref = output_intent.get("/DestOutputProfile")
    profile = profile_ref.get_object() if profile_ref else None
    if not profile or int(profile.get("/N") or 0) != 4:
        raise RuntimeError("CMYK PDF icindeki ICC profili dort kanalli degil.")
    profile_info = clean_text(str(output_intent.get("/Info") or ""))
    if "GRACoL 2013 CRPC6" not in profile_info:
        raise RuntimeError(f"CMYK PDF beklenen Canva baski profilini icermiyor: {profile_info or 'profil yok'}")

    has_cmyk_image = False
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for image_ref in (resources.get("/XObject") or {}).values():
            image = image_ref.get_object()
            if image.get("/Subtype") == "/Image" and image.get("/ColorSpace") == "/DeviceCMYK":
                has_cmyk_image = True
                break
        if has_cmyk_image:
            break
    if not has_cmyk_image:
        raise RuntimeError("CMYK PDF icinde DeviceCMYK baski gorseli bulunamadi.")
    return {
        "cmyk_conversion": "canva_pdf_print_gracol2013_crpc6",
        "cmyk_profile": CANVA_PRINT_CMYK_PROFILE_INFO,
        "cmyk_rendering_intent": "perceptual",
        "cmyk_page_dpi": 96,
    }


def create_canva_print_cmyk_pdf(source: Path, target: Path) -> dict:
    try:
        from PIL import Image, ImageCms, ImageOps
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject
    except ImportError as exc:
        raise RuntimeError("Canva baski CMYK PDF icin Pillow ve pypdf kurulu olmalidir. Uygulamayi yeniden baslatin.") from exc

    if not CANVA_PRINT_CMYK_PROFILE_PATH.is_file():
        raise FileNotFoundError(f"Canva CMYK baski profili bulunamadi: {CANVA_PRINT_CMYK_PROFILE_PATH}")

    target.parent.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex
    base_pdf = target.with_name(f".{target.stem}-{nonce}.base.pdf")
    completed_pdf = target.with_name(f".{target.stem}-{nonce}.complete.pdf")
    try:
        transform = ImageCms.buildTransformFromOpenProfiles(
            ImageCms.createProfile("sRGB"),
            ImageCms.getOpenProfile(str(CANVA_PRINT_CMYK_PROFILE_PATH)),
            "RGB",
            "CMYK",
            renderingIntent=ImageCms.Intent.PERCEPTUAL,
        )
        with Image.open(source) as raw:
            rgb = ImageOps.exif_transpose(raw).convert("RGB")
            cmyk = ImageCms.applyTransform(rgb, transform)
            # Canva's pixel-based PDF Print export uses a 96 DPI page and perceptual rendering.
            cmyk.save(base_pdf, "PDF", resolution=96.0, quality=90, subsampling=0)

        reader = PdfReader(base_pdf)
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        profile_stream = DecodedStreamObject()
        profile_stream.set_data(CANVA_PRINT_CMYK_PROFILE_PATH.read_bytes())
        profile_stream[NameObject("/N")] = NumberObject(4)
        profile_ref = writer._add_object(profile_stream)
        output_intent = DictionaryObject(
            {
                NameObject("/Info"): TextStringObject(CANVA_PRINT_CMYK_PROFILE_INFO),
                NameObject("/Type"): NameObject("/OutputIntent"),
                NameObject("/OutputConditionIdentifier"): TextStringObject("CGATS 21.2"),
                NameObject("/RegistryName"): TextStringObject("http://www.color.org"),
                NameObject("/S"): NameObject("/GTS_PDFX"),
                NameObject("/OutputCondition"): TextStringObject("CGATS21-2-CRPC6"),
                NameObject("/DestOutputProfile"): profile_ref,
            }
        )
        writer.root_object[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(output_intent)])
        with completed_pdf.open("wb") as handle:
            writer.write(handle)
        completed_pdf.replace(target)
    finally:
        base_pdf.unlink(missing_ok=True)
        completed_pdf.unlink(missing_ok=True)

    return validate_canva_print_cmyk_pdf(target)


def build_local_delivery_files(source: Path, staging: Path) -> dict:
    from PIL import Image, ImageOps

    with Image.open(source) as raw:
        rgb = ImageOps.exif_transpose(raw).convert("RGB")
        rgb.save(staging / "png.png", "PNG", optimize=True)
        rgb.save(staging / "jpg.jpg", "JPEG", quality=95, optimize=True, progressive=True, dpi=(300, 300))
        rgb.save(staging / "rgb.pdf", "PDF", resolution=300.0)
    cmyk_meta = create_canva_print_cmyk_pdf(staging / "png.png", staging / "cmyk.pdf")
    return {"generator": "local", **cmyk_meta}


def build_canva_delivery_files(source: Path, staging: Path, sku: str, settings: dict, progress_callback=None) -> dict:
    from PIL import Image, ImageOps

    try:
        canva_access_token(settings, force_refresh=True)
    except Exception as exc:
        raise RuntimeError(
            "Canva oturumu gecersiz. Ayarlar > Canva'yi bagla ile yeniden izin verin: "
            + readable_exception(exc)
        ) from exc

    upload_source = source
    if progress_callback:
        progress_callback(8, "Canva yuklemesi icin gorsel hazirlaniyor")
    if source.stat().st_size > 8 * 1024 * 1024 or source.suffix.lower() not in {".jpg", ".jpeg"}:
        upload_source = staging / "canva-upload.jpg"
        width, height = canva_design_dimensions(source)
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            image.save(upload_source, "JPEG", quality=100, subsampling=0, optimize=True, progressive=True)
    if progress_callback:
        progress_callback(12, "Gorsel Canva'ya yukleniyor")
    asset = canva_upload_asset(upload_source, sku, settings)
    if progress_callback:
        progress_callback(20, "Gorsel Canva'ya yuklendi")
    design = canva_create_design(source, clean_text(asset.get("id") or ""), sku, settings)
    design_id = clean_text(design.get("id") or "")
    if progress_callback:
        progress_callback(35, "Canva tasarimi olusturuldu")
    export_quality = clean_text(settings.get("canva_export_quality") or "pro").lower()
    if export_quality not in {"regular", "pro"}:
        export_quality = "pro"
    canva_export_design(
        design_id,
        {"type": "png", "export_quality": export_quality, "lossless": True, "transparent_background": False},
        staging / "png.png",
        settings,
    )
    if progress_callback:
        progress_callback(55, "PNG Canva'dan indirildi")
    canva_export_design(
        design_id,
        {"type": "jpg", "quality": 100, "export_quality": export_quality},
        staging / "jpg.jpg",
        settings,
    )
    if progress_callback:
        progress_callback(70, "JPG Canva'dan indirildi")
    canva_export_design(
        design_id,
        {"type": "pdf", "export_quality": export_quality},
        staging / "rgb.pdf",
        settings,
    )
    if progress_callback:
        progress_callback(85, "RGB PDF Canva'dan indirildi")
    cmyk_meta = create_canva_print_cmyk_pdf(staging / "png.png", staging / "cmyk.pdf")
    if upload_source != source:
        upload_source.unlink(missing_ok=True)
    if progress_callback:
        progress_callback(95, "CMYK PDF Canva'nin GRACoL baski profiliyle hazirlandi")
    return {
        "generator": "canva_connect",
        "canva_asset_id": clean_text(asset.get("id") or ""),
        "canva_design_id": design_id,
        "canva_edit_url": clean_text(((design.get("urls") or {}).get("edit_url") if isinstance(design.get("urls"), dict) else "") or ""),
        "export_quality": export_quality,
        **cmyk_meta,
    }


def validate_digital_package_files(staging: Path) -> list[dict]:
    from PIL import Image

    for name in ("png.png", "jpg.jpg"):
        with Image.open(staging / name) as image:
            image.verify()
    for name in ("rgb.pdf", "cmyk.pdf"):
        if not (staging / name).read_bytes().startswith(b"%PDF"):
            raise RuntimeError(f"PDF dogrulamasi basarisiz: {name}")
    validate_canva_print_cmyk_pdf(staging / "cmyk.pdf")
    manifest_files = []
    for name in DIGITAL_PACKAGE_FILENAMES:
        path = staging / name
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Digital delivery dosyasi olusmadi: {name}")
        manifest_files.append({"name": name, "size": path.stat().st_size, "sha256": file_sha256(path)})
    return manifest_files


def build_digital_delivery_package(
    product_id: str,
    source_path: str | Path,
    settings: dict | None = None,
    progress_callback=None,
) -> Path:
    settings = settings or get_settings()
    source = assert_artwork_source_safe(Path(source_path), product_id)
    sku = slugify_filename(digital_download_sku(product_id), product_id)
    package_dir = product_upload_dir(product_id) / "digital_delivery" / sku
    staging = package_dir.with_name(package_dir.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        if bool(settings.get("canva_delivery_enabled", True)):
            generator_meta = build_canva_delivery_files(source, staging, sku, settings, progress_callback)
        else:
            generator_meta = build_local_delivery_files(source, staging)
        if not DIGITAL_GUIDE_PATH.is_file() or DIGITAL_GUIDE_PATH.stat().st_size <= 0:
            raise FileNotFoundError(f"Digital delivery guide bulunamadi: {DIGITAL_GUIDE_PATH}")
        shutil.copy2(DIGITAL_GUIDE_PATH, staging / "guide.png")
        manifest_files = validate_digital_package_files(staging)
        write_json_file(
            staging / "manifest.json",
            {
                "product_id": product_id,
                "sku": sku,
                "source_sha256": file_sha256(source),
                "created_at": now_iso(),
                "files": manifest_files,
                **generator_meta,
            },
        )
        if package_dir.exists():
            shutil.rmtree(package_dir)
        staging.replace(package_dir)
        return package_dir
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def google_redirect_uri() -> str:
    return f"http://{APP_PUBLIC_HOST}:{APP_PORT}/oauth/google/callback"


def start_google_oauth() -> dict:
    settings = get_settings()
    secrets = settings["_secrets"]
    client_id = clean_text(secrets.get("google_client_id") or "")
    client_secret = clean_text(secrets.get("google_client_secret") or "")
    if not client_id or not client_secret:
        raise ValueError("Google OAuth client ID ve client secret Ayarlar alaninda kaydedilmelidir.")
    state = uuid.uuid4().hex + uuid.uuid4().hex
    payload = {"state": state, "redirect_uri": google_redirect_uri(), "created_at": now_iso()}
    write_json_file(GOOGLE_OAUTH_PATH, payload)
    params = {
        "client_id": client_id,
        "redirect_uri": payload["redirect_uri"],
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params),
        "redirect_uri": payload["redirect_uri"],
    }


def exchange_google_oauth_code(code: str, state: str) -> dict:
    oauth_state = read_json_file(GOOGLE_OAUTH_PATH, {})
    if not oauth_state or not hmac.compare_digest(clean_text(oauth_state.get("state") or ""), clean_text(state)):
        raise RuntimeError("Google OAuth state dogrulamasi basarisiz.")
    settings = get_settings()
    secrets = settings["_secrets"]
    token = request_form_json(
        "https://oauth2.googleapis.com/token",
        {
            "code": code,
            "client_id": secrets["google_client_id"],
            "client_secret": secrets["google_client_secret"],
            "redirect_uri": oauth_state["redirect_uri"],
            "grant_type": "authorization_code",
        },
    )
    stored = read_json_file(SECRETS_PATH, {})
    stored["google_access_token"] = token.get("access_token", "")
    if token.get("refresh_token"):
        stored["google_refresh_token"] = token["refresh_token"]
    stored["google_token_expires_at"] = time.time() + int(token.get("expires_in") or 3600) - 60
    write_json_file(SECRETS_PATH, stored)
    return {"connected": bool(stored.get("google_access_token")), "scope": token.get("scope", "")}


def google_access_token(settings: dict | None = None) -> str:
    settings = settings or get_settings()
    secrets = settings["_secrets"]
    token = clean_text(secrets.get("google_access_token") or "")
    expires_at = float(secrets.get("google_token_expires_at") or 0)
    if token and expires_at > time.time() + 30:
        return token
    refresh_token = clean_text(secrets.get("google_refresh_token") or "")
    if not refresh_token:
        raise RuntimeError("Google Drive baglantisi yok. Ayarlar > Google Drive bagla adimini tamamla.")
    refreshed = request_form_json(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": secrets.get("google_client_id", ""),
            "client_secret": secrets.get("google_client_secret", ""),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    token = clean_text(refreshed.get("access_token") or "")
    if not token:
        raise RuntimeError("Google access token yenilenemedi.")
    stored = read_json_file(SECRETS_PATH, {})
    stored["google_access_token"] = token
    stored["google_token_expires_at"] = time.time() + int(refreshed.get("expires_in") or 3600) - 60
    write_json_file(SECRETS_PATH, stored)
    return token


def google_drive_headers(settings: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {google_access_token(settings)}"}


def google_drive_find_child(name: str, parent_id: str, settings: dict) -> dict | None:
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    query = f"name='{escaped}' and '{parent_id}' in parents and trashed=false"
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
        {
            "q": query,
            "spaces": "drive",
            "fields": "files(id,name,mimeType,size,md5Checksum,webViewLink)",
            "pageSize": 10,
        }
    )
    files = request_json(url, headers=google_drive_headers(settings), timeout=90).get("files") or []
    return files[0] if files else None


def google_drive_ensure_folder(name: str, parent_id: str, settings: dict) -> dict:
    existing = google_drive_find_child(name, parent_id, settings)
    if existing and existing.get("mimeType") == "application/vnd.google-apps.folder":
        return existing
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    return request_json(
        "https://www.googleapis.com/drive/v3/files?fields=id,name,mimeType,size,md5Checksum,webViewLink",
        method="POST",
        headers=google_drive_headers(settings),
        payload=metadata,
        timeout=90,
    )


def google_drive_upload_file(path: Path, folder_id: str, settings: dict) -> dict:
    existing = google_drive_find_child(path.name, folder_id, settings)
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    headers = {"Content-Type": content_type, **google_drive_headers(settings)}
    if existing:
        url = f"https://www.googleapis.com/upload/drive/v3/files/{existing['id']}?uploadType=media&fields=id,name,size,md5Checksum,webViewLink"
        return request_json(url, method="PATCH", headers=headers, payload=path.read_bytes(), timeout=600)

    boundary = "codex-drive-" + uuid.uuid4().hex
    metadata = json.dumps({"name": path.name, "parents": [folder_id]}, ensure_ascii=False).encode("utf-8")
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("ascii")
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode("ascii")
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode("ascii")
    )
    return request_json(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size,md5Checksum,webViewLink",
        method="POST",
        headers={"Content-Type": f"multipart/related; boundary={boundary}", **google_drive_headers(settings)},
        payload=body,
        timeout=600,
    )


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_google_drive_file(path: Path, remote: dict) -> dict:
    remote_name = clean_text(remote.get("name") or "")
    remote_size = int(remote.get("size") or 0)
    remote_md5 = clean_text(remote.get("md5Checksum") or "").lower()
    if remote_name != path.name:
        raise RuntimeError(f"Google Drive dosya adi dogrulanamadi: {path.name}")
    if remote_size and remote_size != path.stat().st_size:
        raise RuntimeError(f"Google Drive dosya boyutu dogrulanamadi: {path.name}")
    if remote_md5 and remote_md5 != file_md5(path):
        raise RuntimeError(f"Google Drive checksum dogrulanamadi: {path.name}")
    return {
        "id": clean_text(remote.get("id") or ""),
        "name": remote_name,
        "size": remote_size or path.stat().st_size,
        "md5": remote_md5 or file_md5(path),
        "web_view_link": clean_text(remote.get("webViewLink") or ""),
    }


def sync_digital_package_to_drive(
    product_id: str,
    package_dir: Path,
    settings: dict | None = None,
    progress_callback=None,
) -> dict:
    settings = settings or get_settings()
    if not bool(settings.get("google_drive_sync_enabled", True)):
        return {"skipped": True, "reason": "disabled", "package_dir": str(package_dir)}
    parent_id = clean_text(settings.get("google_drive_parent_folder_id") or "") or "root"
    folder = google_drive_ensure_folder(package_dir.name, parent_id, settings)
    folder_id = clean_text(folder.get("id") or "")
    if not folder_id:
        raise RuntimeError("Google Drive SKU klasoru olusturulamadi.")
    uploaded = []
    total = len(DIGITAL_PACKAGE_FILENAMES)
    for index, name in enumerate(DIGITAL_PACKAGE_FILENAMES, start=1):
        path = package_dir / name
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Google Drive'a gidecek dosya eksik: {name}")
        last_error = None
        verified_file = None
        for attempt in range(1, 4):
            try:
                uploaded_file = google_drive_upload_file(path, folder_id, settings)
                remote = uploaded_file
                if not clean_text(remote.get("name") or "") or not remote.get("size"):
                    remote = google_drive_find_child(path.name, folder_id, settings) or uploaded_file
                verified_file = verify_google_drive_file(path, remote)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(attempt * 1.5)
        if verified_file is None:
            raise RuntimeError(f"Google Drive yukleme basarisiz ({name}): {readable_exception(last_error)}")
        uploaded.append(verified_file)
        if progress_callback:
            progress_callback(int(index / max(1, total) * 100), name, index, total)
    return {
        "folder_id": folder_id,
        "folder_name": package_dir.name,
        "folder_url": clean_text(folder.get("webViewLink") or "") or f"https://drive.google.com/drive/folders/{folder_id}",
        "uploaded": len(uploaded),
        "files": uploaded,
        "verified": len(uploaded) == total,
    }


def _prepare_and_sync_digital_delivery_legacy(
    product_id: str,
    source_path: str | Path,
    settings: dict | None = None,
    *,
    track_product_steps: bool = False,
) -> dict:
    settings = settings or get_settings()
    if track_product_steps:
        set_step(product_id, "digital_package", "running", 10)
        update_product(product_id, current_step="digital_package", overall_progress=59)
    package_dir = build_digital_delivery_package(product_id, source_path)
    result = {"package_dir": str(package_dir), "files": list(DIGITAL_PACKAGE_FILENAMES)}
    if track_product_steps:
        set_step(product_id, "digital_package", "done", 100)
        update_product(product_id, overall_progress=61)
        add_event(product_id, "info", "PNG, JPG, RGB PDF ve CMYK PDF hazırlandı.", "digital_package", progress=100)

    def drive_progress(percent: int, name: str, index: int, total: int) -> None:
        if not track_product_steps:
            return
        set_step(product_id, "google_drive", "running", percent)
        update_product(product_id, current_step="google_drive", overall_progress=61 + int(percent * 0.05))
        add_event(
            product_id,
            "info",
            f"Google Drive'a aktarılıyor: {name} ({index}/{total})",
            "google_drive",
            progress=percent,
        )

    try:
        if track_product_steps:
            set_step(product_id, "google_drive", "running", 5)
            update_product(product_id, current_step="google_drive", overall_progress=62)
        result["drive"] = sync_digital_package_to_drive(
            product_id,
            package_dir,
            settings,
            progress_callback=drive_progress,
        )
        drive_skipped = bool(result["drive"].get("skipped"))
        if track_product_steps:
            set_step(product_id, "google_drive", "skipped" if drive_skipped else "done", 100)
            update_product(product_id, overall_progress=66)
        message = "Google Drive kapalı; yerel teslim paketi hazır." if drive_skipped else "DigitalDownload paketi Google Drive'a aktarıldı."
        add_event(product_id, "info", message, "google_drive", progress=100, meta=result)
    except Exception as exc:
        result["drive_error"] = readable_exception(exc)
        if track_product_steps:
            set_step(product_id, "google_drive", "warning", 100, error=result["drive_error"])
            update_product(product_id, overall_progress=66)
        add_event(
            product_id,
            "warning",
            "DigitalDownload paketi yerelde hazır; Google Drive bağlantısı tamamlanınca yeniden senkronlanabilir.",
            "google_drive",
            progress=100,
            meta=result,
        )
    return result


def digital_delivery_status_path(product_id: str) -> Path:
    return product_upload_dir(product_id) / "digital_delivery" / "delivery-status.json"


def write_digital_delivery_status(product_id: str, payload: dict) -> None:
    write_json_file(digital_delivery_status_path(product_id), {**payload, "updated_at": now_iso()})


def digital_delivery_status_payload(product_id: str) -> dict:
    with db() as conn:
        product = conn.execute("SELECT id, source_image_path FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Urun bulunamadi.")
    settings = get_settings()
    secrets = settings["_secrets"]
    sku = slugify_filename(digital_download_sku(product_id), product_id)
    package_dir = product_upload_dir(product_id) / "digital_delivery" / sku
    manifest = read_json_file(package_dir / "manifest.json", {})
    files = []
    package_ready = True
    for name in DIGITAL_PACKAGE_FILENAMES:
        path = package_dir / name
        ready = path.is_file() and path.stat().st_size > 0
        package_ready = package_ready and ready
        files.append({"name": name, "ready": ready, "size": path.stat().st_size if ready else 0})
    saved = read_json_file(digital_delivery_status_path(product_id), {})
    if not clean_text(saved.get("state") or ""):
        saved["state"] = "legacy_package" if package_ready else "not_started"
    return {
        **saved,
        "product_id": product_id,
        "sku": sku,
        "package_dir": str(package_dir),
        "package_ready": package_ready,
        "files": files,
        "manifest": manifest,
        "canva_enabled": bool(settings.get("canva_delivery_enabled", True)),
        "canva_configured": bool(secrets.get("canva_client_id") and secrets.get("canva_client_secret")),
        "canva_connected": bool(secrets.get("canva_access_token") or secrets.get("canva_refresh_token")),
        "drive_enabled": bool(settings.get("google_drive_sync_enabled", True)),
        "drive_configured": bool(secrets.get("google_client_id") and secrets.get("google_client_secret")),
        "drive_connected": bool(secrets.get("google_access_token") or secrets.get("google_refresh_token")),
        "source_ready": bool(product["source_image_path"] and Path(str(product["source_image_path"])).is_file()),
    }


def prepare_and_sync_digital_delivery(
    product_id: str,
    source_path: str | Path,
    settings: dict | None = None,
    *,
    track_product_steps: bool = False,
) -> dict:
    # Kept as a compatibility entry point for existing media jobs.
    return {"state": "disabled", "skipped": True}


def retry_digital_delivery(product_id: str) -> dict:
    ensure_steps(product_id)
    with db() as conn:
        product = conn.execute("SELECT source_image_path FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Urun bulunamadi.")
    source_path = clean_text(product["source_image_path"] or "")
    if not source_path or not Path(source_path).is_file():
        raise ValueError("DigitalDownload paketi icin yerel ana gorsel bulunamadi.")
    result = prepare_and_sync_digital_delivery(product_id, source_path, get_settings(), track_product_steps=True)
    return {"delivery": result, "status": digital_delivery_status_payload(product_id)}


def begin_existing_media_apply(product_id: str, job_id: str, payload: dict) -> dict:
    with db() as conn:
        job = conn.execute("SELECT * FROM media_replacement_jobs WHERE id=? AND product_id=?", (job_id, product_id)).fetchone()
        product = conn.execute("SELECT listing_id FROM products WHERE id=?", (product_id,)).fetchone()
    if not job or not product:
        raise ValueError("Onizleme isi veya urun bulunamadi.")
    if job["status"] != "ready":
        raise ValueError("Yalnizca hazir ve henuz uygulanmamis onizleme Etsy'ye gonderilebilir.")
    if clean_text(product["listing_id"] or "") != clean_text(job["listing_id"]):
        raise RuntimeError("Guvenlik kontrolu: urunun listing ID'si onizlemeden sonra degisti.")
    if not hmac.compare_digest(clean_text(payload.get("approval_token") or ""), clean_text(job["approval_token"] or "")):
        raise RuntimeError("Onizleme onay anahtari gecersiz.")
    required_confirmation = f"{MEDIA_REPLACEMENT_CONFIRMATION_PREFIX} {job['listing_id']}"
    if clean_text(payload.get("confirmation") or "") != required_confirmation:
        raise RuntimeError(f"Onay metni tam olarak '{required_confirmation}' olmali.")

    try:
        preview = json.loads(job["preview_json"] or "{}")
    except Exception:
        preview = {}
    if int(preview.get("manifest_version") or 0) != MEDIA_REPLACEMENT_MANIFEST_VERSION:
        raise RuntimeError("Bu onizleme eski medya kurallarini kullaniyor. Guvenli video kurali icin yeni onizleme olusturun.")
    video_action = clean_text(str(preview.get("video_action") or ""))
    preview_videos = list(preview.get("videos") or [])
    expected_video_signatures = list(preview.get("existing_video_signatures") or [])
    if video_action == "preserve":
        if preview_videos or not expected_video_signatures:
            raise RuntimeError("Video koruma manifesti gecersiz; yeni onizleme olusturun.")
    elif video_action == "create":
        if len(preview_videos) != 1 or expected_video_signatures:
            raise RuntimeError("Eksik video olusturma manifesti gecersiz; yeni onizleme olusturun.")
    elif video_action == "none":
        if preview_videos or expected_video_signatures:
            raise RuntimeError("Videosuz ürün manifesti geçersiz; yeni önizleme oluşturun.")
    else:
        raise RuntimeError("Video politikasi manifestte yok; yeni onizleme olusturun.")
    job_root = (product_upload_dir(product_id) / "media_replacements" / job_id).resolve()
    validate_existing_media_preview(product_id, preview, job_root)
    selected_asset_ids = payload.get("selected_asset_ids")
    if not isinstance(selected_asset_ids, list):
        raise ValueError("Gonderilecek onizleme dosyalari acikca secilmelidir.")
    requested_ids = {clean_text(str(item)) for item in selected_asset_ids if clean_text(str(item))}
    if not requested_ids:
        raise ValueError("En az bir yeni gorsel secilmelidir.")
    manifest_ids = {
        clean_text(str(item.get("id") or ""))
        for item in [*(preview.get("images") or []), *(preview.get("videos") or [])]
    }
    if not requested_ids.issubset(manifest_ids):
        raise RuntimeError("Onay isteğinde manifestte bulunmayan dosya kimliği var.")
    protected_ids = {
        clean_text(str(item.get("id") or ""))
        for item in (preview.get("images") or [])
        if bool(item.get("protected"))
    }
    if not protected_ids.issubset(requested_ids):
        raise RuntimeError("Dört sabit bilgi görseli korumalıdır ve seçimden çıkarılamaz.")
    required_ids = {
        clean_text(str(item.get("id") or ""))
        for item in [*(preview.get("images") or []), *preview_videos]
        if bool(item.get("required"))
    }
    if not required_ids.issubset(requested_ids):
        raise RuntimeError("Ana gorsel veya otomatik video Etsy medya seciminden cikarilamaz.")
    images = [item for item in (preview.get("images") or []) if item.get("id") in requested_ids]
    videos = [item for item in preview_videos if item.get("id") in requested_ids]
    preview["approved_image_ids"] = [item["id"] for item in images]
    if not any(not bool(item.get("protected")) for item in images):
        raise ValueError("En az bir Photoshop mockup görseli seçilmelidir.")

    for item in [*images, *videos]:
        path = Path(item.get("path") or "").resolve()
        if not path.exists() or job_root not in path.parents:
            raise RuntimeError("Onizleme dosyasi guvenli is klasorunun disinda veya kayip.")

    with db() as conn:
        cursor = conn.execute(
            """
            UPDATE media_replacement_jobs
            SET status='applying', stage='Onaylanan medya Etsy icin hazirlaniyor',
                progress=5, error=NULL, preview_json=?, updated_at=?
            WHERE id=? AND product_id=? AND status='ready'
              AND NOT EXISTS (
                  SELECT 1 FROM media_replacement_jobs other
                  WHERE other.listing_id=? AND other.id<>? AND other.status='applying'
              )
            """,
            (json.dumps(preview, ensure_ascii=False), now_iso(), job_id, product_id, job["listing_id"], job_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Medya işlemi başka bir istek tarafından başlatılmış; ikinci yazma engellendi.")
    thread = threading.Thread(
        target=run_existing_media_apply_job,
        args=(job_id, [item["id"] for item in images]),
        daemon=True,
        name=f"media-apply-{job_id[:8]}",
    )
    with media_replacement_lock:
        media_replacement_threads[job_id] = thread
    thread.start()
    return media_replacement_job_payload(job_id)


def run_existing_media_apply_job(job_id: str, image_ids: list[str]) -> None:
    try:
        with db() as conn:
            job = conn.execute("SELECT * FROM media_replacement_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return
        product_id = job["product_id"]
        listing_id = clean_text(job["listing_id"])
        settings = refresh_etsy_token(get_settings())
        preview = json.loads(job["preview_json"] or "{}")
        if int(preview.get("manifest_version") or 0) != MEDIA_REPLACEMENT_MANIFEST_VERSION:
            raise RuntimeError("Eski medya manifesti worker tarafindan reddedildi.")
        video_action = clean_text(str(preview.get("video_action") or ""))
        expected_video_signatures = sorted(
            clean_text(str(item)) for item in (preview.get("existing_video_signatures") or [])
        )
        videos = list(preview.get("videos") or [])
        if video_action == "preserve" and (videos or not expected_video_signatures):
            raise RuntimeError("Video koruma manifesti worker tarafindan reddedildi.")
        if video_action == "create" and (len(videos) != 1 or expected_video_signatures):
            raise RuntimeError("Video olusturma manifesti worker tarafindan reddedildi.")
        if video_action == "none" and (videos or expected_video_signatures):
            raise RuntimeError("Videosuz ürün manifesti worker tarafından reddedildi.")
        if video_action not in {"preserve", "create", "none"}:
            raise RuntimeError("Video politikasi worker tarafindan reddedildi.")
        images = [item for item in (preview.get("images") or []) if item.get("id") in set(image_ids)]
        job_root = product_upload_dir(product_id) / "media_replacements" / job_id
        validate_existing_media_preview(product_id, preview, job_root)
        protected_ids = {
            item.get("id") for item in (preview.get("images") or []) if bool(item.get("protected"))
        }
        if not protected_ids.issubset(set(image_ids)):
            raise RuntimeError("Korunan sabit görseller worker aşamasında eksik; Etsy yazması engellendi.")
        required_ids = {
            item.get("id") for item in (preview.get("images") or []) if bool(item.get("required"))
        }
        if not required_ids.issubset(set(image_ids)):
            raise RuntimeError("Ana gorsel worker asamasinda eksik; Etsy yazmasi engellendi.")
        if not any(not bool(item.get("protected")) for item in images):
            raise RuntimeError("Seçili Photoshop mockup bulunamadı; Etsy yazması engellendi.")

        current_video_signatures = sorted(
            etsy_video_signature(item) for item in fetch_etsy_listing_videos(listing_id, settings)
        )
        if current_video_signatures != expected_video_signatures:
            raise RuntimeError("Etsy video durumu onizlemeden sonra degisti; gorsellere dokunulmadi.")
        update_media_replacement_job(job_id, stage="Yeni gorseller Etsy'ye yukleniyor", progress=28)
        uploaded_image_ids = set()
        for rank, item in enumerate(images[:ETSY_MAX_IMAGE_COUNT], start=1):
            response = upload_replacement_image(Path(item["path"]), product_id, listing_id, rank, settings)
            image_id = clean_text(str(response.get("listing_image_id") or ""))
            if not image_id:
                raise RuntimeError(f"Etsy yuklenen {rank}. gorsel icin image ID dondurmedi; guvenli silme yapilmadi.")
            uploaded_image_ids.add(image_id)
            update_media_replacement_job(job_id, progress=28 + int(rank / max(1, len(images)) * 40))

        if len(uploaded_image_ids) != len(images):
            raise RuntimeError("Yuklenen gorsel kimlikleri eksik; eski medya silinmedi.")

        current_images = fetch_etsy_listing_images(listing_id, settings)
        for image in current_images:
            image_id = clean_text(str(image.get("listing_image_id") or ""))
            if image_id and image_id not in uploaded_image_ids:
                delete_etsy_listing_media(listing_id, image_id, "image", settings)

        current_video_signatures = sorted(
            etsy_video_signature(item) for item in fetch_etsy_listing_videos(listing_id, settings)
        )
        if any(not signature for signature in current_video_signatures):
            raise RuntimeError("Guvenlik kontrolu: Etsy video kimligi okunamadi.")
        video_result = "yok"
        if video_action == "preserve":
            if current_video_signatures != expected_video_signatures:
                raise RuntimeError("Guvenlik kontrolu: mevcut Etsy videosu degisti; islem durduruldu.")
            video_result = "korundu"
        elif video_action == "create":
            if current_video_signatures:
                raise RuntimeError("Etsy'ye bu sirada baska bir video eklendi; ikinci video yuklenmedi.")
            update_media_replacement_job(job_id, stage="Eksik Etsy videosu yukleniyor", progress=75)
            upload_replacement_video(Path(videos[0]["path"]), listing_id, settings)
            created_video_signatures: list[str] = []
            for _attempt in range(12):
                created_video_signatures = sorted(
                    etsy_video_signature(item) for item in fetch_etsy_listing_videos(listing_id, settings)
                )
                if created_video_signatures and all(created_video_signatures):
                    break
                time.sleep(2)
            if not created_video_signatures or any(not signature for signature in created_video_signatures):
                raise RuntimeError("Yeni Etsy videosu yuklendi ancak dogrulanamadi.")
            video_result = "olusturuldu"

        update_media_replacement_job(job_id, stage="Etsy medyasi dogrulaniyor", progress=90)
        verified = False
        last_images = []
        for _attempt in range(6):
            last_images = fetch_etsy_listing_images(listing_id, settings)
            current_ids = {clean_text(str(item.get("listing_image_id") or "")) for item in last_images}
            if len(last_images) == len(images) and (not uploaded_image_ids or uploaded_image_ids.issubset(current_ids)):
                verified = True
                break
            time.sleep(2)
        if not verified:
            raise RuntimeError(f"Etsy dogrulamasi basarisiz: beklenen {len(images)}, okunan {len(last_images)} gorsel.")

        skip_inventory_update = bool(preview.get("skip_inventory_update"))
        if skip_inventory_update:
            inventory = {"skipped": True, "enabled_products_count": 0, "products_count": 0}
        else:
            update_media_replacement_job(job_id, stage="Varyasyonlar Etsy'ye gonderiliyor", progress=94)
            inventory = with_retry(
                product_id,
                "etsy_draft",
                settings,
                "etsy.updateListingInventory.mediaApply",
                lambda: update_etsy_inventory(product_id, listing_id, get_settings(), allow_existing=True),
            )
            add_event(
                product_id,
                "info",
                (
                    "Etsy varyasyonlari guncellendi: "
                    f"{inventory['enabled_products_count']} aktif / {inventory['products_count']} kombinasyon."
                ),
                "etsy_draft",
                meta=inventory,
            )

        sync_etsy_listing_media(product_id, listing_id, settings, fetch_remote=True)
        if bool(preview.get("skip_digital_delivery")):
            digital_export = ""
            digital_delivery = {"skipped": True}
        else:
            digital_export = export_updated_digital_artwork(product_id, preview)
            update_product(product_id, source_image_path=job["source_path"])
            digital_delivery = prepare_and_sync_digital_delivery(product_id, job["source_path"], settings)
        update_media_replacement_job(
            job_id,
            status="done",
            stage="Etsy medyasi guvenle guncellendi",
            progress=100,
            applied_at=now_iso(),
        )
        add_event(
            product_id,
            "done",
            (
                f"Mevcut Etsy urunu guncellendi: {len(images)} gorsel; video {video_result}; "
                + (
                    "varyasyonlara dokunulmadi."
                    if inventory.get("skipped")
                    else f"{inventory['enabled_products_count']} aktif varyasyon."
                )
            ),
            "media_replace_apply",
            meta={
                "job_id": job_id,
                "listing_id": listing_id,
                "digital_export": str(digital_export),
                "digital_delivery": digital_delivery,
                "inventory": inventory,
            },
        )
        queue_item_id = clean_text(preview.get("bulk_queue_item_id") or "")
        if queue_item_id:
            update_existing_mockup_queue_item(queue_item_id, status="done", error=None)
    except Exception as exc:
        message = readable_exception(exc)
        update_media_replacement_job(job_id, status="error", stage="Islem tamamlanamadi", error=message)
        try:
            with db() as conn:
                failed_job = conn.execute(
                    "SELECT preview_json FROM media_replacement_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()
            failed_preview = json.loads(failed_job["preview_json"] or "{}") if failed_job else {}
            queue_item_id = clean_text(failed_preview.get("bulk_queue_item_id") or "")
            if queue_item_id:
                update_existing_mockup_queue_item(queue_item_id, status="error", error=message)
        except Exception:
            pass
    finally:
        with media_replacement_lock:
            media_replacement_threads.pop(job_id, None)


def create_variant(product_id: str, payload: dict) -> dict:
    kind = clean_text(payload.get("kind") or "unframed").lower()
    if kind not in {"framed", "unframed", "digital"}:
        kind = "unframed"
    size = clean_text(payload.get("size_label") or ("DigitalDownload" if kind == "digital" else ""))
    if not size:
        raise ValueError("Boyut bos olamaz.")
    frame = clean_text(payload.get("frame_label") or "")
    if kind == "unframed":
        frame = ""
    product_cost = parse_money(payload.get("product_cost_usd"))
    shipping = parse_money(payload.get("shipping_cost_usd"))
    total = parse_money(payload.get("cost_usd")) or round(product_cost + shipping, 2)
    markup = float(payload.get("markup_percent") or 0)
    sale = parse_money(payload.get("sale_price_usd"))
    if sale <= 0:
        settings = get_settings()
        sale = resolved_variant_price(kind, size, total, markup, settings["pricing_formula"], 1, settings)
    quantity = int(float(payload.get("quantity") or get_settings()["default_quantity"]))
    visible = 1 if payload.get("visible", True) else 0
    orientation = normalize_orientation(clean_text(payload.get("orientation_label") or ""))
    ts = now_iso()
    with db() as conn:
        row = conn.execute("SELECT COALESCE(MAX(source_row), 0) + 1 AS next_row FROM variants WHERE product_id=?", (product_id,)).fetchone()
        source_row = int(row["next_row"] or 1)
        conn.execute(
            """
            INSERT INTO variants(id, product_id, kind, size_label, frame_label, orientation_label, sku, source_row,
                                 cost_usd, product_cost_usd, shipping_cost_usd, markup_percent,
                                 sale_price_usd, profit_usd, profit_margin_percent, quantity,
                                 visible, locked, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                product_id,
                kind,
                size,
                frame,
                orientation,
                clean_text(payload.get("sku") or variant_sku(product_id, kind, size, frame, source_row)),
                source_row,
                total,
                product_cost,
                shipping,
                markup,
                sale,
                round(sale - total, 2),
                profit_margin(total, sale),
                quantity,
                visible,
                ts,
                ts,
            ),
        )
    add_event(product_id, "edit", f"Varyasyon eklendi: {size} {frame}".strip(), "variants")
    return product_payload(product_id)


def update_variant(product_id: str, variant_id: str, payload: dict) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM variants WHERE id=? AND product_id=?", (variant_id, product_id)).fetchone()
    if not row:
        raise ValueError("Varyasyon bulunamadi.")
    kind = clean_text(payload.get("kind") or row["kind"]).lower()
    if kind not in {"framed", "unframed", "digital"}:
        kind = row["kind"]
    size = clean_text(payload.get("size_label") or row["size_label"])
    frame = clean_text(payload.get("frame_label") or "")
    if kind == "unframed":
        frame = ""
    if kind == "digital":
        size = size or "DigitalDownload"
        frame = ""
    product_cost = parse_money(payload.get("product_cost_usd")) if "product_cost_usd" in payload else float(row["product_cost_usd"] or 0)
    shipping = parse_money(payload.get("shipping_cost_usd")) if "shipping_cost_usd" in payload else float(row["shipping_cost_usd"] or 0)
    total = parse_money(payload.get("cost_usd")) if "cost_usd" in payload else round(product_cost + shipping, 2)
    if total <= 0 and kind != "digital":
        total = round(product_cost + shipping, 2)
    markup = float(payload.get("markup_percent") if payload.get("markup_percent") is not None else row["markup_percent"] or 0)
    sale = parse_money(payload.get("sale_price_usd")) if "sale_price_usd" in payload else float(row["sale_price_usd"] or 0)
    if sale <= 0 and kind != "digital":
        settings = get_settings()
        sale = resolved_variant_price(kind, size, total, markup, settings["pricing_formula"], 1, settings)
    quantity = int(float(payload.get("quantity") if payload.get("quantity") is not None else row["quantity"] or get_settings()["default_quantity"]))
    visible = 1 if payload.get("visible", bool(row["visible"])) else 0
    orientation = normalize_orientation(clean_text(payload.get("orientation_label") if payload.get("orientation_label") is not None else row["orientation_label"] or ""))
    sku = clean_text(payload.get("sku") or row["sku"] or variant_sku(product_id, kind, size, frame, int(row["source_row"] or 0)))
    with db() as conn:
        conn.execute(
            """
            UPDATE variants
            SET kind=?, size_label=?, frame_label=?, orientation_label=?, sku=?,
                cost_usd=?, product_cost_usd=?, shipping_cost_usd=?, markup_percent=?,
                sale_price_usd=?, profit_usd=?, profit_margin_percent=?, quantity=?,
                visible=?, updated_at=?
            WHERE id=? AND product_id=?
            """,
            (
                kind,
                size,
                frame,
                orientation,
                sku,
                total,
                product_cost,
                shipping,
                markup,
                sale,
                round(sale - total, 2),
                profit_margin(total, sale),
                quantity,
                visible,
                now_iso(),
                variant_id,
                product_id,
            ),
        )
    add_event(product_id, "edit", f"Varyasyon duzenlendi: {size} {frame}".strip(), "variants")
    return product_payload(product_id)


def push_bulk_product_inventory(product_id: str) -> dict:
    settings = get_settings()
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Urun bulunamadi.")
    listing_id = clean_text(product["listing_id"] or "")
    if not listing_id:
        raise ValueError("Etsy listing ID yok.")
    listing = fetch_etsy_listing_summary(listing_id, settings)
    listing_state = clean_text(str(listing.get("state") or "")).lower()
    if listing_state != "active":
        raise RuntimeError(f"Yalnizca active Etsy urunu guncellenebilir. Mevcut durum: {listing_state or 'bilinmiyor'}")
    update_product(product_id, status="running", current_step="etsy_draft", stop_requested=0)
    set_step(product_id, "etsy_draft", "running", 80)
    inventory = with_retry(
        product_id,
        "etsy_draft",
        settings,
        "etsy.singleUpdateListingInventory.only",
        lambda: update_etsy_inventory(product_id, listing_id, get_settings(), allow_existing=True),
    )
    add_event(product_id, "info", "Tek urun varyasyon/fiyat Etsy'ye yazildi.", "etsy_draft", meta=inventory)
    set_step(product_id, "etsy_draft", "done", 100)
    update_product(product_id, status="done", current_step="etsy_draft", overall_progress=100, etsy_fee_estimate_usd=0)
    return product_payload(product_id) | {"inventory": inventory}


def create_fresh_etsy_draft(product_id: str, product, seo_data: dict, settings: dict, reason: str = "") -> dict:
    if reason:
        add_event(product_id, "warning", reason, "etsy_draft")
    update_product(product_id, listing_id="")
    return create_etsy_draft(product_id, product, seo_data, get_settings())


def with_retry(product_id: str, step_key: str, settings: dict, endpoint: str, fn):
    attempts = int(settings["retry_max_attempts"])
    base_delay = float(settings["retry_base_delay_sec"])
    last_error = None
    for attempt in range(1, attempts + 1):
        check_stop(product_id)
        try:
            result = fn()
            if not (isinstance(result, dict) and result.get("_mock")):
                with db() as conn:
                    conn.execute(
                        "INSERT INTO api_calls(product_id, service, endpoint, status, attempt, created_at) VALUES(?, ?, ?, 'ok', ?, ?)",
                        (product_id, "external", endpoint, attempt, now_iso()),
                    )
                    conn.execute("UPDATE products SET api_calls=api_calls+1 WHERE id=?", (product_id,))
            return result
        except Exception as exc:
            error_text = readable_exception(exc)
            last_error = RuntimeError(error_text)
            increment_retry(product_id, step_key)
            with db() as conn:
                conn.execute(
                    """
                    INSERT INTO api_calls(product_id, service, endpoint, status, attempt, error, created_at)
                    VALUES(?, ?, ?, 'error', ?, ?, ?)
                    """,
                    (product_id, "external", endpoint, attempt, error_text, now_iso()),
                )
            add_event(
                product_id,
                "retry",
                f"{endpoint} hata verdi, deneme {attempt}/{attempts}: {error_text}",
                step_key,
            )
            if attempt < attempts:
                time.sleep(base_delay * attempt)
    raise last_error


def create_deterministic_seo(product_name: str, settings: dict, product_id: str | None = None, analysis: dict | None = None) -> dict:
    prohibited = settings["prohibited_terms"]
    analysis = analysis or {}
    figure = clean_text(str(analysis.get("public_figure_name") or ""))
    if figure.lower() == "unknown":
        figure = ""
    subject = remove_prohibited(figure or product_name, prohibited) or "Iconic Poster"
    if subject.lower() in {"yeni poster", "poster", "new poster", "yeni"}:
        subject = "Statement Wall Art"
    color_style = clean_text(str(analysis.get("dominant_style") or analysis.get("color_palette") or "Black White")).title()
    if len(color_style) > 28:
        color_style = "Black White"
    title = f"{subject} Poster, {color_style} Wall Art, Iconic Room Decor, Sports Room Art, Fan Gift"
    title = normalize_seo_title(title, product_name, analysis, settings)
    body = (
        f"Bring bold visual energy and collector-worthy presence to your walls with this {subject} poster. "
        "Designed with a striking gallery-print feel, the artwork gives your space a confident focal point without overwhelming the room.\n\n"
        "This piece works beautifully in a sports room, home gym, bedroom, office, studio, or gallery wall. "
        "It also makes a thoughtful gift for fans who love iconic, conversation-starting wall art."
    )
    description = build_description_template(
        product_id,
        body,
        [
            f"{subject} poster",
            f"{subject} wall art",
            "basketball wall art",
            "sports room decor",
            "gym wall poster",
            "black white poster",
            "fan gift artwork",
            "gallery wall print",
        ],
    )
    tags = safe_tags(
        [
            f"{subject} poster",
            f"{subject} print",
            "wall art print",
            "modern poster",
            "room decor",
            "gift for fan",
            "gallery wall",
            "office decor",
            "bedroom decor",
            "unframed print",
            "framed poster",
            "digital poster",
            "art print",
        ],
        prohibited,
    )
    return {"title": title, "description_intro": description, "description": description, "description_tail": "", "tags": tags, "warnings": []}


def trim_title_to_etsy_limit(title: str, limit: int = 140) -> str:
    title = clean_text(title).strip(" ,")
    if len(title) <= limit:
        return title
    parts = [part.strip() for part in title.split(",") if part.strip()]
    kept: list[str] = []
    for part in parts:
        candidate = ", ".join([*kept, part])
        if len(candidate) <= limit:
            kept.append(part)
    if kept:
        return ", ".join(kept).strip(" ,")
    return title[:limit].rstrip(" ,")


def normalize_seo_title(raw_title: str, product_name: str, analysis: dict | None, settings: dict) -> str:
    prohibited = settings["prohibited_terms"]
    analysis = analysis or {}
    title = remove_prohibited(clean_text(raw_title), prohibited)
    if 115 <= len(title) <= 140:
        return title

    figure = clean_text(str(analysis.get("public_figure_name") or ""))
    if figure.lower() == "unknown":
        figure = ""
    keywords = analysis.get("subject_keywords") if isinstance(analysis.get("subject_keywords"), list) else []
    subject = figure or clean_text(str(analysis.get("primary_subject") or "")) or product_name
    raw_first = clean_text(title.split(",", 1)[0] if title else "")
    raw_subject = clean_text(re.sub(r"\bposter\b$", "", raw_first, flags=re.IGNORECASE))
    if not subject or subject.lower() in {"yeni poster", "poster", "new poster", "yeni"}:
        subject = raw_subject or clean_text(" ".join(str(item) for item in keywords[:2])) or "Statement Wall Art"
    subject = remove_prohibited(subject, prohibited) or "Statement Wall Art"

    haystack = " ".join(
        [
            subject,
            clean_text(str(analysis.get("visual_style") or "")),
            clean_text(str(analysis.get("dominant_style") or "")),
            clean_text(str(analysis.get("color_palette") or "")),
            " ".join(str(item) for item in keywords[:6]),
        ]
    ).lower()
    if any(word in haystack for word in ["music", "singer", "pop", "dance", "concert", "michael jackson"]):
        parts = [
            f"{subject} Poster",
            "Black White Music Wall Art",
            "Iconic Dance Decor",
            "Music Room Print",
            "Pop Legend Fan Gift",
            "Gallery Poster",
        ]
    elif any(word in haystack for word in ["basketball", "sports", "gym", "athlete", "jordan"]):
        parts = [
            f"{subject} Poster",
            "Black White Basketball Wall Art",
            "Iconic Gym Decor",
            "Sports Room Art",
            "Basketball Fan Gift",
            "Gallery Poster",
        ]
    else:
        style = clean_text(str(analysis.get("dominant_style") or analysis.get("color_palette") or "Modern")).title()
        if len(style) > 24:
            style = "Modern"
        parts = [
            f"{subject} Poster",
            f"{style} Wall Art Print",
            "Iconic Room Decor",
            "Gallery Wall Poster",
            "Bedroom Office Art",
            "Thoughtful Fan Gift",
        ]

    candidate = remove_prohibited(", ".join(parts), prohibited)
    extras = ["Premium Wall Decor", "Collector Print", "Home Gallery Art"]
    for extra in extras:
        if len(candidate) >= 120:
            break
        next_candidate = f"{candidate}, {extra}"
        if len(next_candidate) <= 140:
            candidate = next_candidate
    if len(candidate) < 105 and title:
        merged = f"{candidate}, {title}"
        if len(merged) <= 140:
            candidate = merged
    return trim_title_to_etsy_limit(candidate, 140)


def create_seo_from_analysis(product_name: str, analysis: dict, settings: dict, product_id: str | None = None) -> dict:
    prohibited = settings["prohibited_terms"]
    figure = clean_text(str(analysis.get("public_figure_name") or ""))
    if figure.lower() == "unknown":
        figure = ""
    subject = figure or clean_text(str(analysis.get("primary_subject") or "")) or product_name
    keywords = analysis.get("subject_keywords") if isinstance(analysis.get("subject_keywords"), list) else []
    if not subject or subject.lower() in {"yeni poster", "poster", "new poster", "yeni"}:
        subject = clean_text(" ".join(str(item) for item in keywords[:2])) or "Statement Wall Art"
    subject = remove_prohibited(subject, prohibited)
    seo = create_deterministic_seo(subject, settings, product_id, analysis)
    warnings = []
    if analysis.get("ip_risk_warnings"):
        warnings.extend(str(item) for item in analysis.get("ip_risk_warnings")[:4])
    if not figure:
        warnings.append("Belirgin public figure adı bulunmadı; yerel SEO şablonu kullanıldı.")
    seo["warnings"] = warnings
    return seo


def seo_output_for_product(product_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM seo_outputs WHERE product_id=?", (product_id,)).fetchone()
    if not row:
        return None
    return {
        "title": clean_text(row["title"]),
        "description_intro": clean_multiline_text(row["description_intro"]),
        "description": clean_multiline_text(row["description_intro"]),
        "description_tail": clean_multiline_text(row["description_tail"]),
        "tags": json.loads(row["tags_json"] or "[]"),
        "warnings": json.loads(row["warnings_json"] or "[]"),
    }


def seo_image_data_url(source_path: str | Path) -> str:
    from PIL import Image, ImageOps

    with Image.open(source_path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def new_product_seo_prompt(product_id: str, product) -> str:
    with db() as conn:
        sizes = [
            row["size_label"]
            for row in conn.execute(
                """
                SELECT size_label, MIN(sale_price_usd) AS price
                FROM variants
                WHERE product_id=? AND visible=1 AND kind IN ('framed', 'unframed')
                GROUP BY size_label ORDER BY price, size_label
                """,
                (product_id,),
            ).fetchall()
        ]
    size_text = " | ".join(sizes[:30]) or "Use only sizes visible in the listing variations."
    return f"""
Analyze the supplied poster artwork and create Etsy SEO copy in English. Return one JSON object only with keys title, description, and tags.

TITLE RULES
- Follow this ordering: main subject + Poster, visual style/color + Wall Art, room/use decor, collector/fan gift.
- Example structure: Michael Jordan Shot Poster, Black White Basketball Wall Art, Iconic Gym Decor, Sports Room Art, Basketball Fan Gift.
- Make the title natural, specific to the actual image, and 115-140 characters including spaces.
- Do not invent a person, place, team, event, text, or object that is not clearly visible.

TAGS
- Exactly 13 buyer-search phrases, each at most 20 characters, no duplicates.
- Use phrases that accurately match the image and likely search intent.

DESCRIPTION
- Start with two warm, image-specific paragraphs describing subject, palette, style, mood, rooms, and gift use.
- Add a 'Perfect for those searching for:' section with 6-8 bullet phrases.
- Add an 'Available Sizes' section. Include Digital Download (+9K) and these physical variation labels: {size_text}
- Add 'Premium Unframed Poster Details': semi-glossy 170 gsm paper, 0.19 mm thickness, high-resolution print, FSC-certified or equivalent, print-on-demand.
- Add 'Premium Wooden Framed Poster Details': ready-to-hang kit; durable pine wood; black, white, natural, and dark brown wood colors; 20-25 mm thick and 10-14 mm wide frame; 170 gsm semi-glossy paper; shatterproof plexiglass; FSC-certified or equivalent.
- Add 'Packaging & Delivery': protective packaging, damage resistance, and estimated delivery after dispatch without promising an unverified dispatch time.
- Add 'Important Notes': available framed, unframed, and digital; mockup accessories are not included; colors may vary by monitor; personal use only; the shop owner’s copyright line.
- Do not include Markdown links and do not claim the framed item is unframed.

Panel product name: {clean_text(product['name'])}
Selection category: {clean_text(product['selection_name'] if 'selection_name' in product.keys() else '')}
""".strip()


def minimal_etsy_copy() -> dict:
    return {
        "title": "Poster",
        "description": "Poster",
        "description_intro": "Poster",
        "description_tail": "",
        "tags": [],
        "warnings": [],
    }


def js_string(value: str | Path) -> str:
    return json.dumps(str(value).replace("\\", "/"), ensure_ascii=False)


def external_two_k_done_dir(settings: dict) -> Path:
    return DATA / "workflow" / "prepared"


def external_ready_dir(settings: dict) -> Path:
    return DATA / "workflow" / "ready"


def external_psd_dir(settings: dict) -> Path:
    return selection_mockup_root(settings) / SELECTION_NAMES[0] / "mockups"


def expected_external_mockup_count(settings: dict, only_psd_stems: list[str] | None = None) -> int:
    if only_psd_stems:
        return len(only_psd_stems)
    psd_dir = external_psd_dir(settings)
    if psd_dir.exists():
        count = len([path for path in psd_dir.iterdir() if path.is_file() and path.suffix.lower() == ".psd"])
        if count > 0:
            return count
    configured = int(settings.get("expected_mockup_count") or 0)
    return configured or EXPECTED_EXTERNAL_MOCKUP_COUNT


def external_ready_folder_name_for_prepared_image(prepared_image: Path) -> str:
    stem = prepared_image.stem
    suffix = "_2k_3x4"
    if stem.lower().endswith(suffix):
        stem = stem[: -len(suffix)]
    return slugify_filename(stem, stem)


def photoshop_prepare_jsx(source: Path, output: Path, status: Path) -> str:
    return f"""#target photoshop
app.displayDialogs = DialogModes.NO;
var sourceFile = new File({js_string(source)});
var outputFile = new File({js_string(output)});
var statusFile = new File({js_string(status)});

function writeStatus(payload) {{
    function escapeJson(value) {{
        return String(value)
            .replace(/\\\\/g, "\\\\\\\\")
            .replace(/"/g, '\\\\"')
            .replace(/\\r/g, "\\\\r")
            .replace(/\\n/g, "\\\\n");
    }}
    statusFile.encoding = "UTF8";
    statusFile.open("w");
    statusFile.write(
        '{{"ok":' + (payload.ok ? "true" : "false") +
        ',"error":"' + escapeJson(payload.error || "") +
        '","output":"' + escapeJson(payload.output || "") + '"}}'
    );
    statusFile.close();
}}

try {{
    if (!sourceFile.exists) throw new Error("Source image not found: " + sourceFile.fsName);
    outputFile.parent.create();
    var doc = app.open(sourceFile);
    app.activeDocument = doc;
    try {{ doc.bitsPerChannel = BitsPerChannelType.EIGHT; }} catch (ignoreBits) {{}}
    try {{ doc.changeMode(ChangeMode.RGB); }} catch (ignoreMode) {{}}

    var widthPx = doc.width.as("px");
    var heightPx = doc.height.as("px");
    var targetRatio = 3 / 4;
    var currentRatio = widthPx / heightPx;
    if (Math.abs(currentRatio - targetRatio) > 0.001) {{
        if (currentRatio > targetRatio) {{
            var newWidth = heightPx * targetRatio;
            var left = (widthPx - newWidth) / 2;
            doc.crop([UnitValue(left, "px"), UnitValue(0, "px"), UnitValue(left + newWidth, "px"), UnitValue(heightPx, "px")]);
        }} else {{
            var newHeight = widthPx / targetRatio;
            var top = (heightPx - newHeight) / 2;
            doc.crop([UnitValue(0, "px"), UnitValue(top, "px"), UnitValue(widthPx, "px"), UnitValue(top + newHeight, "px")]);
        }}
    }}

    try {{ app.preferences.interpolation = ResampleMethod.PRESERVEDETAILS; }} catch (ignorePref) {{}}
    try {{
        doc.resizeImage(UnitValue(3000, "px"), UnitValue(4000, "px"), 300, ResampleMethod.PRESERVEDETAILS);
    }} catch (resizeErr) {{
        doc.resizeImage(UnitValue(3000, "px"), UnitValue(4000, "px"), 300, ResampleMethod.BICUBICSMOOTHER);
    }}
    try {{ doc.activeLayer.applyUnSharpMask(60, 1.0, 2); }} catch (ignoreSharpen) {{}}

    var opts = new PNGSaveOptions();
    opts.compression = 6;
    opts.interlaced = false;
    doc.saveAs(outputFile, opts, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    writeStatus({{ok: true, output: outputFile.fsName, width: 3000, height: 4000}});
}} catch (err) {{
    try {{ if (app.documents.length > 0) app.activeDocument.close(SaveOptions.DONOTSAVECHANGES); }} catch (closeErr) {{}}
    writeStatus({{ok: false, error: String(err)}});
}}
"""


def launch_photoshop_jsx(photoshop: Path, script_path: Path) -> subprocess.Popen:
    photoshop_ps = str(photoshop).replace("'", "''")
    script_ps = str(script_path).replace("'", "''")
    command = f"""
$ErrorActionPreference = 'Stop'
if (-not (Get-Process Photoshop -ErrorAction SilentlyContinue)) {{
    Start-Process -FilePath '{photoshop_ps}' -WindowStyle Hidden
}}
$deadline = (Get-Date).AddSeconds(150)
$app = $null
while ((Get-Date) -lt $deadline -and $null -eq $app) {{
    try {{
        $app = New-Object -ComObject Photoshop.Application
    }} catch {{
        Start-Sleep -Seconds 2
    }}
}}
if ($null -eq $app) {{ throw 'Photoshop otomasyon arayuzu hazir olmadi.' }}
$app.DoJavaScriptFile('{script_ps}')
"""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def run_photoshop_prepare(
    product_id: str,
    source_image_path: str,
    settings: dict,
    target_suffix: str = "",
    step_key: str = "photoshop_prepare",
    check_product_stop: bool = True,
    queue_item_id: str = "",
) -> Path:
    source = assert_artwork_source_safe(Path(source_image_path.strip('"')), product_id)
    photoshop = Path(settings.get("photoshop_exe_path") or "")
    if not photoshop.exists():
        raise FileNotFoundError(f"Photoshop.exe bulunamadı: {photoshop}")

    two_k_dir = external_two_k_done_dir(settings)
    two_k_dir.mkdir(parents=True, exist_ok=True)
    suffix = slugify_filename(target_suffix, "").strip("-_.")
    suffix_part = f"_{suffix}" if suffix else ""
    target_name = f"{product_folder_name(product_id)}{suffix_part}_2k_3x4.png"
    target = two_k_dir / target_name
    work_dir = product_upload_dir(product_id) / "photoshop_prepare"
    work_dir.mkdir(parents=True, exist_ok=True)
    status_path = work_dir / f"prepare-status{suffix_part}.json"
    script_path = work_dir / f"CodexPrepareArtwork{suffix_part}.jsx"
    script_path.write_text(photoshop_prepare_jsx(source, target, status_path), encoding="utf-8-sig")
    if target.exists():
        target.unlink()
    if status_path.exists():
        status_path.unlink()

    photoshop_process = launch_photoshop_jsx(photoshop, script_path)
    add_event(product_id, "info", "Photoshop açıldı; 3:4 ve 4K hazırlık scripti çalışıyor.", step_key, meta={"script": str(script_path), "target": str(target)})

    timeout = max(180, min(300, int(settings.get("photoshop_prepare_timeout_sec") or 240)))
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if check_product_stop:
                check_stop(product_id)
            if existing_queue_item_cancelled(queue_item_id):
                raise StopJob()
            if status_path.exists():
                status = read_json_file(status_path, {}) if status_path.stat().st_size > 0 else {}
                if status.get("ok") and target.exists() and target.stat().st_size > 0:
                    wait_for_stable_file(target, stable_checks=2, interval=0.5, timeout=20)
                    if photoshop_process.poll() is None:
                        photoshop_process.terminate()
                        try:
                            photoshop_process.wait(timeout=8)
                        except subprocess.TimeoutExpired:
                            photoshop_process.kill()
                    add_event(product_id, "info", "Photoshop hazırlık görseli tamamlandı.", step_key, meta={"output": str(target)})
                    return target
                if status.get("ok") is False:
                    raise RuntimeError(f"Photoshop hazırlık hatası: {status.get('error')}")
            time.sleep(2)
        raise TimeoutError("Photoshop 3:4/4K hazırlık çıktısı 120 saniyede oluşmadı.")
    except Exception:
        terminate_photoshop_processes()
        raise


def normalize_mockup_stem(value: str) -> str:
    return re.sub(r"\s+", " ", clean_text(value).lower())


def collect_external_outputs(
    product_id: str,
    ready_folder: Path,
    source_name: str,
    only_psd_stems: list[str] | None = None,
    not_before: float = 0,
) -> dict:
    source_stem = Path(source_name).stem.lower()
    allowed = {normalize_mockup_stem(item) for item in (only_psd_stems or []) if clean_text(item)}
    mockups = []
    videos = find_external_videos(ready_folder, not_before=not_before)
    for path in sorted(ready_folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        if not_before and path.stat().st_mtime < not_before - 1:
            continue
        lower = path.name.lower()
        if lower == source_name.lower():
            continue
        if path.suffix.lower() == ".png" and source_stem in path.stem.lower():
            if allowed and not any(normalize_mockup_stem(stem) in normalize_mockup_stem(path.stem) for stem in allowed):
                continue
            mockups.append(path)
    mockups.sort(key=mockup_order_key)
    return {"mockups": mockups, "videos": videos}


def find_external_videos(ready_folder: Path, not_before: float = 0) -> list[Path]:
    if not ready_folder or not ready_folder.exists():
        return []
    videos = []
    for path in sorted(ready_folder.iterdir(), key=lambda item: item.name.lower()):
        if (
            path.is_file()
            and path.stat().st_size > 0
            and path.suffix.lower() in {".mp4", ".mov", ".gif"}
            and (not not_before or path.stat().st_mtime >= not_before - 1)
        ):
            videos.append(path)
    return videos


def wait_for_stable_file(path: Path, stable_checks: int = 3, interval: float = 1.0, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    stable = 0
    previous_size = -1
    while time.time() < deadline:
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > 0 and size == previous_size:
                stable += 1
                if stable >= stable_checks:
                    return
            else:
                stable = 0
                previous_size = size
        time.sleep(interval)
    raise TimeoutError(f"Dosya yazimi tamamlanmadi veya sabitlenmedi: {path}")


def bundled_ffmpeg_path() -> Path | None:
    try:
        import imageio_ffmpeg

        packaged = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if packaged.exists():
            return packaged
    except Exception:
        pass
    executable = shutil.which("ffmpeg")
    return Path(executable) if executable else None


def video_file_is_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 64 * 1024:
        return False
    ffmpeg = bundled_ffmpeg_path()
    if ffmpeg:
        result = subprocess.run(
            [str(ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "NUL"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    raw = path.read_bytes()
    return b"ftyp" in raw[:64] and b"moov" in raw


def wait_for_valid_video_file(path: Path, timeout: float = 180.0, product_id: str = "") -> None:
    deadline = time.time() + timeout
    last_size = -1
    stable = 0
    while time.time() < deadline:
        if product_id:
            check_stop(product_id)
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size == last_size:
                stable += 1
            else:
                stable = 0
                last_size = size
            if stable >= 2 and video_file_is_valid(path):
                return
        time.sleep(2)
    raise TimeoutError(f"Video dosyasi tamamlanmadi veya Etsy uyumlu MP4 degil: {path}")


def stop_photoshop_automation_processes(markers: list[str], wait_seconds: float = 4.0) -> None:
    if not markers:
        return
    ps_script = (
        "$markers = @("
        + ",".join(json.dumps(marker) for marker in markers)
        + "); "
        "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'Photoshop*' -and $_.CommandLine }; "
        "foreach ($proc in $procs) { "
        "$hit = $false; "
        "foreach ($m in $markers) { if ($proc.CommandLine -like ('*' + $m + '*')) { $hit = $true } } "
        "if ($hit) { Stop-Process -Id $proc.ProcessId -Force } "
        "}"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=10)
        time.sleep(wait_seconds)
    except Exception:
        pass


def terminate_photoshop_processes(wait_seconds: float = 1.0) -> None:
    """Terminate Photoshop only when the panel explicitly stops or times out."""
    ps_script = (
        "$procs = Get-Process | Where-Object { $_.ProcessName -like 'Photoshop*' }; "
        "foreach ($proc in $procs) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        time.sleep(max(0.0, wait_seconds))
    except Exception:
        pass


def copy_external_assets(
    product_id: str,
    outputs: dict,
    clear_existing: bool = True,
    artwork_option_id: str | None = None,
    sort_offset: int = 0,
) -> dict:
    if clear_existing:
        clear_assets(product_id, "mockup")
        clear_assets(product_id, "video")
    mockup_dir = product_upload_dir(product_id) / "mockups"
    mockup_dir.mkdir(parents=True, exist_ok=True)
    copied_mockups = 0
    for idx, path in enumerate(outputs["mockups"], start=1):
        sort_order = sort_offset + idx
        target = mockup_dir / f"{sort_order:02d}-{slugify_filename(path.name, 'mockup.png')}"
        shutil.copy2(path, target)
        primary_thumbnail = idx == 1
        if primary_thumbnail:
            validate_primary_thumbnail_image(target)
        add_asset(
            product_id,
            "mockup",
            path.stem,
            target,
            sort_order,
            artwork_option_id=artwork_option_id,
            role="primary_thumbnail" if primary_thumbnail else "mockup",
        )
        copied_mockups += 1
    copied_videos = copy_external_video_assets(product_id, outputs.get("videos") or [], clear_existing=False) if clear_existing else 0
    return {"mockups": copied_mockups, "videos": copied_videos}


def copy_external_video_assets(product_id: str, videos: list[Path], clear_existing: bool = True) -> int:
    if clear_existing:
        clear_assets(product_id, "video")
    video_dir = product_upload_dir(product_id) / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    copied_videos = 0
    for idx, path in enumerate(videos, start=1):
        wait_for_valid_video_file(path)
        target = video_dir / slugify_filename(path.name, "vertical.mp4")
        shutil.copy2(path, target)
        add_asset(product_id, "video", path.stem, target, idx)
        copied_videos += 1
    return copied_videos


def latest_external_ready_folder_for_product(product_id: str, settings: dict) -> Path | None:
    ready_dir = external_ready_dir(settings)
    if not ready_dir.exists():
        return None
    prefix = product_folder_name(product_id).lower()
    candidates: list[Path] = []
    for folder in ready_dir.iterdir():
        if not folder.is_dir():
            continue
        try:
            if any(child.is_file() and child.name.lower().startswith(prefix) for child in folder.iterdir()):
                candidates.append(folder)
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def sync_external_video_asset(product_id: str, ready_folder: str | Path | None, settings: dict, timeout: int | None = None) -> int:
    folder = Path(ready_folder) if ready_folder else latest_external_ready_folder_for_product(product_id, settings)
    if not folder or not folder.exists():
        return 0
    deadline = time.time() + int(timeout if timeout is not None else settings.get("video_wait_timeout_sec") or 420)
    last_seen = 0
    while time.time() < deadline:
        check_stop(product_id)
        videos = find_external_videos(folder)
        if videos:
            try:
                copied = copy_external_video_assets(product_id, videos, clear_existing=True)
            except Exception as exc:
                add_event(product_id, "warning", "Photoshop videosu bulundu ama kaydedilemedi.", "video_mockup", meta={"error": readable_exception(exc), "folder": str(folder)})
                return 0
            if copied:
                add_event(product_id, "info", f"Gec gelen Photoshop videosu kaydedildi: {copied} video.", "video_mockup", meta={"folder": str(folder)})
            return copied
        if last_seen == 0:
            add_event(product_id, "info", "Photoshop video export bekleniyor.", "video_mockup", meta={"folder": str(folder)})
            last_seen = 1
        time.sleep(5)
    return 0


def create_local_mp4_video_preview(product_id: str, source_image_path: str | None = None) -> dict | None:
    # A static image wrapped in MP4 is not a product video. This path is permanently disabled.
    add_event(
        product_id,
        "warning",
        "Photoshop/Adobe Media Encoder videosu yok; statik gorselden MP4 uretilmeyecek.",
        "video_mockup",
    )
    return None

    ffmpeg = bundled_ffmpeg_path()
    if not ffmpeg:
        add_event(product_id, "warning", "MP4 fallback için ffmpeg bulunamadı.", "video_mockup")
        return None
    source_path = None
    with db() as conn:
        row = conn.execute(
            "SELECT path FROM assets WHERE product_id=? AND kind='mockup' ORDER BY sort_order LIMIT 1",
            (product_id,),
        ).fetchone()
    if row and Path(row["path"]).exists():
        source_path = Path(row["path"])
    elif source_image_path and Path(str(source_image_path).strip('"')).exists():
        source_path = Path(str(source_image_path).strip('"'))
    if not source_path:
        return None

    clear_assets(product_id, "video")
    target_dir = product_upload_dir(product_id) / "video"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "local-video-preview.mp4"
    command = [
        str(ffmpeg),
        "-y",
        "-loop",
        "1",
        "-t",
        "15",
        "-i",
        str(source_path),
        "-vf",
        "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(target),
    ]
    result = subprocess.run(command, text=True, capture_output=True, timeout=90)
    if result.returncode != 0 or not video_file_is_valid(target):
        add_event(
            product_id,
            "warning",
            "Yerel MP4 fallback video uretilemedi.",
            "video_mockup",
            meta={"stderr": result.stderr[-1200:], "stdout": result.stdout[-1200:]},
        )
        return None
    asset_id = add_asset(product_id, "video", "Local MP4 video preview", target, 1)
    add_event(product_id, "info", "Yerel MP4 video önizlemesi kaydedildi.", "video_mockup", meta={"path": str(target)})
    return {"id": asset_id, "label": "Local MP4 video preview", "path": str(target)}


def run_external_mockup_script(
    product_id: str,
    prepared_image: Path,
    settings: dict,
    only_psd_stems: list[str] | None = None,
    include_video: bool = True,
    clear_existing: bool = True,
    artwork_option_id: str | None = None,
    sort_offset: int = 0,
    psd_folder: Path | None = None,
    video_psd: Path | None = None,
    preview_output_dir: Path | None = None,
    track_product_progress: bool = True,
    check_product_stop: bool = True,
    queue_item_id: str = "",
) -> dict:
    project_dir = ROOT / "tools"
    workflow = project_dir / "mockup_workflow.py"
    if not workflow.exists():
        raise FileNotFoundError(f"Mockup çalıştırıcısı bulunamadı: {workflow}")
    ready_dir = external_ready_dir(settings)
    ready_dir.mkdir(parents=True, exist_ok=True)

    stop_photoshop_automation_processes(["CodexPrepareArtwork.jsx", "RunMockupBatchAuto.jsx"], wait_seconds=2.0)
    before = {path.resolve() for path in ready_dir.iterdir() if path.is_dir()}
    env = os.environ.copy()
    env["ETSY_V2_SMART_LAYER"] = str(get_settings().get("smart_object_layer") or "Kare 1")
    for key in ("CODEX_MOCKUP_SKIP_VIDEO", "CODEX_MOCKUP_VIDEO_PSD", "CODEX_MOCKUP_PSD_STEMS"):
        env.pop(key, None)
    source_name = prepared_image.name
    ready_folder_name = external_ready_folder_name_for_prepared_image(prepared_image)
    env["CODEX_MOCKUP_FOLDER_NAMES"] = ready_folder_name
    env["CODEX_MOCKUP_SOURCE_FILENAMES"] = source_name
    env["CODEX_MOCKUP_SOURCE_PATH"] = str(prepared_image)
    env["CODEX_MOCKUP_READY_DIR"] = str(ready_dir)
    env["CODEX_MOCKUP_BASE_JSX"] = str(
        ROOT / "tools" / "MockupBatchExport.jsx"
    )
    env["CODEX_PHOTOSHOP_EXE"] = str(
        Path(settings.get("photoshop_exe_path") or DEFAULT_SETTINGS["photoshop_exe_path"])
    )
    env["CODEX_MOCKUP_GENERATED_JSX"] = str(
        product_upload_dir(product_id) / "photoshop" / f"MockupBatch-{uuid.uuid4().hex}.jsx"
    )
    status_path = product_upload_dir(product_id) / "photoshop" / f"MockupBatch-{uuid.uuid4().hex}.status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.unlink(missing_ok=True)
    env["CODEX_MOCKUP_STATUS_FILE"] = str(status_path)
    env["CODEX_MOCKUP_FORCE"] = "1"
    if psd_folder:
        env["CODEX_MOCKUP_PSD_FOLDER"] = str(psd_folder)
    if video_psd:
        env["CODEX_MOCKUP_VIDEO_PSD"] = str(video_psd)
    if only_psd_stems:
        env["CODEX_MOCKUP_PSD_STEMS"] = "|".join(only_psd_stems)
    if not include_video:
        env["CODEX_MOCKUP_SKIP_VIDEO"] = "1"
    launch_started_at = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(workflow), "--open-photoshop"],
            cwd=str(project_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        terminate_photoshop_processes()
        raise TimeoutError("Photoshop mockup başlatıcısı 90 saniyede yanıt vermedi.")
    add_event(
        product_id,
        "info" if result.returncode == 0 else "warning",
        "Harici Etsy mockup scripti çalıştı.",
        "mockup_render",
        meta={
            "returncode": result.returncode,
            "stdout": result.stdout[-1200:],
            "stderr": result.stderr[-1200:],
            "ready_folder_filter": ready_folder_name,
            "source_file_filter": source_name,
        },
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Harici mockup scripti hata verdi.")

    ready_folder = None
    expected_ready_folder = ready_dir / ready_folder_name
    deadline = time.time() + 45
    while time.time() < deadline and ready_folder is None:
        if (check_product_stop and requested_stop(product_id)) or existing_queue_item_cancelled(queue_item_id):
            terminate_photoshop_processes()
            raise StopJob()
        if status_path.exists():
            status = read_json_file(status_path, {})
            if status.get("ok") is False:
                terminate_photoshop_processes()
                raise RuntimeError(f"Photoshop mockup hatası: {status.get('error')}")
        if expected_ready_folder.exists() and expected_ready_folder.is_dir():
            if any(
                child.is_file()
                and child.name.lower() == source_name.lower()
                for child in expected_ready_folder.iterdir()
            ):
                ready_folder = expected_ready_folder
                break
        for folder in ready_dir.iterdir():
            if not folder.is_dir():
                continue
            if any(
                child.is_file()
                and child.name.lower() == source_name.lower()
                and child.stat().st_mtime >= launch_started_at - 1
                for child in folder.iterdir()
            ):
                ready_folder = folder
                break
        if ready_folder is None:
            new_dirs = [path for path in ready_dir.iterdir() if path.is_dir() and path.resolve() not in before]
            for folder in new_dirs:
                if any(
                    child.is_file()
                    and child.suffix.lower() in {".png", ".jpg", ".jpeg"}
                    and child.stat().st_mtime >= launch_started_at - 1
                    for child in folder.iterdir()
                ):
                    ready_folder = folder
                    break
        if ready_folder is None:
            time.sleep(1)
    if ready_folder is None:
        raise TimeoutError("Harici script hazır ürün klasörünü oluşturmadı.")

    wait_timeout = int(settings.get("mockup_wait_timeout_sec") or 900)
    deadline = time.time() + wait_timeout
    outputs = collect_external_outputs(product_id, ready_folder, source_name, only_psd_stems, launch_started_at)
    expected_mockups = expected_external_mockup_count(settings, only_psd_stems)
    last_mockup_count = -1
    stable_mockup_checks = 0
    video_wait_notice_sent = False
    last_activity_at = time.time()
    last_video_size = -1
    video_started_at = None
    video_error = ""
    video_ready = not include_video
    while time.time() < deadline:
        status = read_json_file(status_path, {})
        if status.get("ok") is False:
            terminate_photoshop_processes()
            raise RuntimeError(f"Photoshop mockup hatası: {status.get('error')}")
        if check_product_stop and requested_stop(product_id):
            terminate_photoshop_processes()
            raise StopJob()
        if existing_queue_item_cancelled(queue_item_id):
            terminate_photoshop_processes()
            raise StopJob()
        outputs = collect_external_outputs(product_id, ready_folder, source_name, only_psd_stems, launch_started_at)
        mockup_count = len(outputs["mockups"])
        if mockup_count == last_mockup_count and mockup_count > 0:
            stable_mockup_checks += 1
        else:
            stable_mockup_checks = 0
            last_mockup_count = mockup_count
            last_activity_at = time.time()
        current_video_size = outputs["videos"][0].stat().st_size if outputs["videos"] else -1
        video_size_stable = current_video_size == last_video_size
        if current_video_size != last_video_size:
            last_video_size = current_video_size
            last_activity_at = time.time()
        if include_video and status.get("phase") in {"video", "done"} and video_started_at is None:
            video_started_at = time.time()
        if include_video and mockup_count >= expected_mockups and video_started_at is None:
            video_started_at = time.time()
        video_ready = not include_video
        if include_video and outputs["videos"] and (video_size_stable or status.get("phase") == "done"):
            try:
                video_ready = video_file_is_valid(outputs["videos"][0])
            except (OSError, subprocess.TimeoutExpired):
                video_ready = False
        if status.get("phase") == "done":
            video_error = str(status.get("video_error") or "")
            if include_video and not video_ready:
                video_error = video_error or "Photoshop video çıktısı oluşmadı veya tamamlanamadı."
            if mockup_count < expected_mockups:
                raise RuntimeError(f"Photoshop {mockup_count}/{expected_mockups} mockup üretti; PSD hata raporunu kontrol edin: {ready_folder}")
            break
        if video_started_at is not None and not video_ready and time.time() - video_started_at >= float(settings.get("video_wait_timeout_sec") or 180):
            video_error = "Photoshop video render süresi aşıldı; tamamlanan mockuplar korundu."
            terminate_photoshop_processes()
            break
        if mockup_count >= expected_mockups and video_ready:
            break
        if include_video and mockup_count >= expected_mockups and stable_mockup_checks >= 3 and not video_wait_notice_sent:
            add_event(
                product_id,
                "info",
                f"{mockup_count} Photoshop mockup PNG tamamlandı; video render işleminin bitmesi bekleniyor.",
                "mockup_render",
                meta={"mockups": mockup_count, "ready_folder": str(ready_folder)},
            )
            video_wait_notice_sent = True
        if mockup_count < expected_mockups and time.time() - last_activity_at >= 180:
            terminate_photoshop_processes()
            raise TimeoutError(
                f"Photoshop 180 saniyedir yeni çıktı üretmedi ({mockup_count}/{expected_mockups}); "
                "takılan işlem kapatıldı ve sonraki ürüne geçilecek."
            )
        elapsed = wait_timeout - int(deadline - time.time())
        if track_product_progress:
            set_step(product_id, "mockup_render", "running", min(95, 5 + int(elapsed / max(1, wait_timeout) * 90)))
            update_product(product_id, overall_progress=min(58, 20 + int(elapsed / max(1, wait_timeout) * 38)), current_step="mockup_render")
        time.sleep(5)

    if not outputs["mockups"]:
        terminate_photoshop_processes()
        raise TimeoutError(f"Photoshop mockup PNG ciktilari zamaninda olusmadi. Hazir klasor: {ready_folder}")
    if len(outputs["mockups"]) < expected_mockups:
        terminate_photoshop_processes()
        raise TimeoutError(f"Photoshop mockupları eksik: {len(outputs['mockups'])}/{expected_mockups}. Klasör: {ready_folder}")
    if include_video and not video_ready:
        outputs["videos"] = []
        video_error = video_error or "Photoshop video çıktısı tamamlanamadı; mockuplar korundu."
        add_event(product_id, "warning", video_error, "video_mockup")
    if preview_output_dir is not None:
        preview_output_dir.mkdir(parents=True, exist_ok=True)
        copied_paths = {"mockups": [], "videos": []}
        for kind in ("mockups", "videos"):
            target_dir = preview_output_dir / kind
            target_dir.mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(outputs[kind], start=1):
                if kind == "videos":
                    wait_for_valid_video_file(
                        path,
                        product_id=product_id if check_product_stop else "",
                    )
                target = target_dir / f"{index:02d}-{slugify_filename(path.name, kind[:-1])}"
                shutil.copy2(path, target)
                copied_paths[kind].append(str(target))
        copied = {
            "mockups": len(copied_paths["mockups"]),
            "videos": len(copied_paths["videos"]),
            "paths": copied_paths,
        }
    else:
        copied = copy_external_assets(
            product_id,
            outputs,
            clear_existing=clear_existing,
            artwork_option_id=artwork_option_id,
            sort_offset=sort_offset,
        )
    add_event(
        product_id,
        "info",
        f"Harici script çıktısı alındı: {copied['mockups']} mockup, {copied['videos']} video.",
        "mockup_render",
        meta={"ready_folder": str(ready_folder)},
    )
    return {"ready_folder": str(ready_folder), "source_image": str(prepared_image), "video_error": video_error, **copied}


def fit_image(image, max_size: tuple[int, int]):
    from PIL import Image

    copy = image.copy()
    copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    return copy


def poster_layer(source, max_size: tuple[int, int], frame_color: tuple[int, int, int] | None, mat: int = 34):
    from PIL import Image, ImageDraw, ImageFilter

    art = fit_image(source, (max_size[0] - mat * 2, max_size[1] - mat * 2)).convert("RGBA")
    frame = 22 if frame_color else 0
    w = art.width + mat * 2 + frame * 2
    h = art.height + mat * 2 + frame * 2
    layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    shadow = Image.new("RGBA", (w + 70, h + 70), (0, 0, 0, 0))
    draw_shadow = ImageDraw.Draw(shadow)
    draw_shadow.rounded_rectangle((36, 34, w + 34, h + 34), radius=8, fill=(10, 18, 28, 54))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    paper_x = frame
    paper_y = frame
    draw = ImageDraw.Draw(layer)
    if frame_color:
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=10, fill=frame_color)
    draw.rectangle((paper_x, paper_y, w - frame - 1, h - frame - 1), fill=(248, 248, 246))
    layer.alpha_composite(art, (paper_x + mat, paper_y + mat))
    draw.rectangle((paper_x + mat, paper_y + mat, paper_x + mat + art.width - 1, paper_y + mat + art.height - 1), outline=(210, 214, 218), width=2)
    canvas = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    canvas.alpha_composite(shadow, (0, 0))
    canvas.alpha_composite(layer, (20, 12))
    return canvas


def paste_center(background, layer, offset_y: int = 0, offset_x: int = 0):
    x = (background.width - layer.width) // 2 + offset_x
    y = (background.height - layer.height) // 2 + offset_y
    background.alpha_composite(layer, (x, y))


def make_room_background(width: int, height: int, variant: str):
    from PIL import Image, ImageDraw, ImageFilter

    bg = Image.new("RGBA", (width, height), (236, 232, 225, 255))
    draw = ImageDraw.Draw(bg)
    wall = (238, 235, 230) if variant == "living" else (230, 235, 238)
    floor = (202, 188, 171) if variant == "living" else (190, 199, 202)
    draw.rectangle((0, 0, width, int(height * 0.70)), fill=wall)
    draw.rectangle((0, int(height * 0.70), width, height), fill=floor)
    draw.line((0, int(height * 0.70), width, int(height * 0.70)), fill=(175, 164, 154), width=4)
    if variant == "living":
        draw.rounded_rectangle((70, 970, 730, 1265), radius=38, fill=(170, 159, 147))
        draw.rounded_rectangle((106, 870, 500, 1025), radius=30, fill=(184, 174, 162))
        draw.rectangle((1180, 900, 1830, 930), fill=(102, 84, 68))
        draw.rectangle((1210, 930, 1240, 1300), fill=(80, 66, 54))
        draw.rectangle((1760, 930, 1790, 1300), fill=(80, 66, 54))
    else:
        draw.rectangle((120, 960, 760, 1015), fill=(91, 104, 112))
        draw.rectangle((150, 1015, 190, 1320), fill=(64, 72, 78))
        draw.rectangle((690, 1015, 730, 1320), fill=(64, 72, 78))
        draw.rounded_rectangle((1340, 800, 1740, 1170), radius=28, fill=(224, 226, 222))
        draw.rectangle((1510, 1170, 1570, 1390), fill=(102, 113, 118))
    return bg.filter(ImageFilter.SMOOTH_MORE)


def render_local_mockups(product_id: str, source_image_path: str, product_name: str) -> list[dict]:
    from PIL import Image, ImageDraw

    source_path = Path(source_image_path.strip('"'))
    if not source_path.exists():
        add_event(product_id, "warning", "Mockup için kaynak görsel bulunamadı.", "mockup_render")
        return []

    clear_assets(product_id, "mockup")
    target_dir = product_upload_dir(product_id) / "mockups"
    target_dir.mkdir(parents=True, exist_ok=True)
    source = Image.open(source_path).convert("RGB")
    specs = [
        ("Front clean", (246, 248, 250), None, 0, 0),
        ("White frame", (239, 241, 244), (248, 248, 246), -4, -20),
        ("Black frame", (232, 235, 238), (28, 30, 32), 4, 20),
        ("Wood frame", (238, 236, 232), (153, 108, 70), 0, 0),
        ("Flat lay detail", (224, 221, 214), None, -7, -10),
    ]
    created = []
    for idx, (label, bg_color, frame, angle, offset_x) in enumerate(specs, start=1):
        bg = Image.new("RGBA", (2000, 1600), bg_color + (255,))
        draw = ImageDraw.Draw(bg)
        if label == "Flat lay detail":
            draw.rectangle((0, 1175, 2000, 1600), fill=(205, 199, 190))
            draw.ellipse((1450, 1080, 1850, 1475), fill=(238, 238, 235), outline=(195, 190, 184), width=5)
            draw.rectangle((120, 1240, 650, 1280), fill=(160, 144, 124))
        layer = poster_layer(source, (910, 1260), frame, 28)
        if angle:
            layer = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        paste_center(bg, layer, offset_y=-25, offset_x=offset_x)
        path = target_dir / f"{idx:02d}-{slugify_filename(label, 'mockup')}.png"
        bg.convert("RGB").save(path, "PNG", optimize=True)
        asset_id = add_asset(product_id, "mockup", label, path, idx)
        created.append({"id": asset_id, "label": label, "path": str(path)})

    room_specs = [("Living room wall", "living"), ("Home office wall", "office")]
    for room_idx, (label, room_kind) in enumerate(room_specs, start=6):
        bg = make_room_background(2000, 1600, room_kind)
        layer = poster_layer(source, (650, 920), (30, 30, 30) if room_kind == "office" else (240, 240, 238), 24)
        paste_center(bg, layer, offset_y=-290)
        path = target_dir / f"{room_idx:02d}-{slugify_filename(label, 'mockup')}.png"
        bg.convert("RGB").save(path, "PNG", optimize=True)
        asset_id = add_asset(product_id, "mockup", label, path, room_idx)
        created.append({"id": asset_id, "label": label, "path": str(path)})

    add_event(product_id, "info", f"{len(created)} mockup PNG uretildi.", "mockup_render")
    return created


def render_video_preview(product_id: str, source_image_path: str) -> dict | None:
    from PIL import Image, ImageDraw

    source_path = Path(source_image_path.strip('"'))
    if not source_path.exists():
        return None
    clear_assets(product_id, "video")
    target_dir = product_upload_dir(product_id) / "video"
    target_dir.mkdir(parents=True, exist_ok=True)
    source = Image.open(source_path).convert("RGB")
    frames = []
    for idx in range(12):
        bg = Image.new("RGBA", (1280, 720), (235, 236, 232, 255))
        draw = ImageDraw.Draw(bg)
        draw.rectangle((0, 505, 1280, 720), fill=(203, 191, 174))
        layer = poster_layer(source, (350 + idx * 8, 500 + idx * 10), (34, 34, 34), 18)
        paste_center(bg, layer, offset_y=-75, offset_x=-35 + idx * 6)
        frames.append(bg.convert("P", palette=Image.Palette.ADAPTIVE))
    path = target_dir / "video-preview.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=95, loop=0, optimize=True)
    asset_id = add_asset(product_id, "video", "Local video preview", path, 1)
    add_event(product_id, "info", "Yerel hareketli video önizlemesi üretildi.", "video_mockup")
    return {"id": asset_id, "label": "Local video preview", "path": str(path)}


def multipart_form_data(fields: dict, files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----CodexEtsyBoundary" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, filename, content_type, raw in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(raw)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload_listing_image(
    product_id: str,
    listing_id: str,
    asset: sqlite3.Row,
    rank: int,
    settings: dict,
    *,
    bypass_media_guard: bool = False,
) -> dict:
    assert_etsy_media_write_allowed(
        product_id,
        listing_id,
        settings,
        f"image rank {rank}",
        bypass_media_guard=bypass_media_guard,
    )
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    path = Path(asset["path"])
    content_type = mimetypes.guess_type(str(path))[0] or "image/png"
    body, content_type_header = multipart_form_data(
        {
            "rank": rank,
            "overwrite": "true",
            "is_watermarked": "false",
            "alt_text": f"{asset['label']} for {product_id}"[:500],
        },
        [("image", path.name, content_type, path.read_bytes())],
    )
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/"
        f"{urllib.parse.quote(str(listing_id))}/images"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type_header,
            **etsy_api_headers(settings, oauth=True),
        },
    )
    with urlopen_with_dns_retry(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("listing_image_id"):
        update_asset_etsy_image(asset["id"], data["listing_image_id"], listing_id)
    return data


def upload_etsy_mockup_images(product_id: str, listing_id: str, settings: dict) -> list[dict]:
    uploaded = []
    removed_errors = 0
    static_images = protected_static_assets(product_id)
    main_image = ensure_main_listing_asset(product_id)
    mockup_limit = ETSY_MAX_IMAGE_COUNT - len(static_images) - 1
    with db() as conn:
        mockups = conn.execute(
            "SELECT * FROM assets WHERE product_id=? AND kind='mockup' AND visible=1 ORDER BY sort_order LIMIT ?",
            (product_id, mockup_limit),
        ).fetchall()
    if not mockups:
        raise RuntimeError("Etsy'ye gonderilecek Photoshop mockup gorseli yok.")
    primary_mockup = mockups[0]
    if (
        clean_text(primary_mockup["role"] or "") != "primary_thumbnail"
        and not is_primary_thumbnail_mockup(primary_mockup["label"])
        and not is_primary_thumbnail_mockup(primary_mockup["path"])
    ):
        raise RuntimeError(
            f"{ETSY_PRIMARY_THUMBNAIL_STEM}.psd ciktisi Etsy'de ilk gorsel olmali; "
            "yanlis thumbnail yuklemesi durduruldu."
        )
    validate_primary_thumbnail_image(Path(primary_mockup["path"]))
    assets = []
    seen_hashes: set[str] = set()
    seen_mockup_fingerprints: list[str] = []
    fixed_hashes = {clean_text(asset["content_sha256"]) for asset in static_images}
    fixed_fingerprints = {image_fingerprint(Path(asset["path"])) for asset in static_images}
    for asset in [*mockups, main_image, *static_images]:
        path = Path(asset["path"])
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Etsy'ye gönderilecek görsel eksik veya boş: {path}")
        digest = file_sha256(path)
        protected = bool(int(asset["protected"] or 0))
        fingerprint = image_fingerprint(path)
        if not protected and (
            digest in fixed_hashes
            or any(fingerprint_distance(fingerprint, fixed) <= 3 for fixed in fixed_fingerprints)
        ):
            add_event(
                product_id,
                "warning",
                f"Mockup korunan sabit bilgi gorseliyle ayni oldugu icin yuklenmedi: {asset['label']}",
                "etsy_draft",
            )
            continue
        if not protected and any(
            fingerprint_distance(fingerprint, seen) <= 1 for seen in seen_mockup_fingerprints
        ):
            add_event(
                product_id,
                "warning",
                f"Gorsel olarak yinelenen mockup ikinci kez yuklenmedi: {asset['label']}",
                "etsy_draft",
            )
            continue
        if digest in seen_hashes:
            add_event(product_id, "warning", f"Aynı içerikli görsel ikinci kez yüklenmedi: {asset['label']}", "etsy_draft")
            continue
        if protected and clean_text(asset["content_sha256"]) != digest:
            raise RuntimeError(f"Korunan sabit görsel değişmiş: {asset['label']}")
        seen_hashes.add(digest)
        if not protected:
            seen_mockup_fingerprints.append(fingerprint)
        assets.append(asset)
    protected_roles = [clean_text(asset["role"]) for asset in assets if int(asset["protected"] or 0)]
    if protected_roles != list(STATIC_LISTING_ROLES):
        raise RuntimeError("Yeni listing için korunan dört bilgi görseli eksik veya sırası bozuk.")
    all_roles = [clean_text(asset["role"]) for asset in assets]
    if all_roles.count("main_artwork") != 1 or all_roles[-len(STATIC_LISTING_ROLES) - 1] != "main_artwork":
        raise RuntimeError("Ana gorsel mockuplardan sonra ve sabit bilgi gorsellerinden once tam bir kez bulunmalidir.")
    if len(assets) > ETSY_MAX_IMAGE_COUNT:
        raise RuntimeError("Etsy görsel sınırı aşıldı; hiçbir görsel gönderilmedi.")
    for rank, asset in enumerate(assets, start=1):
        if asset_uploaded_to_listing(asset, listing_id):
            add_event(product_id, "info", f"Etsy gorseli zaten yuklu, atlandi: rank {rank}", "etsy_draft")
            continue

        def send_image(asset_row=asset, image_rank=rank):
            return upload_listing_image(product_id, listing_id, asset_row, image_rank, settings)

        try:
            data = with_retry(product_id, "etsy_draft", settings, f"etsy.uploadListingImage.{rank}", send_image)
            uploaded.append(data)
            add_event(product_id, "info", f"Etsy görseli yüklendi: rank {rank}", "etsy_draft")
        except StopJob:
            raise
        except Exception as exc:
            error_text = str(exc)
            if etsy_listing_removed_error(error_text):
                removed_errors += 1
            add_event(product_id, "warning", f"Etsy görsel yükleme başarısız: rank {rank}", "etsy_draft", meta={"error": error_text})
    if assets and not uploaded and removed_errors:
        update_product(product_id, listing_id="")
        raise RuntimeError("Etsy listing silinmiş/removed durumda; kayıtlı listing ID temizlendi, yeni draft oluşturulmalı.")
    return uploaded


def upload_etsy_static_listing_images(product_id: str, listing_id: str, settings: dict, start_rank: int = 8) -> list[dict]:
    raise RuntimeError(
        "Ayrı sabit görsel yükleme kapatıldı. Sabit görseller yalnızca tekilleştirilmiş ana medya manifestiyle yüklenebilir."
    )


def upload_listing_video(
    product_id: str,
    listing_id: str,
    asset: sqlite3.Row,
    settings: dict,
    *,
    bypass_media_guard: bool = False,
) -> dict:
    assert_etsy_media_write_allowed(
        product_id,
        listing_id,
        settings,
        "video",
        bypass_media_guard=bypass_media_guard,
    )
    settings = refresh_etsy_token(settings)
    secrets = settings["_secrets"]
    path = Path(asset["path"])
    if not path.exists():
        raise FileNotFoundError(f"Video dosyası bulunamadı: {path}")
    content_type = mimetypes.guess_type(str(path))[0] or "video/mp4"
    body, content_type_header = multipart_form_data(
        {"name": path.name},
        [("video", path.name, content_type, path.read_bytes())],
    )
    url = (
        "https://api.etsy.com/v3/application/shops/"
        f"{urllib.parse.quote(str(secrets['etsy_shop_id']))}/listings/"
        f"{urllib.parse.quote(str(listing_id))}/videos"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type_header,
            **etsy_api_headers(settings, oauth=True),
        },
    )
    with urlopen_with_dns_retry(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("video_id"):
        update_asset_etsy_image(asset["id"], data["video_id"], listing_id)
    return data


def upload_etsy_videos(product_id: str, listing_id: str, settings: dict) -> list[dict]:
    uploaded = []
    errors = []
    with db() as conn:
        assets = conn.execute(
            "SELECT * FROM assets WHERE product_id=? AND kind='video' ORDER BY sort_order LIMIT 1",
            (product_id,),
        ).fetchall()
    for rank, asset in enumerate(assets, start=1):
        if asset_uploaded_to_listing(asset, listing_id):
            add_event(product_id, "info", f"Etsy video zaten yuklu, atlandi: rank {rank}", "etsy_draft")
            continue

        def send_video(asset_row=asset):
            return upload_listing_video(product_id, listing_id, asset_row, settings)

        try:
            data = with_retry(product_id, "etsy_draft", settings, f"etsy.uploadListingVideo.{rank}", send_video)
            uploaded.append(data)
            add_event(product_id, "info", f"Etsy video yüklendi: rank {rank}", "etsy_draft", meta=data)
        except StopJob:
            raise
        except Exception as exc:
            error_text = str(exc)
            errors.append(error_text)
            add_event(product_id, "warning", f"Etsy video yükleme başarısız: rank {rank}", "etsy_draft", meta={"error": error_text})
    if assets and not uploaded:
        raise RuntimeError("Etsy video yüklenemedi: " + "; ".join(errors or ["bilinmeyen hata"]))
    return uploaded


def ensure_video_asset_for_etsy(product_id: str, source_image_path: str | None, settings: dict, ready_folder: str | Path | None = None, timeout: int = 45) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM assets WHERE product_id=? AND kind='video' ORDER BY sort_order LIMIT 1",
            (product_id,),
        ).fetchone()
    if row:
        return True
    copied = sync_external_video_asset(product_id, ready_folder, settings, timeout=timeout)
    if copied:
        return True
    add_event(
        product_id,
        "warning",
        "Photoshop/Adobe Media Encoder videosu bulunamadi; Etsy'ye statik MP4 gonderilmeyecek.",
        "video_mockup",
    )
    return False


def run_product_job(product_id: str) -> None:
    ensure_steps(product_id)
    settings = get_settings()
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return

    try:
        update_product(product_id, status="running", stop_requested=0, overall_progress=0)
        add_event(product_id, "start", "Ürün iş akışı başladı.")

        set_step(product_id, "validate", "running", 1)
        path = product["source_image_path"] or ""
        if path and not Path(path.strip('"')).exists():
            add_event(product_id, "warning", "Kaynak görsel yolu bulunamadı; dry-run devam ediyor.", "validate")
        sleep_progress(product_id, "validate", 1, 5, 0.6)
        set_step(product_id, "validate", "done", 100)

        set_step(product_id, "photoshop_prepare", "running", 10)
        prepared_image = run_photoshop_prepare(product_id, path, settings)
        sleep_progress(product_id, "photoshop_prepare", 12, 18, 0.4)
        set_step(product_id, "photoshop_prepare", "done", 100)
        stop_photoshop_automation_processes(["CodexPrepareArtwork.jsx"], wait_seconds=2.0)

        set_step(product_id, "mockup_render", "running", 45)
        update_product(product_id, current_step="mockup_render", overall_progress=45)
        selection_name = canonical_selection_name(
            product["selection_name"] if "selection_name" in product.keys() else ""
        )
        if not selection_name:
            raise ValueError("Yeni ürün için selection kategorisi seçilmedi.")
        template_info = selection_template_info(selection_name, settings)
        if not template_info["ready"]:
            raise ValueError(f"{selection_name} klasörünün mockups alanında PSD bulunamadı.")
        static_psds = [Path(path) for path in template_info["static_psds"]]
        selection_video_psd = Path(template_info["video_psd"]) if template_info["video_psd"] else None
        external_result = run_external_mockup_script(
            product_id,
            prepared_image,
            settings,
            only_psd_stems=[path.stem for path in static_psds],
            include_video=selection_video_psd is not None,
            psd_folder=Path(template_info["mockup_folder"]),
            video_psd=selection_video_psd,
        )
        if not int(external_result.get("videos") or 0) and template_info["ready_videos"]:
            copied_ready_video = copy_external_video_assets(
                product_id,
                [Path(template_info["ready_videos"][0])],
                clear_existing=True,
            )
            external_result["videos"] = copied_ready_video
        additional_result = {"processed_options": 0, "mockups": 0}
        if additional_result.get("processed_options"):
            add_event(
                product_id,
                "info",
                (
                    "Ek görsel çeşit mockupları tamamlandı: "
                    f"{additional_result['processed_options']} çeşit / {additional_result['mockups']} mockup."
                ),
                "mockup_render",
                meta=additional_result,
            )
        sleep_progress(product_id, "mockup_render", 56, 58, 0.3)
        set_step(product_id, "mockup_render", "done", 100)
        set_step(product_id, "video_mockup", "running", 5)
        update_product(product_id, current_step="video_mockup", overall_progress=67)
        if int(external_result.get("videos") or 0) > 0:
            add_event(product_id, "info", "Harici script video mockup çıktısını üretti.", "video_mockup")
        else:
            video_error = external_result.get("video_error") or "Bu selection için kullanılabilir video bulunamadı."
            add_event(product_id, "warning", video_error, "video_mockup")
        update_product(product_id, overall_progress=72)
        set_step(product_id, "video_mockup", "done" if int(external_result.get("videos") or 0) else "warning", 100,
                 error=external_result.get("video_error") or (None if int(external_result.get("videos") or 0) else "Video bulunamadı; mockuplar hazır."))

        seo_data = minimal_etsy_copy()

        set_step(product_id, "etsy_draft", "running", 5)
        update_product(product_id, current_step="etsy_draft", overall_progress=80)
        if settings["etsy_mode"] == "dry_run":
            add_event(
                product_id,
                "warning",
                "Etsy dry-run aktif; draft push icin Ayarlar > Etsy mod = draft yapilmali.",
                "etsy_draft",
            )
        else:
            def draft():
                return create_etsy_draft(product_id, product, seo_data, settings)
            draft_result = with_retry(product_id, "etsy_draft", settings, "etsy.createDraftListing", draft)
            if draft_result.get("_mock"):
                if draft_result.get("free_shipping_failed"):
                    add_event(
                        product_id,
                        "warning",
                        "Etsy ücretsiz kargo kontrolü geçmedi; gerçek istek gönderilmedi.",
                        "etsy_draft",
                        meta={"message": draft_result.get("message")},
                    )
                else:
                    add_event(
                        product_id,
                        "warning",
                        "Etsy draft için eksik ayar var; gerçek istek gönderilmedi.",
                        "etsy_draft",
                        meta={"missing": draft_result.get("missing", [])},
                    )
            else:
                listing_id = str(draft_result.get("listing_id") or "")
                set_step(product_id, "etsy_draft", "running", 25)
                update_product(product_id, overall_progress=84)
                add_event(product_id, "info", "Yeni Etsy draft listing oluşturuldu.", "etsy_draft", meta=draft_result)
                if listing_id:
                    uploads = upload_etsy_mockup_images(product_id, listing_id, settings)
                    set_step(product_id, "etsy_draft", "running", 60)
                    update_product(product_id, overall_progress=89)
                    add_event(
                        product_id,
                        "info",
                        f"Etsy draft görsel push tamamlandı: {len(uploads)} görsel.",
                        "etsy_draft",
                        meta={"listing_id": listing_id, "uploaded_images": len(uploads)},
                    )
                    videos = upload_etsy_videos(product_id, listing_id, settings)
                    set_step(product_id, "etsy_draft", "running", 75)
                    update_product(product_id, overall_progress=92)
                    add_event(
                        product_id,
                        "info",
                        f"Etsy video push tamamlandı: {len(videos)} video.",
                        "etsy_draft",
                        meta={"listing_id": listing_id, "uploaded_videos": len(videos)},
                    )
                    inventory = with_retry(
                        product_id,
                        "etsy_draft",
                        settings,
                        "etsy.updateListingInventory",
                        lambda: update_etsy_inventory(product_id, listing_id, get_settings()),
                    )
                    set_step(product_id, "etsy_draft", "running", 92)
                    update_product(product_id, overall_progress=95)
                    add_event(
                        product_id,
                        "info",
                        (
                            "Etsy varyasyon inventory push tamamlandı: "
                            f"{inventory['enabled_products_count']} aktif / {inventory['products_count']} kombinasyon."
                        ),
                        "etsy_draft",
                        meta=inventory,
                    )
        update_product(product_id, etsy_fee_estimate_usd=float(settings["etsy_listing_fee_usd"]))
        set_step(product_id, "etsy_draft", "running", 98)
        update_product(product_id, current_step="etsy_draft", overall_progress=96)
        set_step(product_id, "etsy_draft", "done", 100)

        set_step(product_id, "cost_finalize", "running", 10)
        add_event(product_id, "done", "Ürün maliyet raporu tamamlandı.", "cost_finalize")
        sleep_progress(product_id, "cost_finalize", 94, 100, 0.5)
        set_step(product_id, "cost_finalize", "done", 100)
        update_product(product_id, status="done", overall_progress=100, current_step="cost_finalize")

    except StopJob:
        terminate_photoshop_processes()
        add_event(product_id, "stopped", "İşlem kullanıcı tarafından durduruldu.")
        update_product(product_id, status="stopped", stop_requested=0)
        for key, _, _ in STEP_DEFS:
            with db() as conn:
                row = conn.execute("SELECT status FROM steps WHERE product_id=? AND step_key=?", (product_id, key)).fetchone()
            if row and row["status"] == "running":
                set_step(product_id, key, "stopped")
    except Exception as exc:
        add_event(product_id, "error", str(exc), meta={"trace": traceback.format_exc(limit=6)})
        update_product(product_id, status="error")
        with db() as conn:
            row = conn.execute(
                "SELECT current_step FROM products WHERE id=?",
                (product_id,),
            ).fetchone()
        if row and row["current_step"]:
            set_step(product_id, row["current_step"], "error", error=str(exc))
    finally:
        with jobs_lock:
            jobs.pop(product_id, None)


def seo_data_for_product(product_id: str, product, settings: dict) -> dict:
    return minimal_etsy_copy()


def push_etsy_now(product_id: str) -> dict:
    settings = get_settings()
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Ürün bulunamadı.")
    if clean_text(product["etsy_update_mode"] if "etsy_update_mode" in product.keys() else "") == "inventory_only":
        return push_etsy_inventory_only(product_id)
    existing_listing_id = clean_text(product["listing_id"] or "")
    if existing_listing_id:
        raise RuntimeError(
            "Mevcut Etsy urun koruma kilidi: listing ID bagli urun Etsy'ye push edilemez. "
            f"listing_id={existing_listing_id}"
        )
    discover_etsy_shop_settings(settings)
    settings = get_settings()
    seo_data = seo_data_for_product(product_id, product, settings)
    set_step(product_id, "etsy_draft", "running", 88)
    update_product(product_id, status="running", current_step="etsy_draft", stop_requested=0)
    try:
        existing_listing_id = clean_text(product["listing_id"] or "")
        if existing_listing_id:
            raise RuntimeError(
                "Mevcut Etsy urun koruma kilidi: listing ID bagli urun Etsy'ye push edilemez. "
                f"listing_id={existing_listing_id}"
            )
        if existing_listing_id and etsy_draft_listing_exists(existing_listing_id, settings):
            draft_result = {"listing_id": existing_listing_id, "_existing": True}
            add_event(
                product_id,
                "info",
                "Mevcut Etsy draft listing güncellenecek; yeni kopya oluşturulmadı.",
                "etsy_draft",
                meta={"listing_id": existing_listing_id},
            )
        else:
            if existing_listing_id:
                add_event(
                    product_id,
                    "warning",
                    "Kayıtlı Etsy listing ID artık draft listesinde yok; yeni draft oluşturulacak.",
                    "etsy_draft",
                    meta={"old_listing_id": existing_listing_id},
                )
                update_product(product_id, listing_id="")
            draft_result = with_retry(
                product_id,
                "etsy_draft",
                settings,
                "etsy.createDraftListing",
                lambda: create_etsy_draft(product_id, product, seo_data, get_settings()),
            )
        if draft_result.get("_mock"):
            if draft_result.get("free_shipping_failed"):
                add_event(
                    product_id,
                    "warning",
                    "Etsy ücretsiz kargo kontrolü geçmedi; gerçek istek gönderilmedi.",
                    "etsy_draft",
                    meta={"message": draft_result.get("message")},
                )
            else:
                add_event(
                    product_id,
                    "warning",
                    "Etsy draft için eksik ayar var; gerçek istek gönderilmedi.",
                    "etsy_draft",
                    meta={"missing": draft_result.get("missing", [])},
                )
        else:
            listing_id = str(draft_result.get("listing_id") or "")
            if not draft_result.get("_existing"):
                add_event(product_id, "info", "Yeni Etsy draft listing oluşturuldu.", "etsy_draft", meta=draft_result)
            if listing_id:
                if draft_result.get("_existing"):
                    add_event(
                        product_id,
                        "info",
                        "Mevcut draft title/aciklama/tag alanlari korunacak; metadata guncellenmedi.",
                        "etsy_draft",
                        meta={"listing_id": listing_id},
                    )
                    add_event(
                        product_id,
                        "info",
                        "Mevcut draft icin gorsel/video upload atlandi; sadece varyasyon inventory guncellenecek.",
                        "etsy_draft",
                        meta={"listing_id": listing_id},
                    )
                else:
                    uploads = upload_etsy_mockup_images(product_id, listing_id, get_settings())
                    add_event(
                        product_id,
                        "info",
                        f"Etsy draft görsel push tamamlandı: {len(uploads)} görsel.",
                        "etsy_draft",
                        meta={"listing_id": listing_id, "uploaded_images": len(uploads)},
                    )
                    ensure_video_asset_for_etsy(product_id, product["source_image_path"], get_settings(), None, timeout=45)
                    videos = upload_etsy_videos(product_id, listing_id, get_settings())
                    add_event(
                        product_id,
                        "info",
                        f"Etsy video push tamamlandı: {len(videos)} video.",
                        "etsy_draft",
                        meta={"listing_id": listing_id, "uploaded_videos": len(videos)},
                    )
                inventory = with_retry(
                    product_id,
                    "etsy_draft",
                    settings,
                    "etsy.updateListingInventory",
                    lambda: update_etsy_inventory(product_id, listing_id, get_settings()),
                )
                add_event(
                    product_id,
                    "info",
                    (
                        "Etsy varyasyon inventory push tamamlandı: "
                        f"{inventory['enabled_products_count']} aktif / {inventory['products_count']} kombinasyon."
                    ),
                    "etsy_draft",
                    meta=inventory,
                )
        update_product(product_id, etsy_fee_estimate_usd=float(settings["etsy_listing_fee_usd"]))
        set_step(product_id, "etsy_draft", "done", 100)
        update_product(product_id, status="done", overall_progress=100, current_step="etsy_draft")
    except StopJob:
        add_event(product_id, "stopped", "Etsy draft işlemi kullanıcı tarafından durduruldu.", "etsy_draft")
        set_step(product_id, "etsy_draft", "stopped")
        update_product(product_id, status="stopped", stop_requested=0, current_step="etsy_draft")
    except Exception as exc:
        add_event(product_id, "error", str(exc), "etsy_draft", meta={"trace": traceback.format_exc(limit=6)})
        set_step(product_id, "etsy_draft", "error", error=str(exc))
        update_product(product_id, status="error", current_step="etsy_draft")
    return product_payload(product_id)


def push_etsy_inventory_only(product_id: str) -> dict:
    settings = get_settings()
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Ürün bulunamadı.")
    listing_id = clean_text(product["listing_id"] or "")
    if not listing_id:
        raise ValueError("Mevcut Etsy listing ID yok; once listing linkini bagla.")
    raise RuntimeError(
        "Mevcut Etsy urun koruma kilidi aktif: mevcut listing icin varyasyon/fiyat guncellemesi kapali. "
        f"listing_id={listing_id}"
    )

    set_step(product_id, "etsy_draft", "running", 88)
    update_product(product_id, status="running", current_step="etsy_draft", stop_requested=0)
    try:
        add_event(
            product_id,
            "info",
            "Mevcut Etsy listing için sadece varyasyon inventory güncellenecek.",
            "etsy_draft",
            meta={"listing_id": listing_id, "listing_url": etsy_listing_url(listing_id)},
        )
        ensure_variants_from_existing_etsy_listing(product_id, listing_id, get_settings())
        static_uploads = []
        if static_uploads:
            add_event(
                product_id,
                "info",
                f"Etsy sabit bilgi görselleri tamamlandı: {len(static_uploads)} görsel.",
                "etsy_draft",
                meta={"listing_id": listing_id, "uploaded_static_images": len(static_uploads)},
            )
        inventory = with_retry(
            product_id,
            "etsy_draft",
            settings,
            "etsy.updateListingInventory.only",
            lambda: update_etsy_inventory(product_id, listing_id, get_settings()),
        )
        add_event(
            product_id,
            "info",
            (
                "Sadece varyasyonlar Etsy'ye yazildi; gorsel, video, baslik, aciklama ve shipping degistirilmedi. "
                f"{inventory['enabled_products_count']} aktif / {inventory['products_count']} kombinasyon."
            ),
            "etsy_draft",
            meta=inventory,
        )
        set_step(product_id, "etsy_draft", "done", 100)
        update_product(product_id, status="done", overall_progress=100, current_step="etsy_draft", etsy_fee_estimate_usd=0)
    except StopJob:
        add_event(product_id, "stopped", "Etsy varyasyon güncelleme kullanıcı tarafından durduruldu.", "etsy_draft")
        set_step(product_id, "etsy_draft", "stopped")
        update_product(product_id, status="stopped", stop_requested=0, current_step="etsy_draft")
    except Exception as exc:
        add_event(product_id, "error", str(exc), "etsy_draft", meta={"trace": traceback.format_exc(limit=6)})
        set_step(product_id, "etsy_draft", "error", error=str(exc))
        update_product(product_id, status="error", current_step="etsy_draft")
    return product_payload(product_id)


def product_payload(product_id: str | None = None) -> dict:
    settings = get_settings()
    etsy_ok, etsy_missing = etsy_ready(settings)
    with db() as conn:
        if product_id:
            products = [conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()]
        else:
            products = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
        output = []
        for product in products:
            if not product:
                continue
            product_dict = row_to_dict(product)
            product_dict.pop("ai" + "_cost_usd", None)
            product_dict.pop("api_calls", None)
            product_dict["digital_download_sku"] = digital_download_sku(product["id"])
            product_dict["product_folder_name"] = product_folder_name(product["id"])
            if product_dict.get("listing_id"):
                product_dict["etsy_listing_url"] = etsy_listing_url(str(product_dict["listing_id"]))
            product_dict["source_image_url"] = upload_url_for_path(product_dict.get("source_image_path"))
            product_dict["etsy_push"] = {
                "mode": "inventory" if product_dict.get("etsy_update_mode") == "inventory_only" else settings.get("etsy_mode"),
                "ready": etsy_ok,
                "missing": etsy_missing,
                "listing_id": product_dict.get("listing_id"),
                "free_shipping_required": bool(settings.get("free_shipping_required")),
                "required_shipping_profile_name": settings.get("required_shipping_profile_name"),
            }
            steps = conn.execute("SELECT * FROM steps WHERE product_id=? ORDER BY id", (product["id"],)).fetchall()
            events = conn.execute(
                "SELECT * FROM events WHERE product_id=? ORDER BY id DESC LIMIT 80",
                (product["id"],),
            ).fetchall()
            variants = conn.execute(
                """
                SELECT * FROM variants
                WHERE product_id=?
                ORDER BY
                    CASE kind WHEN 'digital' THEN 0 WHEN 'framed' THEN 1 WHEN 'unframed' THEN 2 ELSE 3 END,
                    sale_price_usd ASC,
                    size_label, orientation_label, frame_label, source_row
                """,
                (product["id"],),
            ).fetchall()
            assets = conn.execute(
                "SELECT * FROM assets WHERE product_id=? ORDER BY kind, sort_order, created_at",
                (product["id"],),
            ).fetchall()
            seo = conn.execute(
                "SELECT * FROM seo_outputs WHERE product_id=?",
                (product["id"],),
            ).fetchone()
            product_dict["steps"] = [row_to_dict(row) for row in steps if row["step_key"] in ACTIVE_STEP_KEYS]
            product_dict["events"] = [row_to_dict(row) for row in events]
            product_dict["artwork_options"] = []
            asset_dicts = []
            for row in assets:
                asset = row_to_dict(row)
                asset["url"] = upload_url_for_path(asset.get("path"))
                asset_dicts.append(asset)
            product_dict["assets"] = asset_dicts
            if not product_dict.get("source_image_url"):
                for asset in asset_dicts:
                    if asset.get("kind") == "etsy_listing_image" and asset.get("url"):
                        product_dict["source_image_url"] = asset["url"]
                        break
            if seo:
                seo_dict = row_to_dict(seo)
                try:
                    seo_dict["tags"] = json.loads(seo_dict.pop("tags_json") or "[]")
                except Exception:
                    seo_dict["tags"] = []
                try:
                    seo_dict["warnings"] = json.loads(seo_dict.pop("warnings_json") or "[]")
                except Exception:
                    seo_dict["warnings"] = []
                seo_dict["description"] = clean_multiline_text(
                    seo_dict.get("description_intro", "")
                    + ("\n\n" + seo_dict.get("description_tail", "") if clean_multiline_text(seo_dict.get("description_tail", "")) else "")
                )
                product_dict["seo"] = seo_dict
            else:
                product_dict["seo"] = None
            variant_dicts = [row_to_dict(row) for row in variants]
            product_dict["variants"] = variant_dicts
            physical_sizes = []
            frame_options = []
            for variant in variant_dicts:
                if not variant["visible"] or variant["kind"] == "digital":
                    continue
                size_label = canonical_etsy_size_label(variant["size_label"])
                if size_label and size_label not in physical_sizes:
                    physical_sizes.append(size_label)
                frame_option = etsy_format_value(variant)
                if frame_option and frame_option not in frame_options:
                    frame_options.append(frame_option)
            frame_options.sort(key=lambda value: (
                0 if value.lower() == "no frame" else
                1 if value.lower().startswith("white") else
                2 if value.lower().startswith("wood") else
                3 if value.lower().startswith("dark wood") else
                4 if value.lower().startswith("black") else
                5 if value.lower().startswith("metal") else
                50,
                value.lower(),
            ))
            product_dict["variant_summary"] = {
                "digital": [v["size_label"] for v in variant_dicts if v["kind"] == "digital" and v["visible"]],
                "physical_sizes": physical_sizes,
                "frame_options": frame_options,
                "unframed_sizes": sorted({v["size_label"] for v in variant_dicts if v["kind"] == "unframed" and v["visible"]}),
                "framed_sizes": sorted({v["size_label"] for v in variant_dicts if v["kind"] == "framed" and v["visible"]}),
                "frames": sorted({v["frame_label"] for v in variant_dicts if v["kind"] == "framed" and v["frame_label"] and v["visible"]}),
                "orientations": sorted({v.get("orientation_label", "") for v in variant_dicts if v.get("orientation_label") and v["visible"]}),
                "artwork_options": [],
            }
            output.append(product_dict)
    return {"products": output}


def product_summary_payload() -> dict:
    settings = get_settings()
    etsy_ok, etsy_missing = etsy_ready(settings)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM variants v WHERE v.product_id=p.id) AS variant_count,
                   (SELECT path FROM assets a
                    WHERE a.product_id=p.id AND a.kind IN ('etsy_listing_image', 'mockup', 'static_listing_image')
                    ORDER BY CASE a.kind WHEN 'etsy_listing_image' THEN 0 WHEN 'mockup' THEN 1 ELSE 2 END, a.sort_order, a.created_at
                    LIMIT 1) AS thumb_path
            FROM products p
            WHERE COALESCE(p.etsy_update_mode, 'full') != 'inventory_only'
            ORDER BY p.created_at DESC
            """
        ).fetchall()
    output = []
    for product in rows:
        item = row_to_dict(product)
        item.pop("api_calls", None)
        item["variant_count"] = int(item.pop("variant_count") or 0)
        thumb = item.pop("thumb_path", "")
        item["source_image_url"] = upload_url_for_path(item.get("source_image_path")) or upload_url_for_path(thumb)
        if item.get("listing_id"):
            item["etsy_listing_url"] = etsy_listing_url(str(item["listing_id"]))
        item["digital_download_sku"] = digital_download_sku(item["id"])
        item["product_folder_name"] = product_folder_name(item["id"])
        item["etsy_push"] = {
            "mode": "inventory" if item.get("etsy_update_mode") == "inventory_only" else settings.get("etsy_mode"),
            "ready": etsy_ok,
            "missing": etsy_missing,
            "listing_id": item.get("listing_id"),
            "free_shipping_required": bool(settings.get("free_shipping_required")),
            "required_shipping_profile_name": settings.get("required_shipping_profile_name"),
        }
        item["assets"] = []
        item["variants"] = []
        item["steps"] = []
        item["events"] = []
        item["seo"] = None
        item["variant_summary"] = {
            "digital": [],
            "physical_sizes": [],
            "frame_options": [],
            "unframed_sizes": [],
            "framed_sizes": [],
            "frames": [],
            "orientations": [],
        }
        output.append(item)
    return {"products": output}


def create_product(payload: dict) -> dict:
    product_id = str(uuid.uuid4())
    image_file = payload.get("image_file") or {}
    name = clean_text(payload.get("name") or Path(str(image_file.get("filename") or "")).stem or "Yeni Poster")
    selection_name = canonical_selection_name(str(payload.get("selection_name") or ""))
    if not selection_name:
        raise ValueError("Yeni ürün için selection kategorisi seçilmelidir.")
    available_selections = {item["name"] for item in selection_catalog_payload()["selections"]}
    if selection_name not in available_selections:
        raise ValueError("Seçilen selection kategorisi panel klasörlerinde bulunamadı.")
    ensure_selection_folder(selection_name)
    source_image_path = clean_text(payload.get("source_image_path") or "")
    if image_file.get("data_url"):
        saved = save_uploaded_data(product_id, image_file.get("filename") or "poster.jpg", image_file["data_url"], "images")
        source_image_path = str(saved)
    ts = now_iso()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO products(id, name, source_image_path, status, selection_name, created_at, updated_at)
            VALUES(?, ?, ?, 'idle', ?, ?, ?)
            """,
            (product_id, name, source_image_path, selection_name, ts, ts),
        )
    ensure_steps(product_id)
    ensure_digital_variant(product_id)
    apply_default_variant_csvs(product_id, get_settings())
    ensure_static_listing_images(product_id)
    add_event(product_id, "created", "Ürün kaydı oluşturuldu.")
    return product_payload(product_id)


def create_products_bulk(payload: dict) -> dict:
    files = payload.get("image_files") or []
    if not isinstance(files, list) or not files:
        raise ValueError("Gorsel dosyasi secilmedi.")
    base_name = clean_text(payload.get("name") or "")
    selection_name = canonical_selection_name(str(payload.get("selection_name") or ""))
    if not selection_name:
        raise ValueError("Yeni ürünler için selection kategorisi seçilmelidir.")
    created_ids = []
    for file_payload in files:
        if not isinstance(file_payload, dict) or not file_payload.get("data_url"):
            continue
        file_stem = clean_text(Path(str(file_payload.get("filename") or "")).stem)
        name = base_name
        if len(files) > 1:
            name = f"{base_name} - {file_stem}".strip(" -") if base_name else file_stem
        result = create_product({"name": name, "image_file": file_payload, "selection_name": selection_name})
        product = (result.get("products") or [{}])[0]
        if product.get("id"):
            created_ids.append(product["id"])
    if not created_ids:
        raise ValueError("Gecerli gorsel dosyasi bulunamadi.")
    summary = product_summary_payload()
    summary["created_ids"] = created_ids
    summary["products_created"] = len(created_ids)
    return summary


def renumber_artwork_options(product_id: str) -> None:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, is_primary FROM artwork_options WHERE product_id=? ORDER BY is_primary DESC, sort_order, created_at",
            (product_id,),
        ).fetchall()
        ts = now_iso()
        primary = [row for row in rows if int(row["is_primary"] or 0)]
        others = [row for row in rows if not int(row["is_primary"] or 0)]
        order = primary[:1] + others
        for idx, row in enumerate(order, start=1):
            conn.execute(
                "UPDATE artwork_options SET label=?, sort_order=?, updated_at=? WHERE id=?",
                (str(idx), idx, ts, row["id"]),
            )


def upload_artwork_options(product_id: str, payload: dict) -> dict:
    files = payload.get("artwork_files") or []
    if payload.get("image_file"):
        files = [payload.get("image_file")]
    if not isinstance(files, list) or not files:
        raise ValueError("Çeşit görseli bulunamadı.")
    ensure_primary_artwork_option(product_id)
    created = 0
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS n FROM artwork_options WHERE product_id=?",
            (product_id,),
        ).fetchone()
        sort_order = int(row["n"] or 0) + 1
        ts = now_iso()
        for file_payload in files:
            if not isinstance(file_payload, dict) or not file_payload.get("data_url"):
                continue
            saved = save_uploaded_data(
                product_id,
                file_payload.get("filename") or f"artwork-{sort_order}.png",
                file_payload["data_url"],
                "artwork_options",
            )
            conn.execute(
                """
                INSERT INTO artwork_options(id, product_id, label, source_path, sort_order, visible, is_primary, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (str(uuid.uuid4()), product_id, str(sort_order), str(saved), sort_order, ts, ts),
            )
            sort_order += 1
            created += 1
    renumber_artwork_options(product_id)
    add_event(product_id, "info", f"{created} ek görsel çeşidi eklendi.", "artwork_options")
    return product_payload(product_id)


def delete_artwork_option(product_id: str, option_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM artwork_options WHERE id=? AND product_id=?",
            (option_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Görsel çeşidi bulunamadı.")
        if int(row["is_primary"] or 0):
            raise ValueError("Ana görsel çeşidi silinemez; ana görseli düzenle ile değiştir.")
        conn.execute("DELETE FROM assets WHERE product_id=? AND artwork_option_id=?", (product_id, option_id))
        conn.execute("DELETE FROM artwork_options WHERE id=? AND product_id=?", (option_id, product_id))
    renumber_artwork_options(product_id)
    add_event(product_id, "edit", f"Görsel çeşidi silindi: {row['label']}", "artwork_options")
    return product_payload(product_id)


def update_asset_visibility(product_id: str, asset_id: str, payload: dict) -> dict:
    visible = 1 if bool(payload.get("visible")) else 0
    with db() as conn:
        row = conn.execute(
            "SELECT id, kind, protected FROM assets WHERE id=? AND product_id=?",
            (asset_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Asset bulunamadı.")
        if (clean_text(row["kind"]) == "static_listing_image" or int(row["protected"] or 0)) and not visible:
            raise RuntimeError("Korunan sabit Etsy bilgi gorseli gizlenemez.")
        conn.execute(
            "UPDATE assets SET visible=?, updated_at=? WHERE id=? AND product_id=?",
            (visible, now_iso(), asset_id, product_id),
        )
    return product_payload(product_id)


def delete_asset(product_id: str, asset_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE id=? AND product_id=?",
            (asset_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Asset bulunamadı.")
        if clean_text(row["kind"]) == "static_listing_image" or int(row["protected"] or 0):
            raise RuntimeError("Korunan sabit Etsy bilgi gorseli silinemez.")
        conn.execute("DELETE FROM assets WHERE id=? AND product_id=?", (asset_id, product_id))
    try:
        path = Path(row["path"])
        if path.exists() and path.is_file() and str(path.resolve()).startswith(str(UPLOADS.resolve())):
            path.unlink()
    except Exception:
        pass
    add_event(product_id, "edit", f"Asset silindi: {row['label']}", "assets")
    return product_payload(product_id)


RECOVERABLE_ETSY_DRAFT_ERRORS = (
    "primary_fields",
    "primary_language_missing",
)


def is_recoverable_etsy_draft_error(text: str) -> bool:
    lowered = clean_text(text).lower()
    return any(marker in lowered for marker in RECOVERABLE_ETSY_DRAFT_ERRORS)


def can_resume_etsy_draft_only(product_id: str) -> bool:
    with db() as conn:
        product = conn.execute(
            "SELECT current_step, etsy_update_mode FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
        if not product:
            return False
        if clean_text(product["etsy_update_mode"] if "etsy_update_mode" in product.keys() else "") == "inventory_only":
            return False
        if clean_text(product["current_step"] or "") != "etsy_draft":
            return False
        rows = conn.execute(
            "SELECT step_key, status FROM steps WHERE product_id=?",
            (product_id,),
        ).fetchall()
    statuses = {row["step_key"]: row["status"] for row in rows}
    required_done = ("validate", "photoshop_prepare", "mockup_render", "video_mockup")
    return all(statuses.get(key) == "done" for key in required_done)


def prepare_etsy_draft_resume(product_id: str) -> None:
    ts = now_iso()
    with db() as conn:
        conn.execute(
            """
            UPDATE steps
            SET status='pending', progress=88, retry_count=0, error=NULL,
                completed_at=NULL, updated_at=?
            WHERE product_id=? AND step_key='etsy_draft'
            """,
            (ts, product_id),
        )
        conn.execute(
            """
            UPDATE products
            SET status='queued', stop_requested=0, current_step='etsy_draft', updated_at=?
            WHERE id=?
            """,
            (ts, product_id),
        )


def run_queued_product(product_id: str) -> None:
    with db() as conn:
        product = conn.execute("SELECT etsy_update_mode, stop_requested FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return
    if int(product["stop_requested"] or 0):
        update_product(product_id, status="stopped", stop_requested=0)
        return
    if clean_text(product["etsy_update_mode"] if "etsy_update_mode" in product.keys() else "") == "inventory_only":
        update_product(product_id, status="stopped", stop_requested=0)
        add_event(
            product_id,
            "stopped",
            "Mevcut Etsy urunu genel uretim kuyrugunda calistirilamaz; kontrollu medya editorunu kullanin.",
        )
        return
    elif can_resume_etsy_draft_only(product_id):
        add_event(product_id, "queue", "Onceki adimlar tamam; Etsy draft adimindan devam ediliyor.", "etsy_draft")
        push_etsy_now(product_id)
    else:
        run_product_job(product_id)


def queue_worker() -> None:
    global queue_thread
    while True:
        with jobs_lock:
            while job_queue:
                product_id = job_queue.pop(0)
                with db() as conn:
                    row = conn.execute("SELECT status, stop_requested FROM products WHERE id=?", (product_id,)).fetchone()
                if not row:
                    continue
                if int(row["stop_requested"] or 0):
                    update_product(product_id, status="stopped", stop_requested=0)
                    add_event(product_id, "stopped", "Sıradaki işlem başlamadan durduruldu.")
                    continue
                if product_id in jobs and jobs[product_id].is_alive():
                    continue
                thread = threading.current_thread()
                jobs[product_id] = thread
                break
            else:
                queue_thread = None
                return

        try:
            add_event(product_id, "queue", "Sıradaki ürün çalışmaya alındı.")
            run_queued_product(product_id)
        finally:
            with jobs_lock:
                jobs.pop(product_id, None)


def ensure_queue_worker_locked() -> None:
    global queue_thread
    if queue_thread and queue_thread.is_alive():
        return
    queue_thread = threading.Thread(target=queue_worker, daemon=True)
    queue_thread.start()


def enqueue_product(product_id: str, *, reset_steps: bool = True) -> dict:
    with db() as conn:
        product = conn.execute(
            "SELECT id, listing_id, etsy_update_mode FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
    if not product:
        raise ValueError("Ürün bulunamadı.")
    if clean_text(product["etsy_update_mode"] or "") == "inventory_only":
        raise ValueError(
            "Mevcut Etsy urunleri genel uretim kuyruguna eklenemez. "
            "Yalnizca urun detayindaki onizlemeli ve onayli medya editoru kullanilabilir."
        )
    if clean_text(product["listing_id"] or "") and clean_text(product["etsy_update_mode"] or "") != "inventory_only":
        raise ValueError(
            "Guvenlik kilidi: listing ID bagli urun full workflow ile tekrar baslatilamaz. "
            "Mevcut Etsy urunu icin sadece varyasyon/fiyat guncelleme kullanilmali."
        )
    with jobs_lock:
        if product_id in jobs and jobs[product_id].is_alive():
            return product_payload(product_id)
        if product_id in job_queue:
            return product_payload(product_id)
        if reset_steps:
            reset_steps_for_run(product_id)
        update_product(product_id, stop_requested=0, status="queued")
        job_queue.append(product_id)
        add_event(product_id, "queue", f"Ürün sıraya eklendi. Sıra: {len(job_queue)}")
        ensure_queue_worker_locked()
    return product_payload(product_id)


def start_job(product_id: str) -> dict:
    return enqueue_product(product_id, reset_steps=not can_resume_etsy_draft_only(product_id))


def stop_job(product_id: str) -> dict:
    removed = False
    with jobs_lock:
        while product_id in job_queue:
            job_queue.remove(product_id)
            removed = True
    update_product(product_id, stop_requested=1)
    if removed:
        update_product(product_id, status="stopped", stop_requested=0)
        add_event(product_id, "stopped", "Ürün kuyruktan çıkarıldı.")
    else:
        add_event(product_id, "stop", "Durdurma isteği alındı.")
        terminate_photoshop_processes()
    return product_payload(product_id)


def stop_all_product_jobs() -> dict:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, status FROM products
            WHERE status IN ('queued', 'running')
              AND COALESCE(etsy_update_mode, 'full') != 'inventory_only'
            """
        ).fetchall()
    affected = [row["id"] for row in rows]
    with jobs_lock:
        job_queue[:] = [product_id for product_id in job_queue if product_id not in set(affected)]
    for row in rows:
        if row["status"] == "queued":
            update_product(row["id"], status="stopped", stop_requested=0)
            add_event(row["id"], "stopped", "Tüm üretimi durdur komutuyla kuyruktan çıkarıldı.")
        else:
            update_product(row["id"], stop_requested=1)
            add_event(row["id"], "stop", "Tüm üretimi durdur komutu alındı.")
    if any(row["status"] == "running" for row in rows):
        terminate_photoshop_processes()
    return {"ok": True, "stopped": len(rows)}


def forget_queued_product(product_id: str) -> None:
    with jobs_lock:
        while product_id in job_queue:
            job_queue.remove(product_id)


def resume_queued_jobs() -> None:
    settings = get_settings()
    with db() as conn:
        stale_running = conn.execute(
            """
            SELECT id FROM products
            WHERE status='running'
            ORDER BY updated_at, created_at
            """
        ).fetchall()
        for row in stale_running:
            product_id = row["id"]
            conn.execute(
                "UPDATE products SET status='stopped', stop_requested=0, updated_at=? WHERE id=?",
                (now_iso(), product_id),
            )
            conn.execute(
                "INSERT INTO events(product_id, kind, step_key, message, meta_json, created_at) VALUES(?, 'stopped', NULL, ?, NULL, ?)",
                (product_id, "Server yeniden başladı; yarım kalan aktif işlem güvenlik için durduruldu.", now_iso()),
            )
        rows = conn.execute(
            """
            SELECT id FROM products
            WHERE status='queued' AND COALESCE(stop_requested, 0)=0
            ORDER BY updated_at, created_at
            """
        ).fetchall()
        if not bool(settings.get("auto_resume_queue_on_start")):
            for row in rows:
                product_id = row["id"]
                conn.execute(
                    "UPDATE products SET status='stopped', stop_requested=0, updated_at=? WHERE id=?",
                    (now_iso(), product_id),
                )
                conn.execute(
                    "INSERT INTO events(product_id, kind, step_key, message, meta_json, created_at) VALUES(?, 'stopped', NULL, ?, NULL, ?)",
                    (product_id, "Server acilisinda otomatik kuyruk devam ettirme kapali; urun guvenlik icin durduruldu.", now_iso()),
                )
            return
        error_rows = conn.execute(
            """
            SELECT p.id,
                   COALESCE(s.error, '') AS step_error,
                   COALESCE((
                       SELECT e.message
                       FROM events e
                       WHERE e.product_id=p.id AND e.kind IN ('error', 'retry')
                       ORDER BY e.id DESC
                       LIMIT 1
                   ), '') AS last_error
            FROM products p
            LEFT JOIN steps s ON s.product_id=p.id AND s.step_key='etsy_draft'
            WHERE p.status='error'
              AND p.current_step='etsy_draft'
              AND COALESCE(p.stop_requested, 0)=0
            ORDER BY p.updated_at, p.created_at
            """
        ).fetchall()
    recoverable_rows = [
        row
        for row in error_rows
        if is_recoverable_etsy_draft_error(f"{row['step_error']} {row['last_error']}")
        and can_resume_etsy_draft_only(row["id"])
    ]
    if not rows and not recoverable_rows:
        return
    with jobs_lock:
        for row in recoverable_rows:
            product_id = row["id"]
            if product_id not in job_queue:
                prepare_etsy_draft_resume(product_id)
                job_queue.append(product_id)
                add_event(product_id, "queue", "Duzeltilen Etsy draft hatasi icin urun kaldigi adimdan tekrar siraya alindi.", "etsy_draft")
        for row in rows:
            product_id = row["id"]
            if product_id not in job_queue:
                update_product(product_id, status="queued")
                job_queue.append(product_id)
                add_event(product_id, "queue", "Server yeniden başladı; ürün kuyruğa geri alındı.")
        ensure_queue_worker_locked()


def resume_applying_media_jobs() -> None:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, preview_json FROM media_replacement_jobs WHERE status='applying' ORDER BY updated_at"
        ).fetchall()
    for row in rows:
        try:
            preview = json.loads(row["preview_json"] or "{}")
            image_ids = [
                clean_text(str(item))
                for item in (preview.get("approved_image_ids") or [])
                if clean_text(str(item))
            ]
            if not image_ids:
                image_ids = [
                    clean_text(str(item.get("id") or ""))
                    for item in (preview.get("images") or [])
                    if clean_text(str(item.get("id") or ""))
                ]
            if not image_ids:
                update_media_replacement_job(
                    row["id"],
                    status="error",
                    stage="Islem devam ettirilemedi",
                    error="Onaylanan gorsel kimlikleri bulunamadi.",
                )
                continue
            update_media_replacement_job(
                row["id"],
                stage="Yarim kalan Etsy aktarimi devam ediyor",
                progress=5,
                error=None,
            )
            thread = threading.Thread(
                target=run_existing_media_apply_job,
                args=(row["id"], image_ids),
                daemon=True,
                name=f"media-resume-{row['id'][:8]}",
            )
            with media_replacement_lock:
                media_replacement_threads[row["id"]] = thread
            thread.start()
        except Exception as exc:
            update_media_replacement_job(
                row["id"],
                status="error",
                stage="Islem devam ettirilemedi",
                error=readable_exception(exc),
            )


def recover_interrupted_previews() -> None:
    """No preview worker survives a server restart."""
    with db() as conn:
        conn.execute(
            """UPDATE media_replacement_jobs
               SET status='error', stage='Önizleme yarıda kaldı',
                   error='Sunucu kapanırken önizleme tamamlanmadı. Yeniden üretimi başlatın.',
                   updated_at=?
               WHERE status IN ('queued', 'running')""",
            (now_iso(),),
        )


def upload_variants_csv(product_id: str, payload: dict) -> dict:
    csv_file = payload.get("csv_file") or {}
    if not csv_file.get("data_url"):
        raise ValueError("CSV dosyası bulunamadı.")
    settings = get_settings()
    percent = float(payload.get("percent") if payload.get("percent") is not None else payload.get("markup_percent") or 0)
    upload_kind = clean_text(payload.get("variant_kind") or "auto").lower()
    include_shipping = bool(payload.get("include_shipping_in_profit", settings["include_shipping_in_profit"]))
    pricing_formula = payload.get("pricing_formula") or settings["pricing_formula"]
    retail_multiplier = float(payload.get("gelato_retail_multiplier") or settings["gelato_retail_multiplier"] or 1)
    saved = save_uploaded_data(product_id, csv_file.get("filename") or "costs.csv", csv_file["data_url"], "csv")
    result = parse_variants_csv(product_id, saved, percent, upload_kind, include_shipping, pricing_formula, retail_multiplier)
    return product_payload(product_id) | {"csv_result": result}


def delete_variant(product_id: str, variant_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM variants WHERE id=? AND product_id=?",
            (variant_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Varyasyon bulunamadı.")
        if row["locked"]:
            raise ValueError("DigitalDownload sabit satırı silinemez.")
        conn.execute("DELETE FROM variants WHERE id=? AND product_id=?", (variant_id, product_id))
    add_event(product_id, "edit", f"Varyasyon silindi: {row['size_label']} {row['frame_label']}".strip(), "variants")
    return product_payload(product_id)


preview_image_lock = threading.Lock()


def panel_preview_path(source: Path) -> Path:
    stat = source.stat()
    key = hashlib.sha256(f"{source}:{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
    target = DATA / "preview_cache" / f"{key}.jpg"
    if not target.exists():
        with preview_image_lock:
            if not target.exists():
                from PIL import Image, ImageOps
                target.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(source) as original:
                    original.draft("RGB", (720, 720))
                    image = ImageOps.exif_transpose(original)
                    image.thumbnail((720, 720))
                    image.convert("RGB").save(target, "JPEG", quality=82)
    return target


class Handler(BaseHTTPRequestHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        allowed = {f"localhost:{APP_PORT}", f"127.0.0.1:{APP_PORT}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in allowed or (origin and origin not in {f"http://{h}" for h in allowed}):
            self.send_json({"error": "Yalnızca yerel panelden erişilebilir."}, 403)
            return False
        is_library_upload = self.command == "POST" and urllib.parse.urlparse(self.path).path == "/api/v2/library-files"
        required_type = "application/octet-stream" if is_library_upload else "application/json"
        if self.command in {"POST", "PATCH", "DELETE"} and not self.headers.get("Content-Type", "").startswith(required_type):
            self.send_json({"error": "JSON içerik türü gerekli."}, 415)
            return False
        return True

    server_version = "EtsyEkosistem/2.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def serve_static(self):
        parsed = urllib.parse.urlparse(self.path)
        raw_path = parsed.path
        upload = raw_path.startswith("/uploads/")
        base = UPLOADS if upload else STATIC
        rel = urllib.parse.unquote(raw_path.removeprefix("/uploads/") if upload else raw_path.lstrip("/") or "index.html")
        path = (base / rel).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():
            self.send_error(404)
            return
        if upload and urllib.parse.parse_qs(parsed.query).get("preview") == ["1"] and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            path = panel_preview_path(path)
        stat = path.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "private, max-age=0, must-revalidate" if upload else "no-cache")
        self.end_headers()
        try:
            with path.open("rb") as content:
                shutil.copyfileobj(content, self.wfile, 256 * 1024)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            if path == "/api/health":
                self.send_json({"ok": True, "app": "etsy-ekosistem-v2", "version": "2.0.0", "root": str(ROOT), "data_dir": str(DATA), "pid": os.getpid(), "time": now_iso()})
            elif path == "/api/v2/status":
                import v2_local
                self.send_json(v2_local.status(sys.modules[__name__]))
            elif path == "/api/etsy/oauth/start":
                self.send_json(start_etsy_oauth())
            elif path == "/api/google/oauth/start":
                self.send_json(start_google_oauth())
            elif path == "/api/canva/oauth/start":
                self.send_json(start_canva_oauth())
            elif path == "/oauth/canva/callback":
                if query.get("error"):
                    self.send_html(f"<h1>Canva connection failed</h1><p>{html.escape((query.get('error_description') or query.get('error') or [''])[0])}</p>", 400)
                    return
                code = (query.get("code") or [""])[0]
                state = (query.get("state") or [""])[0]
                try:
                    exchange_canva_oauth_code(code, state)
                    self.send_html(
                        "<h1>Canva connected</h1>"
                        "<p>You can close this window and return to the Etsy panel.</p>"
                        f"<p><a href='http://{APP_PUBLIC_HOST}:{APP_PORT}'>Return to panel</a></p>"
                    )
                except Exception as exc:
                    self.send_html(f"<h1>Canva token failed</h1><pre>{html.escape(str(exc))}</pre>", 500)
            elif path == "/oauth/google/callback":
                if query.get("error"):
                    self.send_html(f"<h1>Google Drive connection failed</h1><p>{html.escape((query.get('error_description') or query.get('error') or [''])[0])}</p>", 400)
                    return
                code = (query.get("code") or [""])[0]
                state = (query.get("state") or [""])[0]
                try:
                    exchange_google_oauth_code(code, state)
                    self.send_html(
                        "<h1>Google Drive connected</h1>"
                        "<p>You can close this window and return to the Etsy panel.</p>"
                        f"<p><a href='http://{APP_PUBLIC_HOST}:{APP_PORT}'>Return to panel</a></p>"
                    )
                except Exception as exc:
                    self.send_html(f"<h1>Google token failed</h1><pre>{html.escape(str(exc))}</pre>", 500)
            elif path == "/oauth/etsy/callback":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if query.get("error"):
                    self.send_html(f"<h1>Etsy bağlantısı başarısız</h1><p>{query.get('error_description', query.get('error'))[0]}</p>", 400)
                    return
                code = (query.get("code") or [""])[0]
                state = (query.get("state") or [""])[0]
                try:
                    exchange_etsy_oauth_code(code, state)
                    self.send_html(
                        "<h1>Etsy bağlantısı tamamlandı</h1>"
                        "<p>Bu pencereyi kapatıp Etsy Ekosistemi paneline dönebilirsin.</p>"
                    f"<p><a href='http://{APP_PUBLIC_HOST}:{APP_PORT}'>Panele dön</a></p>"
                    )
                except Exception as exc:
                    self.send_html(
                        "<h1>Etsy token alınamadı</h1>"
                        f"<pre>{str(exc)}</pre>"
                        f"<p><a href='http://{APP_PUBLIC_HOST}:{APP_PORT}'>Panele dön</a></p>",
                        500,
                    )
            elif path == "/api/settings":
                self.send_json(public_settings())
            elif path == "/api/selections":
                self.send_json(selection_catalog_payload())
            elif path == "/api/existing-mockup-queue":
                self.send_json(
                    existing_mockup_queue_payload(
                        batch_id=(query.get("batch_id") or [""])[0],
                        section=(query.get("section") or [""])[0],
                    )
                )
            elif path.startswith("/api/media-replacements/"):
                self.send_json(media_replacement_job_payload(path.split("/")[3]))
            elif path == "/api/bulk-products":
                catalog = bulk_products_payload(
                    page=int((query.get("page") or [1])[0]),
                    page_size=int((query.get("page_size") or [4])[0]),
                    search=(query.get("search") or [""])[0],
                )
                if (query.get("hydrate") or ["1"])[0].lower() not in {"0", "false", "no"}:
                    catalog = hydrate_bulk_product_cards(catalog)
                self.send_json(catalog)
            elif path.startswith("/api/bulk-products/"):
                product_id = path.split("/")[3]
                refresh_remote = (query.get("refresh") or ["1"])[0].lower() not in {"0", "false", "no"}
                self.send_json(bulk_product_detail(product_id, refresh_remote=refresh_remote))
            elif path.startswith("/api/products/") and path.endswith("/media-replacement/latest"):
                product_id = path.split("/")[3]
                self.send_json({"job": latest_media_replacement_job(product_id)})
            elif path.startswith("/api/products/") and path.endswith("/digital-delivery"):
                self.send_json(digital_delivery_status_payload(path.split("/")[3]))
            elif path == "/api/products":
                self.send_json(product_summary_payload() if query.get("summary") else product_payload())
            elif path.startswith("/api/products/"):
                product_id = path.split("/")[3]
                self.send_json(product_payload(product_id))
            else:
                self.serve_static()
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/v2/library-files":
                import v2_local
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Dosya boyutu belirtilmeli.")
                previous_timeout = self.connection.gettimeout()
                self.connection.settimeout(90)
                try:
                    result = v2_local.receive_library_file(
                        sys.modules[__name__], self.rfile,
                        (query.get("filename") or [""])[0], (query.get("kind") or [""])[0],
                        int(self.headers.get("Content-Length", "0")),
                    )
                finally:
                    self.connection.settimeout(previous_timeout)
                self.send_json(result, 201)
                return
            payload = self.read_json()
            if path.startswith("/api/v2/"):
                import v2_local
                self.send_json(v2_local.action(sys.modules[__name__], path, payload))
            elif path == "/api/settings":
                self.send_json(save_settings(payload))
            elif path == "/api/selections/open":
                self.send_json(open_selection_folder(clean_text(payload.get("selection_name") or "")))
            elif path == "/api/products/bulk":
                self.send_json(create_products_bulk(payload), 201)
            elif path == "/api/products":
                self.send_json(create_product(payload), 201)
            elif path == "/api/etsy/listing/import":
                self.send_json(import_existing_etsy_listing(payload), 201)
            elif path == "/api/bulk-variations/run":
                self.send_json(bulk_update_shop_variations(payload))
            elif path == "/api/bulk-products/refresh":
                self.send_json(refresh_bulk_products(payload))
            elif path == "/api/existing-mockup-queue/start":
                self.send_json(start_existing_mockup_batch(payload), 202)
            elif path == "/api/existing-mockup-queue/pause-all":
                self.send_json(pause_all_existing_mockups())
            elif path == "/api/existing-mockup-queue/resume-all":
                self.send_json(resume_all_existing_mockups())
            elif path.startswith("/api/existing-mockup-queue/") and path.endswith("/pause"):
                self.send_json(pause_existing_mockup_queue_item(path.split("/")[3]))
            elif path.startswith("/api/existing-mockup-queue/") and path.endswith("/resume"):
                self.send_json(resume_existing_mockup_queue_item(path.split("/")[3]))
            elif path.startswith("/api/existing-mockup-queue/") and path.endswith("/source"):
                self.send_json(replace_existing_mockup_source(path.split("/")[3], payload))
            elif path.startswith("/api/existing-mockup-queue/") and path.endswith("/review"):
                self.send_json(review_existing_mockup_source(path.split("/")[3], payload))
            elif path.startswith("/api/existing-mockup-queue/") and path.endswith("/apply"):
                self.send_json(apply_existing_mockup_queue_item(path.split("/")[3]), 202)
            elif path.startswith("/api/products/") and path.endswith("/media-replacement/preview"):
                self.send_json(start_existing_media_preview(path.split("/")[3], payload), 202)
            elif path.startswith("/api/products/") and "/media-replacement/" in path and path.endswith("/apply"):
                parts = path.split("/")
                self.send_json(begin_existing_media_apply(parts[3], parts[5], payload), 202)
            elif path.startswith("/api/products/") and path.endswith("/digital-delivery/retry"):
                self.send_json(retry_digital_delivery(path.split("/")[3]))
            elif path.startswith("/api/bulk-products/") and path.endswith("/push"):
                self.send_json(push_bulk_product_inventory(path.split("/")[3]))
            elif path.startswith("/api/bulk-products/") and path.endswith("/variants"):
                self.send_json(create_variant(path.split("/")[3], payload), 201)
            elif path.endswith("/start") and path.startswith("/api/products/"):
                self.send_json(start_job(path.split("/")[3]))
            elif path.endswith("/push-etsy") and path.startswith("/api/products/"):
                self.send_json(push_etsy_now(path.split("/")[3]))
            elif path.endswith("/push-etsy-inventory") and path.startswith("/api/products/"):
                self.send_json(push_etsy_inventory_only(path.split("/")[3]))
            elif path.endswith("/stop") and path.startswith("/api/products/"):
                product_id = path.split("/")[3]
                self.send_json(stop_job(product_id))
            elif path == "/api/production/stop-all":
                self.send_json(stop_all_product_jobs())
            elif path == "/api/etsy/discover":
                self.send_json(discover_etsy_shop_settings())
            elif path.endswith("/csv") and path.startswith("/api/products/"):
                self.send_json(upload_variants_csv(path.split("/")[3], payload))
            elif path.endswith("/variants/reprice") and path.startswith("/api/products/"):
                product_id = path.split("/")[3]
                settings = get_settings()
                percent = float(payload.get("percent") if payload.get("percent") is not None else payload.get("markup_percent") or 0)
                reprice_variants(
                    product_id,
                    percent,
                    bool(payload.get("include_shipping_in_profit", settings["include_shipping_in_profit"])),
                    payload.get("pricing_formula") or settings["pricing_formula"],
                    float(payload.get("gelato_retail_multiplier") or settings["gelato_retail_multiplier"] or 1),
                    clean_text(payload.get("variant_kind") or "all").lower(),
                )
                self.send_json(product_payload(product_id))
            else:
                self.send_json({"error": "Not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_PATCH(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path.startswith("/api/bulk-products/"):
                parts = path.split("/")
                payload = self.read_json()
                if len(parts) >= 6 and parts[4] == "variants":
                    self.send_json(update_variant(parts[3], parts[5], payload))
                    return
                self.send_json({"error": "Not found"}, 404)
                return
            if not path.startswith("/api/products/"):
                self.send_json({"error": "Not found"}, 404)
                return
            parts = path.split("/")
            product_id = parts[3]
            payload = self.read_json()
            if len(parts) >= 6 and parts[4] == "assets":
                self.send_json(update_asset_visibility(product_id, parts[5], payload))
                return
            with db() as conn:
                product = conn.execute(
                    "SELECT status, listing_id, etsy_update_mode FROM products WHERE id=?",
                    (product_id,),
                ).fetchone()
            if not product:
                raise ValueError("Ürün bulunamadı.")
            if product["status"] in {"queued", "running"}:
                raise RuntimeError("Çalışan ürünü düzenlemeden önce durdurmalısın.")
            updates = {}
            for key in ("name", "source_image_path"):
                if key in payload:
                    updates[key] = clean_text(str(payload[key]))
            if "selection_name" in payload:
                selection_name = canonical_selection_name(clean_text(str(payload["selection_name"])))
                template = selection_template_info(selection_name)
                if not template["ready"]:
                    raise ValueError(f"{selection_name} klasöründe PSD bulunamadı.")
                if clean_text(product["etsy_update_mode"] or "") == "inventory_only":
                    raise RuntimeError(
                        "Etsy draft/listing oluşmuş üründe PSD kategorisi bu akıştan değiştirilemez. "
                        "Mevcut ürün medya editörünü kullan."
                    )
                updates["selection_name"] = selection_name
            image_file = payload.get("image_file") or {}
            if image_file.get("data_url"):
                if clean_text(product["etsy_update_mode"] or "") == "inventory_only":
                    raise RuntimeError(
                        "Etsy draft/listing oluşmuş ürünün ana görseli genel üretimden değiştirilemez. "
                        "Mevcut ürün medya editörünü kullan."
                    )
                saved = save_uploaded_data(product_id, image_file.get("filename") or "poster.jpg", image_file["data_url"], "images")
                source = assert_artwork_source_safe(saved, product_id)
                updates.update(
                    source_image_path=str(source),
                    status="idle",
                    overall_progress=0,
                    current_step="",
                    stop_requested=0,
                )
                for kind in ("mockup", "video", "main_listing_image"):
                    clear_assets(product_id, kind)
                reset_steps_for_run(product_id)
            update_product(product_id, **updates)
            add_event(product_id, "edit", "Ürün bilgileri düzenlendi.")
            self.send_json(product_payload(product_id))
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_DELETE(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path.startswith("/api/existing-mockup-queue/"):
                self.send_json(delete_existing_mockup_queue_item(path.split("/")[3]))
                return
            if path.startswith("/api/bulk-products/"):
                parts = path.split("/")
                if len(parts) >= 6 and parts[4] == "variants":
                    self.send_json(delete_variant(parts[3], parts[5]))
                    return
                self.send_json({"error": "Not found"}, 404)
                return
            if not path.startswith("/api/products/"):
                self.send_json({"error": "Not found"}, 404)
                return
            parts = path.split("/")
            product_id = parts[3]
            if len(parts) >= 6 and parts[4] == "variants":
                self.send_json(delete_variant(product_id, parts[5]))
                return
            if len(parts) >= 6 and parts[4] == "assets":
                self.send_json(delete_asset(product_id, parts[5]))
                return
            with db() as conn:
                product = conn.execute(
                    "SELECT status FROM products WHERE id=?",
                    (product_id,),
                ).fetchone()
            if product and product["status"] in {"queued", "running"}:
                raise RuntimeError("Çalışan ürünü silmeden önce durdurmalısın.")
            forget_queued_product(product_id)
            folder_to_delete = product_upload_dir(product_id).resolve()
            with db() as conn:
                conn.execute("DELETE FROM products WHERE id=?", (product_id,))
            try:
                if folder_to_delete.exists() and folder_to_delete.is_dir() and str(folder_to_delete).startswith(str(UPLOADS.resolve())):
                    shutil.rmtree(folder_to_delete)
            except Exception:
                pass
            self.send_json({"ok": True})
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def main() -> None:
    init_db()
    recover_interrupted_previews()
    ensure_selection_library()
    resume_queued_jobs()
    resume_applying_media_jobs()
    resume_existing_mockup_queue()
    print(f"Etsy Ekosistem V2 running at http://{APP_HOST}:{APP_PORT}")
    ThreadingHTTPServer((APP_HOST, APP_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
