import os
import sys
import time
import json
import zipfile
import subprocess
import threading
import re
import shutil
import socket
import secrets
import requests
import urllib3
import telebot
from telebot import types

# NOTE: Telegram Bot API inline/reply keyboards do not support arbitrary red/green/blue
# background colors. Button meaning is therefore kept consistent by action grouping:
# positive/start = normal, navigation/info = normal, destructive = normal.
# Color-square emojis are intentionally not used in button labels.

# psutil library for advanced hardware reading (Safe-catch for Termux)
try:
    import psutil
except ImportError:
    psutil = None

# ----------------- CENTRAL CONFIGURATION -----------------
# সব সেটিংস main.py-এর ভিতরেই রাখা হয়েছে — আলাদা config.json লাগবে না।
CONFIG = {
    "bot_token": '8474938545:AAG99txUTh07Rf3x92xNOBtAeNAsEtex5I8',
    "base_dir": "projects",
    "meta_file": "projects_meta.json",

    # Admin / force join
    "owner_id": 8393671553,
    "force_join_enabled": False,
    "force_channel": "",  # Added only from the bot Admin Panel
    "force_join_link": "",

    # User limits (admin panel থেকে বদলানো যাবে)
    "default_project_limit": 1,
    "default_online_days": 2,
    "max_online_days": 30,

    # Hosting / recovery
    "auto_restart_default": True,
    "monitor_interval_seconds": 8,
    "expiry_cleanup_interval_seconds": 60,
    "process_grace_seconds": 8,

    # UI / animation
    "animation_speed": 0.12,
    "animation_style": "wave",   # wave | pulse | dots | orbit
    "show_live_status": True,
    "deploy_enabled": True,
    "dynamic_animation_enabled": True,
    "report_group_id": 0,
    "report_group_enabled": False,
    "max_concurrent_projects": 8,
    "queue_enabled": True,
    "queue_interval_seconds": 5,
    "expiry_grace_hours": 24,
    "crash_window_seconds": 300,
    "max_crash_restarts": 5,
    "max_file_edit_bytes": 524288,
    "suspended_users": {},
}

BOT_TOKEN = os.getenv("BOT_TOKEN", CONFIG["bot_token"])
BASE_DIR = CONFIG["base_dir"]
META_FILE = CONFIG["meta_file"]
OWNER_ID = int(CONFIG["owner_id"])

def cfg(key, default=None):
    return CONFIG.get(key, default)

def _load_runtime_admin_settings():
    """Load admin-managed settings saved by the bot itself."""
    try:
        if os.path.exists(META_FILE):
            with open(META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            settings = data.get("_settings", {})
            if isinstance(settings, dict):
                for key in (
                    "force_join_enabled", "force_channel", "force_channels", "force_join_link", "maintenance_mode",
                    "auto_restart_default", "deploy_enabled",
                    "dynamic_animation_enabled", "show_live_status",
                    "default_online_days", "default_project_limit",
                    "report_group_id", "report_group_enabled", "max_concurrent_projects",
                    "queue_enabled", "expiry_grace_hours", "suspended_users"
                ):
                    if key in settings:
                        CONFIG[key] = settings[key]
                CONFIG["force_join_enabled"] = bool(CONFIG.get("force_join_enabled", False))
                CONFIG["force_channel"] = str(CONFIG.get("force_channel", "") or "")
                stored_channels = CONFIG.get("force_channels", [])
                if not isinstance(stored_channels, list):
                    stored_channels = []
                CONFIG["force_channels"] = [str(x).strip() for x in stored_channels if str(x).strip()]
                if not CONFIG["force_channels"] and CONFIG["force_channel"]:
                    CONFIG["force_channels"] = [CONFIG["force_channel"]]
                CONFIG["force_join_link"] = str(CONFIG.get("force_join_link", "") or "")
    except Exception:
        pass

def _save_runtime_admin_settings():
    """Save only bot-added force-join settings to the metadata storage."""
    try:
        data = {}
        if os.path.exists(META_FILE):
            with open(META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        settings = data.get("_settings", {}) if isinstance(data.get("_settings", {}), dict) else {}
        settings.update({
            "force_join_enabled": bool(CONFIG.get("force_join_enabled", False)),
            "force_channel": str(CONFIG.get("force_channel", "") or ""),
            "force_channels": CONFIG.get("force_channels", []),
            "force_join_link": str(CONFIG.get("force_join_link", "") or ""),
            "maintenance_mode": bool(CONFIG.get("maintenance_mode", False)),
            "auto_restart_default": bool(CONFIG.get("auto_restart_default", True)),
            "deploy_enabled": bool(CONFIG.get("deploy_enabled", True)),
            "dynamic_animation_enabled": bool(CONFIG.get("dynamic_animation_enabled", True)),
            "show_live_status": bool(CONFIG.get("show_live_status", True)),
            "default_online_days": CONFIG.get("default_online_days", 2),
            "default_project_limit": CONFIG.get("default_project_limit", 1),
            "report_group_id": CONFIG.get("report_group_id", 0),
            "report_group_enabled": bool(CONFIG.get("report_group_enabled", False)),
            "max_concurrent_projects": int(CONFIG.get("max_concurrent_projects", 8)),
            "queue_enabled": bool(CONFIG.get("queue_enabled", True)),
            "expiry_grace_hours": float(CONFIG.get("expiry_grace_hours", 24)),
            "suspended_users": CONFIG.get("suspended_users", {})
        })
        data["_settings"] = settings
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Settings] Save failed: {e}")

def set_cfg(key, value):
    CONFIG[key] = value
    if key in (
        "force_join_enabled", "force_channel", "force_channels", "force_join_link", "maintenance_mode",
        "auto_restart_default", "deploy_enabled",
        "dynamic_animation_enabled", "show_live_status",
        "default_online_days", "default_project_limit",
        "report_group_id", "report_group_enabled", "max_concurrent_projects",
        "queue_enabled", "expiry_grace_hours", "suspended_users"
    ):
        _save_runtime_admin_settings()

def get_force_channels():
    """Return all configured Force Join targets (unique, ordered)."""
    channels = CONFIG.get("force_channels", [])
    if not isinstance(channels, list):
        channels = []
    channels = [str(x).strip() for x in channels if str(x).strip()]

    # Backward compatibility with older saved single-target configuration.
    legacy = str(CONFIG.get("force_channel", "") or "").strip()
    if legacy and legacy not in channels:
        channels.insert(0, legacy)

    seen = set()
    result = []
    for channel in channels:
        key = channel.lower()
        if key not in seen:
            seen.add(key)
            result.append(channel)
    return result


def _save_force_channels(channels):
    clean = []
    seen = set()
    for channel in channels:
        value = str(channel).strip()
        if not value:
            continue
        key = value.lower()
        if key not in seen:
            seen.add(key)
            clean.append(value)

    CONFIG["force_channels"] = clean
    # Keep legacy key synced so old parts of the bot remain compatible.
    CONFIG["force_channel"] = clean[0] if clean else ""
    CONFIG["force_join_enabled"] = bool(clean)
    _save_runtime_admin_settings()
    return clean


def set_force_channel(channel):
    # Legacy helper: replace with one target.
    _save_force_channels([channel.strip()] if str(channel).strip() else [])


def add_force_channel_target(value):
    """
    Add one Force Join channel/group without removing existing targets.
    Returns the verified Telegram chat object and True when newly added.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty target")

    target = int(raw) if raw.lstrip("-").isdigit() else "@" + raw.lstrip("@")
    chat = bot.get_chat(target)

    canonical = str(getattr(chat, "id", target))
    existing = get_force_channels()
    if canonical in existing or str(target) in existing:
        return chat, False

    existing.append(canonical)
    _save_force_channels(existing)
    return chat, True


def remove_force_channel_target(target):
    value = str(target).strip()
    channels = get_force_channels()
    remaining = [x for x in channels if str(x) != value]
    if len(remaining) == len(channels):
        return False
    _save_force_channels(remaining)
    return True


def clear_force_channels():
    _save_force_channels([])

def set_owner_id(owner_id):
    CONFIG["owner_id"] = int(owner_id)
    global OWNER_ID
    OWNER_ID = int(owner_id)

def get_force_channel():
    channels = get_force_channels()
    return channels[0] if channels else ""

def get_force_join_link():
    return CONFIG.get("force_join_link", "")

def set_force_join_link(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty join link")

    if raw.lower().startswith("t.me/"):
        raw = "https://" + raw

    if not (raw.startswith("https://t.me/") or raw.startswith("http://t.me/")):
        raise ValueError("invalid Telegram join link")

    CONFIG["force_join_link"] = raw
    _save_runtime_admin_settings()
    return raw

def set_force_join_target(value):
    """
    Accept @username / username or a numeric Telegram chat ID.
    For public chats, the join button is built from the chat username.
    For private chats/groups, a join link can be discovered if Telegram returns one.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty target")

    if raw.lstrip("-").isdigit():
        target = int(raw)
    else:
        target = "@" + raw.lstrip("@")

    # Verify that the bot can access the target chat and collect join metadata.
    chat = bot.get_chat(target)
    username = getattr(chat, "username", None)
    invite_link = getattr(chat, "invite_link", None)

    CONFIG["force_channel"] = str(target)
    if username:
        CONFIG["force_join_link"] = f"https://t.me/{username}"
    elif invite_link:
        CONFIG["force_join_link"] = str(invite_link)
    else:
        # Keep a manually configured private invite link, if one already exists.
        CONFIG["force_join_link"] = str(CONFIG.get("force_join_link", "") or "")

    _save_runtime_admin_settings()
    return chat


# Force join starts OFF unless an admin has previously added it from the bot.
_load_runtime_admin_settings()


# ----------------- REAL TELEGRAM COLORED BUTTONS -----------------
# Telegram Bot API styles:
# primary = blue | success = green | danger = red
#
# pyTelegramBotAPI versions serialize reply markup differently. Some use to_dict(),
# others use to_json(), so both are overridden to guarantee that the "style" field
# is actually sent to Telegram.

class StyledInlineKeyboardButton(types.InlineKeyboardButton):
    def __init__(self, *args, style=None, **kwargs):
        self._button_style = style
        super().__init__(*args, **kwargs)

    def to_dict(self):
        data = super().to_dict()
        if self._button_style in ("primary", "success", "danger"):
            data["style"] = self._button_style
        return data

    def to_json(self):
        return json.dumps(self.to_dict())

class StyledKeyboardButton(types.KeyboardButton):
    def __init__(self, *args, style=None, **kwargs):
        self._button_style = style
        super().__init__(*args, **kwargs)

    def to_dict(self):
        data = super().to_dict()
        if self._button_style in ("primary", "success", "danger"):
            data["style"] = self._button_style
        return data

    def to_json(self):
        return json.dumps(self.to_dict())

def _button_style(text="", action=""):
    key = f"{text} {action}".lower()

    # RED — destructive actions only
    if any(x in key for x in (
        "terminate", "delete", "remove", "stop", "wipe", "clear",
        "proj_stop:", "proj_delete:", "proj_clear_env:"
    )):
        return "danger"

    # GREEN — positive/start/create actions
    if any(x in key for x in (
        "deploy", "start", "add", "install", "create",
        "btn_deploy", "proj_start:", "select_main:", "proj_add_env:",
        "proj_install:"
    )):
        return "success"

    # BLUE — navigation, management and all remaining actions
    return "primary"

def styled_button(text, callback_data=None, **kwargs):
    style = kwargs.pop("style", None) or _button_style(
        text, callback_data or kwargs.get("url", "")
    )
    return StyledInlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        style=style,
        **kwargs
    )

def styled_reply_button(text, **kwargs):
    style = kwargs.pop("style", None) or _button_style(text, "")
    return StyledKeyboardButton(text=text, style=style, **kwargs)
# ---------------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
print("[ButtonStyle] Telegram button styles enabled: blue=primary, green=success, red=danger")


# System and Process Tracking Databases
active_processes = {}
user_states = {}

ASCII_LOGO = """
🚀 ᴊxᴇ ʜᴏꜱᴛɪɴɢ ʜᴜʙ
"""

# ----------------- STORAGE SYSTEM -----------------
def load_meta():
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_meta(data):
    with open(META_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# ----------------- SAFE NETWORK API WRAPPER -----------------
def safe_api_call(func, *args, **kwargs):
    """Retries a telegram API call if a temporary network connection reset or timeout occurs"""
    max_retries = 3
    backoff = 1.5
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout, 
                urllib3.exceptions.ProtocolError,
                ConnectionResetError) as e:
            if attempt < max_retries - 1:
                print(f"[Network Warning] Connection lost, retrying in {backoff}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 2
            else:
                print(f"[Network Error] Persistent connection failure: {e}")
                raise e
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                return None  # Safely ignore as content is already identical
            raise e

def bot_send_message(chat_id, text, **kwargs):
    return safe_api_call(bot.send_message, chat_id, text, **kwargs)

def bot_edit_message(text, chat_id, message_id, **kwargs):
    return safe_api_call(bot.edit_message_text, text, chat_id, message_id, **kwargs)

def bot_send_document(chat_id, document, **kwargs):
    return safe_api_call(bot.send_document, chat_id, document, **kwargs)

def bot_delete_message(chat_id, message_id):
    try:
        return safe_api_call(bot.delete_message, chat_id, message_id)
    except Exception:
        pass  # Ignore if already deleted

# ----------------- PORT UTILITIES -----------------
def find_free_port():
    """Find an available local TCP port for a project process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])

# ----------------- FILE INDEX MAPPING SYSTEM -----------------
def _is_valid_project_rel_path(rel_path):
    """Return True only for a normal, project-relative user file path."""
    if not isinstance(rel_path, str):
        return False

    raw = rel_path.strip()
    if not raw or "\x00" in raw:
        return False

    # Treat both Windows and POSIX separators as separators for validation.
    normalized = raw.replace("\\", "/")

    # Absolute paths, drive letters and parent traversal are never valid.
    if normalized.startswith("/") or normalized.startswith("//"):
        return False
    if re.match(r"^[A-Za-z]:", normalized):
        return False

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return False

    lower = normalized.lower()

    # Hide bogus Windows environment/system paths that can arrive as literal
    # filenames inside an uploaded ZIP, e.g. %SystemDrive%\ProgramData\...
    system_markers = (
        "%systemdrive%", "%windir%", "%systemroot%", "%programdata%",
        "programdata/microsoft/windows/", "windows/system32/",
        "windows/caches/", "appdata/local/microsoft/windows/"
    )
    if any(marker in lower for marker in system_markers):
        return False

    return True


def resolve_project_file_path(proj_dir, rel_path, must_exist=False):
    """
    Resolve a file only if it remains inside the current project root.
    Symlinks resolving outside the project are rejected too.
    """
    if not _is_valid_project_rel_path(rel_path):
        return None

    root = os.path.realpath(os.path.abspath(proj_dir))
    normalized = rel_path.replace("\\", os.sep).replace("/", os.sep)
    target = os.path.realpath(os.path.abspath(os.path.join(root, normalized)))

    if not (target == root or target.startswith(root + os.sep)):
        return None

    if must_exist and not os.path.exists(target):
        return None

    return target


def update_project_files_map(proj_id, proj_dir):
    all_files = []
    root_abs = os.path.realpath(os.path.abspath(proj_dir))

    for root, dirs, files_in_dir in os.walk(root_abs, followlinks=False):
        # Never follow directory symlinks.
        dirs[:] = [
            d for d in dirs
            if not os.path.islink(os.path.join(root, d))
        ]

        for f in files_in_dir:
            if f == "output.log":
                continue

            full = os.path.join(root, f)

            # Do not expose symlink files or anything resolving outside root.
            if os.path.islink(full):
                continue

            rel_path = os.path.relpath(full, root_abs).replace(os.sep, "/")

            if not _is_valid_project_rel_path(rel_path):
                continue

            safe_full = resolve_project_file_path(root_abs, rel_path, must_exist=True)
            if safe_full is None or not os.path.isfile(safe_full):
                continue

            all_files.append(rel_path)

    all_files.sort(key=str.lower)
    files_map = {str(idx): path for idx, path in enumerate(all_files)}

    meta = load_meta()
    if proj_id in meta:
        meta[proj_id]['files'] = files_map
        save_meta(meta)

    return files_map

# ----------------- DIAGNOSTICS & SYSTEM METRICS -----------------
def get_server_stats():
    cpu_p, ram_p, disk_p, free_gb = 12.0, 39.5, 50.0, 35.0
    env_mode = "Cloud Compute"

    try:
        if psutil:
            try:
                cpu_p = round(psutil.cpu_percent(interval=None), 1)
            except Exception:
                cpu_p = 0.0

            try:
                ram_p = round(psutil.virtual_memory().percent, 1)
            except Exception:
                pass

            try:
                disk = shutil.disk_usage("/")
                disk_p = round((disk.used / disk.total) * 100, 1)
                free_gb = round(disk.free / (1024 ** 3), 1)
            except Exception:
                pass
    except Exception:
        pass

    return (
        "🖥️ ꜱᴇʀᴠᴇʀ ꜱᴛᴀᴛᴜꜱ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"☁️ ᴘʟᴀᴛꜰᴏʀᴍ: {env_mode}\n"
        f"⚡ ᴄᴘᴜ: {cpu_p}%\n"
        f"💾 ʀᴀᴍ: {ram_p}%\n"
        f"📦 ꜱᴛᴏʀᴀɢᴇ: {disk_p}% used\n"
        f"🆓 ꜰʀᴇᴇ ꜱᴘᴀᴄᴇ: {free_gb} GB\n\n"
        "🟢 ꜱᴇʀᴠɪᴄᴇ: Online"
    )

# ----------------- LIMIT / EXPIRY / ADMIN UTILITIES -----------------
def is_admin(user_id):
    return int(user_id) == int(OWNER_ID)

def user_project_count(chat_id):
    return sum(1 for v in load_meta().values() if v.get("chat_id") == chat_id)

def get_user_limit(chat_id):
    if is_admin(chat_id):
        return float('inf')  # Admin has unlimited projects
    meta = load_meta()
    settings = meta.get("_settings", {})
    return int(settings.get("user_limits", {}).get(str(chat_id), cfg("default_project_limit", 1)))
def get_project_expiry(proj_data):
    return float(proj_data.get("expires_at", 0) or 0)

def format_remaining(seconds):
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d}d {h}h {m}m"

def project_is_expired(proj_data):
    exp = get_project_expiry(proj_data)
    return bool(exp and time.time() >= exp)

def register_user_profile(user):
    """Keep a lightweight registry so admin controls also work for users without projects."""
    try:
        meta = load_meta()
        users = meta.setdefault("_settings", {}).setdefault("users", {})
        users[str(user.id)] = {
            "username": f"@{user.username}" if getattr(user, "username", None) else "",
            "name": " ".join(x for x in [getattr(user, "first_name", "") or "", getattr(user, "last_name", "") or ""] if x).strip(),
            "last_seen": time.time(),
        }
        save_meta(meta)
    except Exception:
        pass

def resolve_user_identifier(identifier):
    """
    Resolve either a numeric Telegram ID or a @username already known to this bot.
    Usernames are learned from stored project metadata.
    """
    raw = str(identifier or "").strip()
    if not raw:
        return None, None

    # Numeric ID works directly.
    if raw.lstrip("-").isdigit():
        try:
            return int(raw), None
        except Exception:
            return None, None

    username = raw.lstrip("@").strip().lower()
    if not username:
        return None, None

    meta = load_meta()
    for uid, profile in meta.get("_settings", {}).get("users", {}).items():
        stored = str(profile.get("username", "") or "").lstrip("@").strip().lower()
        if stored and stored == username:
            try:
                return int(uid), stored
            except Exception:
                pass
    for key, pdata in meta.items():
        if str(key).startswith("_") or not isinstance(pdata, dict):
            continue

        stored = str(pdata.get("username", "") or "").lstrip("@").strip().lower()
        if stored and stored == username:
            try:
                return int(pdata.get("chat_id")), stored
            except Exception:
                continue

    return None, None

def set_user_limit(chat_id, limit):
    meta = load_meta()
    meta.setdefault("_settings", {}).setdefault("user_limits", {})[str(chat_id)] = max(0, int(limit))
    save_meta(meta)

def set_project_expiry(proj_id, days):
    meta = load_meta()
    if proj_id in meta:
        days = max(0, min(float(days), float(cfg("max_online_days", 30))))
        meta[proj_id]["expires_at"] = time.time() + days * 86400
        save_meta(meta)

def cleanup_expired_projects():
    """Expiry flow: warn before expiry, stop on expiry, retain through grace period, then delete."""
    meta = load_meta()
    changed = False
    now = time.time()
    grace = max(0, float(cfg("expiry_grace_hours", 24))) * 3600

    for proj_id, data in list(meta.items()):
        if str(proj_id).startswith("_") or not isinstance(data, dict):
            continue
        exp = get_project_expiry(data)
        if not exp:
            continue
        left = exp - now
        warned = set(data.get("expiry_warnings", []))

        for label, threshold in (("1h", 3600), ("15m", 900)):
            if 0 < left <= threshold and label not in warned:
                notify_project(data, f"⏳ ᴘʀᴏᴊᴇᴄᴛ ᴇxᴘɪʀʏ ᴡᴀʀɴɪɴɢ\n━━━━━━━━━━━━━━━━━━\n📦 {data.get('name', proj_id)}\n⏱️ ᴛɪᴍᴇ ʟᴇꜰᴛ: {format_remaining(left)}")
                warned.add(label); data["expiry_warnings"] = sorted(warned); changed = True

        if left <= 0:
            if not data.get("expired_at"):
                stop_project_process(proj_id, notify=False)
                data["expired_at"] = now
                data["expiry_status"] = "expired"
                notify_project(data, f"⏳ ᴘʀᴏᴊᴇᴄᴛ ᴇxᴘɪʀᴇᴅ\n━━━━━━━━━━━━━━━━━━\n📦 {data.get('name', proj_id)}\n🛑 ꜱᴇʀᴠɪᴄᴇ ꜱᴛᴏᴘᴘᴇᴅ. ꜰɪʟᴇꜱ ᴡɪʟʟ ʀᴇᴍᴀɪɴ ꜰᴏʀ {int(grace//3600)}ʜ ɢʀᴀᴄᴇ ᴘᴇʀɪᴏᴅ.")
                project_activity(proj_id, "Expired")
                changed = True
            elif now - float(data.get("expired_at", now)) >= grace:
                stop_project_process(proj_id, notify=False)
                shutil.rmtree(data.get("dir", ""), ignore_errors=True)
                del meta[proj_id]
                changed = True

    if changed:
        save_meta(meta)


def is_user_suspended(user_id):
    suspended = cfg("suspended_users", {}) or {}
    return str(user_id) in suspended


def set_user_suspension(user_id, reason=""):
    suspended = dict(cfg("suspended_users", {}) or {})
    suspended[str(user_id)] = {"reason": str(reason or "No reason provided"), "time": time.time()}
    set_cfg("suspended_users", suspended)


def clear_user_suspension(user_id):
    suspended = dict(cfg("suspended_users", {}) or {})
    suspended.pop(str(user_id), None)
    set_cfg("suspended_users", suspended)


def user_suspension_reason(user_id):
    suspended = cfg("suspended_users", {}) or {}
    if not isinstance(suspended, dict):
        return "Temporarily restricted by administrator."
    info = suspended.get(str(user_id), {})
    return info.get("reason", "") if isinstance(info, dict) else str(info)


def active_project_count():
    return sum(1 for info in active_processes.values() if info.get("process") and info["process"].poll() is None)


def queue_store():
    meta = load_meta()
    return meta.setdefault("_settings", {}).setdefault("start_queue", [])


def enqueue_project_start(proj_id):
    meta = load_meta()
    queue = meta.setdefault("_settings", {}).setdefault("start_queue", [])
    if proj_id not in queue:
        queue.append(proj_id)
    if proj_id in meta:
        meta[proj_id]["queue_state"] = "queued"
        meta[proj_id]["queue_requested_at"] = time.time()
    save_meta(meta)
    return queue.index(proj_id) + 1 if proj_id in queue else 0


def queue_position(proj_id):
    queue = load_meta().get("_settings", {}).get("start_queue", [])
    try: return queue.index(proj_id) + 1
    except ValueError: return 0


def request_project_start(proj_id, proj_data):
    if not bool(cfg("queue_enabled", True)) or active_project_count() < int(cfg("max_concurrent_projects", 8)):
        return run_project_process(proj_id, proj_data)
    pos = enqueue_project_start(proj_id)
    return True, f"QUEUED:{pos}"


def queue_worker():
    while True:
        try:
            meta = load_meta()
            queue = list(meta.get("_settings", {}).get("start_queue", []))
            changed = False
            while queue and active_project_count() < int(cfg("max_concurrent_projects", 8)):
                pid = queue.pop(0); pdata = meta.get(pid)
                changed = True
                if not pdata or project_is_expired(pdata) or is_user_suspended(pdata.get("chat_id")):
                    continue
                pdata["queue_state"] = "starting"
                save_meta(meta)
                ok, msg = run_project_process(pid, pdata)
                if ok:
                    pdata = load_meta().get(pid, pdata)
                    notify_project(pdata, f"🟢 ᴏɴʟɪɴᴇ ꜱʟᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ\n━━━━━━━━━━━━━━━━━━\n📦 {pdata.get('name', pid)}\n🚀 ᴘʀᴏᴊᴇᴄᴛ ꜱᴛᴀʀᴛᴇᴅ.")
                meta = load_meta()
            if changed:
                meta.setdefault("_settings", {})["start_queue"] = queue
                save_meta(meta)
        except Exception:
            pass
        time.sleep(max(2, int(cfg("queue_interval_seconds", 5))))

def expiry_monitor():
    while True:
        try:
            cleanup_expired_projects()
        except Exception:
            pass
        time.sleep(int(cfg("expiry_cleanup_interval_seconds", 60)))

threading.Thread(target=expiry_monitor, daemon=True).start()
threading.Thread(target=queue_worker, daemon=True).start()

# ----------------- CRASH GUARD RECOVERY DAEMON -----------------
def bg_project_monitor():
    while True:
        time.sleep(8)
        try:
            meta = load_meta()
            for proj_id, proj_data in meta.items():
                if proj_id.startswith('_') or project_is_expired(proj_data):
                    continue
                if proj_data.get('auto_restart') is True:
                    if proj_id in active_processes:
                        poll = active_processes[proj_id]['process'].poll()
                        if poll is not None:
                            log_path = os.path.join(proj_data['dir'], 'output.log')
                            missing = get_missing_module(log_path)
                            notify_project(
                                proj_data,
                                f"⚠️ ᴘʀᴏᴊᴇᴄᴛ ᴄʀᴀꜱʜᴇᴅ\n━━━━━━━━━━━━━━━━━━\n"
                                f"📦 {proj_data.get('name', proj_id)}\n"
                                f"📄 {proj_data.get('main_file', 'Unknown')}"
                            )
                            project_activity(proj_id, "Crashed")
                            if not missing:
                                now = time.time()
                                window = int(cfg("crash_window_seconds", 300))
                                history = [x for x in proj_data.get("crash_history", []) if now - float(x) <= window]
                                history.append(now)
                                proj_data["crash_history"] = history[-20:]
                                max_restarts = int(cfg("max_crash_restarts", 5))
                                if len(history) > max_restarts:
                                    proj_data["auto_restart"] = False
                                    proj_data["crash_protection"] = True
                                    save_meta(meta)
                                    notify_project(proj_data, f"🛑 ᴄʀᴀꜱʜ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴀᴄᴛɪᴠᴇ\n━━━━━━━━━━━━━━━━━━\n📦 {proj_data.get('name', proj_id)}\n⚠️ Too many crashes in a short time. Auto restart was paused.")
                                else:
                                    proj_data['restart_count'] = int(proj_data.get('restart_count', 0)) + 1
                                    save_meta(meta)
                                    notify_project(proj_data, f"🔄 ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛɪɴɢ\n━━━━━━━━━━━━━━━━━━\n📦 {proj_data.get('name', proj_id)}\n🔁 Attempt {len(history)}/{max_restarts}")
                                    request_project_start(proj_id, proj_data)
        except Exception:
            pass

threading.Thread(target=bg_project_monitor, daemon=True).start()

# ----------------- PROJECT EVENTS / MONITORING -----------------
def project_activity(proj_id, event):
    meta = load_meta()
    if proj_id in meta:
        meta[proj_id].setdefault("activity", []).append({"time": time.time(), "event": event})
        meta[proj_id]["activity"] = meta[proj_id]["activity"][-30:]
        meta[proj_id]["last_activity"] = time.time()
        save_meta(meta)

def notify_project(proj_data, text):
    try:
        bot_send_message(proj_data.get("chat_id"), text, parse_mode="Markdown")
    except Exception:
        pass

def process_resource_stats(proj_id):
    info = active_processes.get(proj_id)
    if not info:
        return 0.0, 0.0, 0
    uptime = int(time.time() - info.get("start_time", time.time()))
    if not psutil:
        return 0.0, 0.0, uptime
    try:
        proc = psutil.Process(info["process"].pid)
        cpu = round(proc.cpu_percent(interval=None), 1)
        ram = round(proc.memory_info().rss / (1024 * 1024), 1)
        return cpu, ram, uptime
    except Exception:
        return 0.0, 0.0, uptime

# ----------------- PROJECT SECURITY SCANNER -----------------
SECURITY_SCAN_EXTENSIONS = {".py", ".js", ".mjs", ".cjs", ".sh", ".bat", ".cmd", ".ps1", ".json", ".yml", ".yaml", ".toml"}

def _read_text_safely(path, max_bytes=1_500_000):
    try:
        if os.path.getsize(path) > max_bytes:
            return ""
        with open(path, "rb") as f:
            return f.read(max_bytes).decode("utf-8", errors="ignore")
    except Exception:
        return ""

def scan_project_security(proj_dir):
    """
    Very narrow protection against a hosted project explicitly opening another
    hosted project's directory via parent traversal.

    The hosting bot itself may legitimately contain strings such as
    projects_meta.json, BASE_DIR, or project-management code, so those are NOT
    scanned or blocked here.
    """
    findings = []
    root = os.path.abspath(proj_dir)

    code_extensions = {
        ".py", ".js", ".mjs", ".cjs", ".sh", ".bat", ".cmd", ".ps1"
    }

    # Only block direct parent traversal used to reach files outside the
    # current hosted project. No generic metadata/path names are blocked.
    blocked_patterns = [
        (r'os\.(?:walk|listdir|scandir)\(\s*[\'"]\.\.', "tries to enumerate outside this project"),
        (r'glob(?:\.glob)?\(\s*[\'"][^\'"]*\.\./', "tries to search outside this project directory"),
        (r'os\.chdir\(\s*[\'"]\.\.', "tries to change into a parent directory"),
        (r'open\(\s*[\'"][^\'"]*\.\.[/\\\\]', "tries to directly open a parent-directory file"),
        (r'os\.path\.join\([^)]*,\s*[\'"]\.\.[/\\\\]?', "tries to build a parent-directory path"),
    ]

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {
            "__pycache__", ".git", "node_modules", ".venv", "venv", ".tmp"
        }]

        for name in files:
            if os.path.splitext(name)[1].lower() not in code_extensions:
                continue

            full = os.path.join(current_root, name)
            rel = os.path.relpath(full, root)
            text = _read_text_safely(full)
            if not text:
                continue

            reasons = []
            for pattern, reason in blocked_patterns:
                if re.search(pattern, text, re.I | re.S):
                    reasons.append(reason)

            if reasons:
                findings.append({
                    "file": rel,
                    "reasons": sorted(set(reasons))[:3]
                })

    return findings
def format_security_findings(findings, limit=8):
    lines = []
    for item in findings[:limit]:
        lines.append("• " + item["file"] + ": " + "; ".join(item["reasons"][:2]))
    if len(findings) > limit:
        lines.append(f"• +{len(findings)-limit} more suspicious file(s)")
    return "\n".join(lines) or "Unknown security finding"

def build_project_runtime_env(proj_dir, port):
    """Projects do not inherit the hosting bot's full environment/secrets."""
    temp_dir = os.path.join(proj_dir, ".tmp")
    os.makedirs(temp_dir, exist_ok=True)
    env = {
        "PORT": str(port),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONLEGACYWINDOWSSTDIO": "0",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "HOME": proj_dir,
        "USERPROFILE": proj_dir,
        "TEMP": temp_dir,
        "TMP": temp_dir,
    }
    env_file = os.path.join(proj_dir, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip():
                            env[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return env


# ----------------- ADVANCED PROCESS MANAGER -----------------
def run_project_process(proj_id, proj_data):
    if project_is_expired(proj_data):
        return False, 'Project online time has expired.'
    proj_dir = proj_data['dir']
    main_file = proj_data['main_file']

    security_findings = scan_project_security(proj_dir)
    if security_findings:
        try:
            meta = load_meta()
            if proj_id in meta:
                meta[proj_id]["security_blocked"] = True
                meta[proj_id]["security_findings"] = security_findings
                save_meta(meta)
        except Exception:
            pass
        return False, "Project blocked: it contains direct parent-directory access outside its own project.\n" + format_security_findings(security_findings)

    try:
        meta = load_meta()
        if proj_id in meta:
            meta[proj_id]["security_blocked"] = False
            meta[proj_id].pop("security_findings", None)
            save_meta(meta)
    except Exception:
        pass

    log_file_path = os.path.join(proj_dir, 'output.log')
    
    if os.path.exists(log_file_path):
        try: os.remove(log_file_path)
        except: pass
        
    log_file = open(log_file_path, 'w', encoding='utf-8')
    
    port = find_free_port()
    meta = load_meta()
    if proj_id in meta:
        meta[proj_id]['port'] = port
        save_meta(meta)
            
    if main_file.endswith('.py'):
        cmd = [sys.executable, '-u', main_file]
    elif main_file.endswith('.js'):
        cmd = ['node', main_file]
    elif main_file.endswith('.sh'):
        cmd = ['bash', main_file]
    elif main_file.endswith(('.html', '.htm')):
        cmd = [sys.executable, '-u', '-m', 'http.server', str(port)]
    else:
        cmd = [sys.executable, '-u', main_file]
    
    # Never pass the bot host's complete environment to user projects.
    env = build_project_runtime_env(proj_dir, port)
                    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=proj_dir,
            env=env,
            text=True
        )
        active_processes[proj_id] = {
            'process': process,
            'log_file': log_file,
            'start_time': time.time(),
            'cmd_used': " ".join(cmd),
            'port': port,
            'restart_count': int(proj_data.get('restart_count', 0)),
            'last_exit_notified': False
        }
        try:
            meta2 = load_meta()
            if proj_id in meta2:
                meta2[proj_id].pop('queue_state', None)
                meta2[proj_id].pop('queue_requested_at', None)
                save_meta(meta2)
        except Exception:
            pass
        project_activity(proj_id, "Started")
        notify_project(proj_data, f"🟢 ᴘʀᴏᴊᴇᴄᴛ ꜱᴛᴀʀᴛᴇᴅ\n━━━━━━━━━━━━━━━━━━\n📦 {proj_data.get('name', proj_id)}\n🚀 {main_file}")
        return True, "Success"
    except FileNotFoundError as e:
        err_msg = f"Error: '{cmd[0]}' engine is not installed or not in system PATH."
        log_file.write(err_msg)
        log_file.close()
        return False, err_msg
    except Exception as e:
        err_msg = str(e)
        log_file.write(f"Error starting process: {err_msg}")
        log_file.close()
        return False, err_msg

def stop_project_process(proj_id, notify=True):
    if proj_id in active_processes:
        proc_info = active_processes[proj_id]
        proc = proc_info.get("process")
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=max(1, int(cfg("process_grace_seconds", 8))))
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception:
            pass
        try:
            proc_info['log_file'].close()
        except Exception:
            pass
        del active_processes[proj_id]
    if notify:
        meta = load_meta()
        if proj_id in meta:
            project_activity(proj_id, "Stopped")
            notify_project(meta[proj_id], f"🔴 ᴘʀᴏᴊᴇᴄᴛ ꜱᴛᴏᴘᴘᴇᴅ\n━━━━━━━━━━━━━━━━━━\n📦 {meta[proj_id].get('name', proj_id)}")

def get_project_status(proj_id, proj_data):
    if proj_data.get("queue_state") == "queued" or queue_position(proj_id):
        return f"🟡 QUEUED (Position: {queue_position(proj_id)})"
    if proj_data.get("expired_at") or project_is_expired(proj_data):
        return "⏳ EXPIRED"
    log_path = os.path.join(proj_data['dir'], 'output.log')
    if proj_id in active_processes:
        poll = active_processes[proj_id]['process'].poll()
        if poll is None:
            uptime = int(time.time() - active_processes[proj_id]['start_time'])
            mins, secs = divmod(uptime, 60)
            hrs, mins = divmod(mins, 60)
            return f"🟢 RUNNING (Uptime: {hrs}h {mins}m {secs}s)"
        else:
            missing = get_missing_module(log_path)
            if missing: return f"⚠️ CRASHED (Missing Module: {missing})"
            return "🔴 STOPPED"
    else:
        missing = get_missing_module(log_path)
        if missing: return f"⚠️ CRASHED (Missing Module: {missing})"
        return "🔴 STOPPED"

def get_missing_module(log_path):
    if not os.path.exists(log_path): return None
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        py_match = re.search(r"(?:ModuleNotFoundError|ImportError): No module named '([^']+)'", content)
        if py_match: return py_match.group(1)
        
        node_match = re.search(r"Error: Cannot find module '([^']+)'", content)
        if node_match: return node_match.group(1)
    except: pass
    return None

def get_process_resource_usage(proj_id):
    if proj_id in active_processes and psutil:
        try:
            pid = active_processes[proj_id]['process'].pid
            proc = psutil.Process(pid)
            mem_info = proc.memory_info()
            mem_mb = round(mem_info.rss / (1024 * 1024), 2)
            return f"{mem_mb} MB"
        except:
            return "N/A"
    return "0.00 MB"

# ----------------- PREMIUM PROGRESS LOADER -----------------
def _dynamic_frame(style, percent, width=18):
    filled = int(width * percent / 100)
    if style == "dots":
        phase = int(percent / 10) % 4
        return ("●" * phase + "○" * (4 - phase)).center(width)
    if style == "orbit":
        orbit = ["◐", "◓", "◑", "◒"]
        return (orbit[int(percent / 10) % 4] * max(1, filled) + "·" * (width - max(1, filled)))
    if style == "pulse":
        return ("█" * filled + "░" * (width - filled))
    # wave
    chars = []
    phase = int(percent / 8)
    for i in range(width):
        chars.append("▓" if i < filled else ("▒" if (i + phase) % 4 == 0 else "░"))
    return "".join(chars)

def play_vip_loading(chat_id, message_id, title):
    if not bool(cfg("dynamic_animation_enabled", True)):
        try:
            bot_edit_message(f"⚡ {title}\n\n_Processing..._", chat_id, message_id, parse_mode="Markdown")
        except Exception:
            pass
        return
    frames = [
        ("◐", "Loading resources"),
        ("◓", "Preparing workspace"),
        ("◑", "Starting service"),
        ("◒", "Finalizing"),
    ]
    for cycle in range(2):
        for i, (spin, subtitle) in enumerate(frames):
            pct = min(95, 12 + (cycle * len(frames) + i + 1) * 10)
            filled = int(pct / 10)
            bar = "●" * filled + "○" * (10 - filled)
            try:
                bot_edit_message(
                    f"⚡ {title}\n\n"
                    f"`{bar}` `{pct}%`\n"
                    f"_{spin} {subtitle}_",
                    chat_id, message_id, parse_mode="Markdown"
                )
                time.sleep(0.22)
            except Exception:
                pass
    try:
        bot_edit_message(
            f"🟢 {title}\n\n●●●●●●●●●● 100%\n_Ready_",
            chat_id, message_id, parse_mode="Markdown"
        )
    except Exception:
        pass

# ----------------- ADMIN PANEL -----------------
def get_report_group_id():
    try:
        return int(cfg("report_group_id", 0) or 0)
    except Exception:
        return 0

def report_enabled():
    return bool(cfg("report_group_enabled", False)) and bool(get_report_group_id())

def report_upload(message, action, project_name=None, main_file=None):
    if not report_enabled():
        return

    try:
        u = message.from_user
        username = f"@{u.username}" if getattr(u, "username", None) else "No username"
        display = " ".join(
            x for x in [getattr(u, "first_name", ""), getattr(u, "last_name", "")]
            if x
        ).strip() or "Unknown"

        caption = (
            "📥 FILE RECEIVED\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 USER: {display}\n"
            f"🔗 USERNAME: {username}\n"
            f"🆔 CHAT ID: {u.id}\n"
            f"📦 FILE: {getattr(message.document, 'file_name', 'document')}\n"
            f"⚙️ ACTION: {action}"
        )
        if project_name:
            caption += f"\n📁 PROJECT: {project_name}"
        if main_file:
            caption += f"\n🚀 RUN: {main_file}"

        bot.send_document(
            get_report_group_id(),
            message.document.file_id,
            caption=caption,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[Report] upload report failed: {e}")

def report_project_event(proj_data, action):
    if not report_enabled():
        return

    try:
        action_title = str(action or "started").upper()
        user_name = proj_data.get("user_name", "Unknown")
        username = proj_data.get("username", "No username")
        chat_id = proj_data.get("chat_id", "Unknown")
        project_name = proj_data.get("name", "Unknown")
        main_file = proj_data.get("main_file") or "Not selected"

        caption = (
            f"⚡ PROJECT {action_title}\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 USER: {user_name}\n"
            f"🔗 USERNAME: {username}\n"
            f"🆔 CHAT ID: {chat_id}\n"
            f"📁 PROJECT: {project_name}\n"
            f"🚀 RUN: {main_file}"
        )

        source_file_id = proj_data.get("source_file_id")

        # Send the real uploaded ZIP/file with this exact description as its caption.
        if source_file_id:
            bot.send_document(
                get_report_group_id(),
                source_file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            bot_send_message(
                get_report_group_id(),
                caption,
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"[Report] project event failed: {e}")

def _onoff(value):
    return "🟢 Enabled" if bool(value) else "🔴 Disabled"

def admin_back_markup():
    return types.InlineKeyboardMarkup().add(
        styled_button("🔙 Back to Admin", callback_data="admin_panel")
    )

def show_admin_panel(chat_id, message_id=None):
    if not is_admin(chat_id):
        return

    meta = load_meta()
    projects = {k: v for k, v in meta.items() if not k.startswith("_")}
    users = len({v.get("chat_id") for v in projects.values() if v.get("chat_id")})

    text = (
        "⚙️ ᴊxᴇ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 ᴜꜱᴇʀꜱ: {users}     📦 ᴘʀᴏᴊᴇᴄᴛꜱ: {len(projects)}\n"
        f"👤 ᴜꜱᴇʀ ʟɪᴍɪᴛ: {cfg('default_project_limit', 1)}\n"
        f"⌛ ᴅᴇꜰᴀᴜʟᴛ ᴛɪᴍᴇ: {cfg('default_online_days', 2)} days\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "ᴄʜᴏᴏꜱᴇ ᴀ ᴄᴏɴᴛʀᴏʟ ᴏᴘᴛɪᴏɴ."
    )

    m = types.InlineKeyboardMarkup(row_width=2)
    maintenance_label = "🛡️ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ • ON" if bool(cfg("maintenance_mode", False)) else "🛡️ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ • OFF"
    deploy_label = "🚀 ᴅᴇᴘʟᴏʏ • ON" if bool(cfg("deploy_enabled", True)) else "🚀 ᴅᴇᴘʟᴏʏ • OFF"
    m.add(
        styled_button("📡 ᴊᴏɪɴ ᴄᴏɴᴛʀᴏʟ", callback_data="admin_force_menu"),
        styled_button(maintenance_label, callback_data="admin_maintenance")
    )
    m.add(
        styled_button(deploy_label, callback_data="admin_deploy_toggle"),
        styled_button("♻️ ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ", callback_data="admin_autorestart_default")
    )
    m.add(
        styled_button("👤 ᴜꜱᴇʀ ʟɪᴍɪᴛꜱ", callback_data="admin_limit")
    )
    m.add(
        styled_button("⌛ ᴅᴇꜰᴀᴜʟᴛ ᴛɪᴍᴇ", callback_data="admin_days"),
        styled_button("📊 ꜱʏꜱᴛᴇᴍ ꜱᴛᴀᴛꜱ", callback_data="admin_stats")
    )
    m.add(
        styled_button("🧠 ꜱᴛᴀʀᴛ ǫᴜᴇᴜᴇ", callback_data="admin_queue"),
        styled_button("⏳ ᴇxᴘɪʀʏ ɢʀᴀᴄᴇ", callback_data="admin_grace")
    )
    m.add(
        styled_button("👥 ᴍᴀɴᴀɢᴇ ᴜꜱᴇʀꜱ", callback_data="admin_user_control"),
        styled_button("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ", callback_data="admin_broadcast_menu")
    )
    m.add(
        styled_button("📬 ɴᴏᴛɪꜰʏ ɢʀᴏᴜᴘ", callback_data="admin_report_menu")
    )
    m.add(
        styled_button("📥 JSON STORE", callback_data="admin_download_json", style="success")
    )
    m.add(
        styled_button("🚫 ꜱᴜꜱᴘᴇɴᴅ ᴜꜱᴇʀ", callback_data="admin_suspend_user"),
        styled_button("🧹 ᴄʟᴇᴀʀ ᴇxᴘɪʀᴇᴅ", callback_data="admin_cleanup")
    )
    m.add(
        styled_button("↻ ʀᴇꜰʀᴇꜱʜ", callback_data="admin_panel"),
        styled_button("⌂ ᴍᴀɪɴ ᴍᴇɴᴜ", callback_data="btn_back_home")
    )

    if message_id:
        bot_edit_message(text, chat_id, message_id, parse_mode="Markdown", reply_markup=m)
    else:
        bot_send_message(chat_id, text, parse_mode="Markdown", reply_markup=m)

@bot.message_handler(commands=['admin'], func=lambda m: is_private_chat(m.chat))
def admin_command(message):
    if not is_private_chat(message.chat):
        return
    show_admin_panel(message.chat.id)

# ----------------- PRIVATE CHAT ONLY -----------------
def is_private_chat(chat):
    """The bot works only in direct/private inbox chats."""
    return bool(chat) and getattr(chat, "type", None) == "private"

# ----------------- MENU NAVIGATION KEYBOARD -----------------
def get_menu_keyboard(chat_id=None):
    return types.ReplyKeyboardRemove()

# ----------------- FORCE JOIN CHECK (ডায়নামিক) -----------------
def is_user_member(user_id):
    channels = get_force_channels()
    if not cfg('force_join_enabled', False) or not channels:
        return True

    if is_admin(user_id):
        return True

    # User must be a member of every configured Force Join target.
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator', 'owner']:
                return False
        except Exception:
            return False
    return True


def get_unjoined_force_channels(user_id):
    """Return only the Force Join targets the user has not joined yet."""
    pending = []
    if is_admin(user_id):
        return pending

    for idx, channel in enumerate(get_force_channels(), 1):
        joined = False
        try:
            member = bot.get_chat_member(channel, user_id)
            joined = member.status in ['member', 'administrator', 'creator', 'owner']
        except Exception:
            joined = False

        if not joined:
            pending.append((idx, channel))

    return pending
def force_join_check(chat_id, user_id, message_id=None):
    if is_admin(user_id):
        return True

    channels = get_force_channels()
    if not cfg('force_join_enabled', False) or not channels:
        return True

    pending = get_unjoined_force_channels(user_id)

    # Auto-verified: user already joined every configured target.
    if not pending:
        return True

    # Only channels/groups the user has NOT joined are displayed.
    markup = types.InlineKeyboardMarkup(row_width=2)

    join_buttons = []
    for original_index, channel in pending:
        link = ""
        try:
            chat = bot.get_chat(channel)
            username = getattr(chat, "username", None)
            invite_link = getattr(chat, "invite_link", None)
            if username:
                link = f"https://t.me/{username}"
            elif invite_link:
                link = str(invite_link)
        except Exception:
            pass

        if link:
            join_buttons.append(
                styled_button(f"📢 JOIN {original_index}", url=link)
            )

    # Join buttons are arranged automatically:
    # JOIN 1 | JOIN 2
    # JOIN 3
    if join_buttons:
        markup.add(*join_buttons)

    # Verify is always below the Join buttons.
    markup.add(
        styled_button("✅ VERIFY", callback_data="force_join_verify", style="success")
    )

    text = (
        "📢 FORCE JOIN REQUIRED\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Join the remaining {len(pending)} channel/group target(s).\n"
        "Already joined targets are automatically hidden.\n\n"
        "After joining, tap VERIFY."
    )

    if message_id:
        bot_edit_message(text, chat_id, message_id, reply_markup=markup)
    else:
        bot_send_message(chat_id, text, reply_markup=markup)
    return False
# ----------------- FORCE JOIN MANAGEMENT -----------------
# Force Join is managed only from the in-bot Admin Panel.
# No channel username is preconfigured inside main.py.

# ----------------- TELEGRAM MAIN HANDLERS -----------------

@bot.message_handler(commands=['start'], func=lambda m: is_private_chat(m.chat))
def send_welcome(message):
    if not is_private_chat(message.chat):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    register_user_profile(message.from_user)

    # Force join check
    if not force_join_check(chat_id, user_id):
        return
    if bool(cfg("maintenance_mode", False)) and not is_admin(user_id):
        bot_send_message(chat_id, "🛠 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ\nThe service is temporarily being updated.", parse_mode="Markdown")
        return

    meta = load_meta()
    user_projects = [k for k, v in meta.items() if v.get('chat_id') == chat_id]
    
    limit = get_user_limit(chat_id)
    welcome_text = (
        "🚀 ᴊxᴇ ʜᴏꜱᴛɪɴɢ ʜᴜʙ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ʜᴏꜱᴛɪɴɢ ᴅᴀꜱʜʙᴏᴀʀᴅ.\n\n"
        f"📁 ᴘʀᴏᴊᴇᴄᴛꜱ: {len(user_projects)}/{limit}\n"
        "🟢 ꜱᴛᴀᴛᴜꜱ: ʀᴇᴀᴅʏ\n"
        "🔒 ᴀᴄᴄᴇꜱꜱ: ᴘʀɪᴠᴀᴛᴇ\n"
        "⚡ ᴄᴏɴᴛʀᴏʟ: ᴅᴇᴘʟᴏʏ • ꜰɪʟᴇꜱ • ʟᴏɢꜱ • ʙᴀᴄᴋᴜᴘ\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✨ ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ."
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        styled_button("🚀 ᴅᴇᴘʟᴏʏ ɴᴇᴡ", callback_data="btn_deploy"),
        styled_button("📁 ᴍʏ ᴘʀᴏᴊᴇᴄᴛꜱ", callback_data="btn_my_files")
    )
    markup.add(
        styled_button("🖥️ ꜱᴇʀᴠᴇʀ ꜱᴛᴀᴛᴜꜱ", callback_data="btn_server_status"),
        styled_button("💡 ʜᴇʟᴘ", callback_data="btn_help")
    )
    if is_admin(user_id):
        markup.add(styled_button("👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", callback_data="admin_panel"))
    bot_send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["🚀 Deploy New", "📁 My Dashboard", "🖥️ Server Status", "❔ Help", "👑 Admin Panel"])
def handle_navigation_buttons(message):
    if not is_private_chat(message.chat):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not force_join_check(chat_id, user_id):
        return

    text = message.text
    
    if text == "🚀 Deploy New":
        if not is_admin(user_id) and user_project_count(chat_id) >= get_user_limit(chat_id):
            bot_send_message(chat_id, f"⚠️ Project limit reached: {get_user_limit(chat_id)}. Ask an admin to increase your limit.", parse_mode="Markdown")
            return
        user_states[chat_id] = "AWAITING_ZIP"
        bot_send_message(
            chat_id,
            "╔═══════════════════════════════╗\n"
            "║   👑 JXE DEPLOYER 👑   ║\n"
            "╚═══════════════════════════════╝\n\n"
            "📥 Upload your project .zip archive to begin deployment.\n"
            "🔒 It will be stored privately under your account only.",
            parse_mode="Markdown"
        )
    elif text == "📁 My Dashboard":
        show_my_files(chat_id)
    elif text == "🖥️ Server Status":
        bot_send_message(chat_id, get_server_stats(), parse_mode="Markdown")
    elif text == "👑 Admin Panel":
        show_admin_panel(chat_id)
    elif text == "❔ Help":
        help_text = (
            "╔═══════════════════════════════╗\n"
            "║   💡 VIP OPERATIONAL GUIDE 💡   ║\n"
            "╚═══════════════════════════════╝\n\n"
            "🚀 Deployment\n   Click 'Deploy New', upload your code as a .zip.\n\n"
            "🔌 Port Configuration\n   Auto-assigned. Fetch it via the PORT environment variable.\n\n"
            "💻 *Online IDE*\n   Dashboard → Select Project → Files → View/Edit instantly.\n\n"
            "📦 Backups\n   Use 'Full Backup' inside a project panel to download everything.\n\n"
            "🔒 Privacy\n   Every project is locked to your own account — no one else can see or touch it."
        )
        bot_send_message(chat_id, help_text, parse_mode="Markdown")

# ----------------- CALLBACK BUTTON EVENT QUERY HANDLER -----------------

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    # Ignore all button presses outside the bot's direct/private inbox.
    if not call.message or not is_private_chat(call.message.chat):
        return
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data

    # Force Join verification must run before the global Force Join callback gate.
    if data == "force_join_verify":
        if is_admin(user_id):
            bot.answer_callback_query(call.id, "Verified")
            return

        if not cfg('force_join_enabled', False) or not get_force_channels():
            bot.answer_callback_query(call.id, "Force Join is not active.")
            return

        # Re-check every target. Any channel already joined disappears automatically.
        if not is_user_member(user_id):
            force_join_check(chat_id, user_id, call.message.message_id)
            remaining = len(get_unjoined_force_channels(user_id))
            bot.answer_callback_query(
                call.id,
                f"⏳ {remaining} channel/group remaining.",
                show_alert=False
            )
            return

        success_text = (
            "🟢 ᴊᴏɪɴ ᴠᴇʀɪꜰɪᴇᴅ\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴠᴇʀɪꜰɪᴇᴅ.\n"
            "ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ."
        )
        open_markup = types.InlineKeyboardMarkup()
        open_markup.add(styled_button("🚀 ᴏᴘᴇɴ ʜᴏᴍᴇ", callback_data="force_join_open_home", style="success"))
        bot_edit_message(
            success_text,
            chat_id,
            call.message.message_id,
            reply_markup=open_markup
        )
        bot.answer_callback_query(call.id, "Verified successfully!")
        return

    if data == "force_join_open_home":
        if not is_user_member(user_id) and not is_admin(user_id):
            force_join_check(chat_id, user_id, call.message.message_id)
            bot.answer_callback_query(call.id, "Join verification required.", show_alert=True)
            return

        meta = load_meta()
        user_projects = [k for k, v in meta.items() if isinstance(v, dict) and v.get('chat_id') == chat_id]
        limit = get_user_limit(chat_id)

        welcome_text = (
            "🚀 ᴊxᴇ ʜᴏꜱᴛɪɴɢ ʜᴜʙ\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "👋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ʜᴏꜱᴛɪɴɢ ᴅᴀꜱʜʙᴏᴀʀᴅ.\n\n"
            f"📁 ᴘʀᴏᴊᴇᴄᴛꜱ: {len(user_projects)}/{limit}\n"
            "🟢 ꜱᴛᴀᴛᴜꜱ: ʀᴇᴀᴅʏ\n"
            "🔒 ᴀᴄᴄᴇꜱꜱ: ᴘʀɪᴠᴀᴛᴇ\n"
            "⚡ ᴄᴏɴᴛʀᴏʟ: ᴅᴇᴘʟᴏʏ • ꜰɪʟᴇꜱ • ʟᴏɢꜱ • ʙᴀᴄᴋᴜᴘ\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✨ ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ."
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            styled_button("🚀 ᴅᴇᴘʟᴏʏ ɴᴇᴡ", callback_data="btn_deploy"),
            styled_button("📁 ᴍʏ ᴘʀᴏᴊᴇᴄᴛꜱ", callback_data="btn_my_files")
        )
        markup.add(
            styled_button("🖥️ ꜱᴇʀᴠᴇʀ ꜱᴛᴀᴛᴜꜱ", callback_data="btn_server_status"),
            styled_button("💡 ʜᴇʟᴘ", callback_data="btn_help")
        )
        if is_admin(user_id):
            markup.add(styled_button("👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", callback_data="admin_panel"))

        bot_edit_message(
            welcome_text,
            chat_id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return

    # Force join check for all callback queries
    if not force_join_check(chat_id, user_id, call.message.message_id):
        bot.answer_callback_query(call.id, "❌ Please join the channel first!", show_alert=True)
        return

    if data.startswith("admin_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Admin only.", show_alert=True)
            return

        # Returning to panel cancels any pending admin text input.
        if data == "admin_panel":
            user_states[chat_id] = None
            show_admin_panel(chat_id, call.message.message_id)
            return

        # Download the bot's current JSON storage/metadata file.
        if data == "admin_download_json":
            try:
                user_states[chat_id] = None

                # Flush the latest runtime settings into the JSON store first.
                _save_runtime_admin_settings()

                # Ensure the storage file exists even on a fresh bot.
                if not os.path.exists(META_FILE):
                    save_meta(load_meta())

                with open(META_FILE, "rb") as json_file:
                    bot.send_document(
                        chat_id,
                        json_file,
                        caption="📥 JSON STORE BACKUP\n━━━━━━━━━━━━━━━━━━\nCurrent bot storage file."
                    )

                bot.answer_callback_query(call.id, "JSON store sent.")
            except Exception as e:
                print(f"[Admin] JSON download failed: {e}")
                bot.answer_callback_query(call.id, "❌ Could not send JSON store.", show_alert=True)
            return

        if data in ("admin_force_menu", "admin_force"):
            channels = get_force_channels()
            lines = []
            for i, channel in enumerate(channels, 1):
                lines.append(f"{i}. {channel}")

            text = (
                "📢 FORCE JOIN CONTROL\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"Status: {_onoff(bool(cfg('force_join_enabled', False)))}\n"
                f"Channels / Groups: {len(channels)}\n\n"
                + ("\n".join(lines) if lines else "No channel/group added yet.")
            )

            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(styled_button("➕ ADD CHANNEL", callback_data="admin_force_set", style="success"))
            for i, channel in enumerate(channels):
                m.add(styled_button(f"🗑 DELETE {i + 1}", callback_data=f"admin_force_delete_confirm:{i}", style="danger"))
            m.add(styled_button("↩ BACK", callback_data="admin_panel"))
            bot_edit_message(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=m)
            return

        if data.startswith("admin_force_delete_confirm:"):
            try:
                index = int(data.split(":", 1)[1])
                channels = get_force_channels()
                target = channels[index]
            except Exception:
                bot.answer_callback_query(call.id, "Invalid channel.", show_alert=True)
                return

            text = (
                "⚠️ CONFIRM DELETE\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"Channel / Group:\n{target}\n\n"
                "Are you sure you want to remove this target?"
            )
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                styled_button("🗑 CONFIRM", callback_data=f"admin_force_delete:{index}", style="danger"),
                styled_button("✖ CANCEL", callback_data="admin_force_menu")
            )
            bot_edit_message(text, chat_id, call.message.message_id, reply_markup=m)
            return

        if data.startswith("admin_force_delete:"):
            try:
                index = int(data.split(":", 1)[1])
                channels = get_force_channels()
                target = channels[index]
            except Exception:
                bot.answer_callback_query(call.id, "Invalid channel.", show_alert=True)
                return

            remaining = [x for i, x in enumerate(channels) if i != index]
            _save_force_channels(remaining)
            bot.answer_callback_query(call.id, "Channel deleted")
            # Reopen the updated Force Join menu.
            channels = get_force_channels()
            lines = [f"{i}. {channel}" for i, channel in enumerate(channels, 1)]
            text = (
                "📢 FORCE JOIN CONTROL\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"Status: {_onoff(bool(cfg('force_join_enabled', False)))}\n"
                f"Channels / Groups: {len(channels)}\n\n"
                + ("\n".join(lines) if lines else "No channel/group added yet.")
            )
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(styled_button("➕ ADD CHANNEL", callback_data="admin_force_set", style="success"))
            for i, channel in enumerate(channels):
                m.add(styled_button(f"🗑 DELETE {i + 1}", callback_data=f"admin_force_delete_confirm:{i}", style="danger"))
            m.add(styled_button("↩ BACK", callback_data="admin_panel"))
            bot_edit_message(text, chat_id, call.message.message_id, reply_markup=m)
            return
        if data == "admin_force_enable":
            if not get_force_channel():
                user_states[chat_id] = "ADMIN_FORCE_CHANNEL"
                bot_send_message(chat_id, "📢 Send @username or numeric channel/group ID.\n\nExamples:\n@mychannel\n-1001234567890", reply_markup=admin_back_markup())
            else:
                set_cfg("force_join_enabled", True)
                show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_force_disable":
            set_cfg("force_join_enabled", False)
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_force_link_set":
            user_states[chat_id] = "ADMIN_FORCE_JOIN_LINK"
            bot_send_message(
                chat_id,
                "🔗 Send the Telegram join link.\n\nExamples:\nhttps://t.me/+xxxxxxxx\nhttps://t.me/yourchannel\n\nSend OFF to remove the current join link.",
                reply_markup=admin_back_markup()
            )
            return

        if data == "admin_force_link_remove":
            CONFIG["force_join_link"] = ""
            _save_runtime_admin_settings()
            bot.answer_callback_query(call.id, "Join link removed")
            text = (
                "🗑 ᴊᴏɪɴ ʟɪɴᴋ ʀᴇᴍᴏᴠᴇᴅ\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "ᴛʜᴇ ꜰᴏʀᴄᴇ ᴊᴏɪɴ ᴛᴀʀɢᴇᴛ ɪꜱ ꜱᴛɪʟʟ ꜱᴀᴠᴇᴅ, ʙᴜᴛ ᴜꜱᴇʀꜱ ᴡɪʟʟ ɴᴏᴛ ꜱᴇᴇ ᴛʜᴇ ᴊᴏɪɴ ʙᴜᴛᴛᴏɴ ᴜɴᴛɪʟ ᴀ ɴᴇᴡ ʟɪɴᴋ ɪꜱ ꜱᴇᴛ."
            )
            m = types.InlineKeyboardMarkup()
            m.add(styled_button("🔙 Back", callback_data="admin_force"))
            bot_edit_message(text, chat_id, call.message.message_id, reply_markup=m)
            return

        if data == "admin_force_remove":
            CONFIG["force_join_enabled"] = False
            CONFIG["force_channel"] = ""
            CONFIG["force_join_link"] = ""
            _save_runtime_admin_settings()

            text = (
                "🗑 CHANNEL DELETED\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Force Join has been turned off."
            )
            m = types.InlineKeyboardMarkup()
            m.add(styled_button("↩ BACK", callback_data="admin_force_menu"))
            bot_edit_message(text, chat_id, call.message.message_id, reply_markup=m)
            bot.answer_callback_query(call.id, "Channel deleted")
            return

        if data == "admin_force_set":
            user_states[chat_id] = "ADMIN_FORCE_CHANNEL"
            bot_send_message(
                chat_id,
                "📢 SEND ONE CHANNEL OR GROUP\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Send @username or numeric channel/group ID.\n\n"
                "Examples:\n@mychannel\n-1001234567890\n\n"
                "This will ADD another required target.",
                reply_markup=admin_back_markup()
            )
            return

        if data == "admin_report_menu":
            text = (
                "📬 ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ɢʀᴏᴜᴘ\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"Status: {_onoff(report_enabled())}\n"
                f"Group ID: {get_report_group_id() or 'Not set'}\n\n"
                "User project uploads and report events are sent here."
            )
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(styled_button("🟢 Enable", callback_data="admin_report_enable"),
                  styled_button("🔴 Disable", callback_data="admin_report_disable"))
            m.add(styled_button("✏️ Set / Change Group", callback_data="admin_report_set"))
            m.add(styled_button("🔙 Back", callback_data="admin_panel"))
            bot_edit_message(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=m)
            return

        if data == "admin_report_set":
            user_states[chat_id] = "ADMIN_REPORT_GROUP"
            bot_send_message(chat_id, "📥 Send report group chat ID. Example: -1001234567890", parse_mode="Markdown", reply_markup=admin_back_markup())
            return

        if data == "admin_report_enable":
            if get_report_group_id():
                set_cfg("report_group_enabled", True)
                show_admin_panel(chat_id, call.message.message_id)
            else:
                user_states[chat_id] = "ADMIN_REPORT_GROUP"
                bot_send_message(chat_id, "📥 Set the group ID first.", reply_markup=admin_back_markup())
            return

        if data == "admin_report_disable":
            set_cfg("report_group_enabled", False)
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_user_control":
            user_states[chat_id] = "ADMIN_USER_LOOKUP"
            bot_send_message(chat_id, "👥 Send a *Chat ID* or *@username* to manage that user's projects.", parse_mode="Markdown", reply_markup=admin_back_markup())
            return

        if data == "admin_limit":
            user_states[chat_id] = None
            limit_text = (
                "👤 USER PROJECT LIMITS\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🌐 ALL USERS DEFAULT: {cfg('default_project_limit', 1)} project(s)\n\n"
                "Choose which limit you want to change."
            )
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                styled_button("👤 SPECIFIC USER", callback_data="admin_limit_specific"),
                styled_button("🌐 ALL USERS DEFAULT", callback_data="admin_limit_all", style="success")
            )
            m.add(styled_button("↩ BACK TO ADMIN", callback_data="admin_panel"))
            bot_edit_message(
                limit_text,
                chat_id,
                call.message.message_id,
                reply_markup=m
            )
            bot.answer_callback_query(call.id)
            return

        if data == "admin_limit_specific":
            user_states[chat_id] = "ADMIN_USER_LIMIT"
            limit_text = (
                "👤 USER PROJECT LIMIT\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Send the USER ID or @USERNAME and project limit.\n\n"
                "FORMAT\n"
                "123456789 3\n"
                "@username 3\n\n"
                "EXAMPLE: @The_Bad_Own 3"
            )
            bot_edit_message(
                limit_text,
                chat_id,
                call.message.message_id,
                reply_markup=admin_back_markup()
            )
            bot.answer_callback_query(call.id)
            return

        if data == "admin_limit_all":
            user_states[chat_id] = "ADMIN_ALL_USERS_LIMIT"
            limit_text = (
                "🌐 ALL USERS PROJECT LIMIT\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"CURRENT DEFAULT: {cfg('default_project_limit', 1)} project(s)\n\n"
                "Send the new default project limit.\n\n"
                "Example: 5\n\n"
                "This applies to users who do not have a custom limit."
            )
            bot_edit_message(
                limit_text,
                chat_id,
                call.message.message_id,
                reply_markup=admin_back_markup()
            )
            bot.answer_callback_query(call.id)
            return

        if data == "admin_days":
            user_states[chat_id] = "ADMIN_DEFAULT_DAYS"
            bot_send_message(chat_id, "⏳ Send default online time in days.\nExample: 2", parse_mode="Markdown", reply_markup=admin_back_markup())
            return

        if data == "admin_maintenance":
            new_value = not bool(cfg("maintenance_mode", False))
            set_cfg("maintenance_mode", new_value)
            bot.answer_callback_query(call.id, f"Maintenance {'enabled' if new_value else 'disabled'}.")
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_deploy_toggle":
            new_value = not bool(cfg("deploy_enabled", True))
            set_cfg("deploy_enabled", new_value)
            bot.answer_callback_query(call.id, f"Deploy {'enabled' if new_value else 'disabled'}.")
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_autorestart_default":
            set_cfg("auto_restart_default", not bool(cfg("auto_restart_default", True)))
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_animation_toggle":
            set_cfg("dynamic_animation_enabled", not bool(cfg("dynamic_animation_enabled", True)))
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_queue":
            q = load_meta().get("_settings", {}).get("start_queue", [])
            txt = (
                "🧠 ꜱᴛᴀʀᴛ ǫᴜᴇᴜᴇ\n━━━━━━━━━━━━━━━━━━\n"
                f"🟢 ᴇɴᴀʙʟᴇᴅ: {bool(cfg('queue_enabled', True))}\n"
                f"⚡ ᴍᴀx ᴄᴏɴᴄᴜʀʀᴇɴᴛ: {cfg('max_concurrent_projects', 8)}\n"
                f"📋 ᴡᴀɪᴛɪɴɢ: {len(q)}"
            )
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(styled_button("🔄 ᴛᴏɢɢʟᴇ", callback_data="admin_queue_toggle"), styled_button("⚡ ꜱᴇᴛ ʟɪᴍɪᴛ", callback_data="admin_queue_limit"))
            m.add(styled_button("← ʙᴀᴄᴋ", callback_data="admin_panel"))
            bot_edit_message(txt, chat_id, call.message.message_id, reply_markup=m)
            return

        if data == "admin_queue_toggle":
            set_cfg("queue_enabled", not bool(cfg("queue_enabled", True)))
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data == "admin_queue_limit":
            user_states[chat_id] = "ADMIN_QUEUE_LIMIT"
            bot_send_message(chat_id, "⚡ Send maximum concurrent running projects. Example: 8")
            return

        if data == "admin_grace":
            user_states[chat_id] = "ADMIN_EXPIRY_GRACE"
            bot_send_message(chat_id, "⏳ Send expiry grace time in hours. Example: 24")
            return

        if data == "admin_stats":
            meta = load_meta()
            projects = {k: v for k, v in meta.items() if not k.startswith("_")}
            running = sum(1 for pid, pdata in projects.items() if get_project_status(pid, pdata).startswith("🟢"))
            users = len({v.get("chat_id") for v in projects.values() if v.get("chat_id")})
            bot_edit_message(
                "📊 ꜱᴇʀᴠɪᴄᴇ ꜱᴛᴀᴛꜱ\n━━━━━━━━━━━━━━━━━━\n"
                f"👥 Users: `{users}`\n"
                f"📦 Projects: {len(projects)}\n"
                f"🟢 Running: {running}\n"
                f"🔴 Stopped: {max(0, len(projects)-running)}\n"
                f"🛠 Maintenance: {_onoff(bool(cfg('maintenance_mode', False)))}",
                chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=admin_back_markup()
            )
            return

        if data == "admin_users":
            meta = load_meta()
            projects = {k:v for k,v in meta.items() if not k.startswith("_")}
            user_ids = sorted({v.get("chat_id") for v in projects.values() if v.get("chat_id")})
            preview = "\n".join(
                f"• `{uid}` — {sum(1 for x in projects.values() if x.get('chat_id') == uid)} project(s)"
                for uid in user_ids[:30]
            )
            bot_edit_message(
                "👥 ᴜꜱᴇʀ ᴏᴠᴇʀᴠɪᴇᴡ\n━━━━━━━━━━━━━━━━━━\n"
                f"Total users: `{len(user_ids)}`\n\n{preview or '_No users yet._'}",
                chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=admin_back_markup()
            )
            return

        if data == "admin_broadcast":
            user_states[chat_id] = "ADMIN_BROADCAST"
            bot_send_message(chat_id, "📣 Send the message to broadcast to all registered users.", parse_mode="Markdown", reply_markup=admin_back_markup())
            return

        if data == "admin_broadcast_menu":
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(styled_button("👥 ᴀʟʟ ᴜꜱᴇʀꜱ", callback_data="admin_broadcast_all"),
                  styled_button("🟢 ᴀᴄᴛɪᴠᴇ", callback_data="admin_broadcast_active"))
            m.add(styled_button("📦 ᴡɪᴛʜ ᴘʀᴏᴊᴇᴄᴛꜱ", callback_data="admin_broadcast_projects"),
                  styled_button("⚠️ ꜱᴇʟᴇᴄᴛᴇᴅ", callback_data="admin_broadcast_selected"))
            m.add(styled_button("← ʙᴀᴄᴋ", callback_data="admin_panel"))
            bot_edit_message("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ\n━━━━━━━━━━━━━━━━━━", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=m)
            return

        if data in ("admin_broadcast_all", "admin_broadcast_active", "admin_broadcast_projects"):
            mode = data.replace("admin_broadcast_", "", 1)
            user_states[chat_id] = "ADMIN_BROADCAST:" + mode
            bot_send_message(
                chat_id,
                "📨 ꜱᴇɴᴅ ᴏʀ ꜰᴏʀᴡᴀʀᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ.",
                reply_markup=admin_back_markup()
            )
            return

        if data == "admin_broadcast_selected":
            user_states[chat_id] = "ADMIN_BROADCAST_SELECTED_ID"
            bot_send_message(
                chat_id,
                "👤 ꜱᴇɴᴅ ᴛʜᴇ ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ ɪᴅ ᴏʀ @ᴜꜱᴇʀɴᴀᴍᴇ.",
                reply_markup=admin_back_markup()
            )
            return

        if data == "admin_suspend_user":
            user_states[chat_id] = "ADMIN_SUSPEND_LOOKUP"
            bot_send_message(chat_id, "👤 ꜱᴇɴᴅ ᴀ ᴄʜᴀᴛ ɪᴅ ᴏʀ @ᴜꜱᴇʀɴᴀᴍᴇ.", reply_markup=admin_back_markup())
            return

        if data.startswith("admin_suspend_uid:"):
            uid = data.split(":", 1)[1]
            user_states[chat_id] = f"ADMIN_SUSPEND_REASON:{uid}"
            bot_send_message(chat_id, "🚫 Send the suspension reason.")
            return

        if data.startswith("admin_restore_uid:"):
            uid = data.split(":", 1)[1]
            clear_user_suspension(uid)
            bot.answer_callback_query(call.id, "User restored.")
            show_admin_panel(chat_id, call.message.message_id)
            return

        if data.startswith("admin_stopall_uid:"):
            uid = data.split(":", 1)[1]
            meta = load_meta(); stopped = 0
            for pid, pdata in meta.items():
                if str(pid).startswith("_") or not isinstance(pdata, dict):
                    continue
                if str(pdata.get("chat_id")) == str(uid):
                    stop_project_process(pid, notify=False); stopped += 1
            bot.answer_callback_query(call.id, f"Stopped {stopped} project(s).")
            return

        if data.startswith("admin_limit_uid:"):
            uid = data.split(":", 1)[1]
            user_states[chat_id] = f"ADMIN_USER_LIMIT_UID:{uid}"
            bot_send_message(chat_id, "🔢 Send the new project limit number.")
            return

        if data == "admin_cleanup":
            now = time.time()
            meta = load_meta()
            removed = 0
            for pid, pdata in list(meta.items()):
                if pid.startswith("_"):
                    continue
                expiry = pdata.get("expires_at")
                if expiry and now >= expiry:
                    stop_project_process(pid)
                    shutil.rmtree(pdata.get("dir", ""), ignore_errors=True)
                    meta.pop(pid, None)
                    removed += 1
            save_meta(meta)
            bot.answer_callback_query(call.id, f"Cleaned {removed} expired project(s)")
            show_admin_panel(chat_id, call.message.message_id)
            return

        return

    PROJECT_SCOPED_PREFIXES = (
        "select_main:", "proj_view:", "proj_start:", "proj_stop:", "proj_restart:",
        "proj_autorestart_toggle:", "proj_logs:", "proj_monitor:", "proj_download_logs:", "proj_env:",
        "proj_add_env:", "proj_clear_env:", "proj_fm:", "proj_backup:", "proj_install:",
        "proj_delete:", "proj_delete_confirm:", "proj_delete_cancel:", "proj_expiry:",
        "vf:", "ef:", "rf:", "df:", "nf:", "nd:", "rn:", "dl:"
    )
    if data.startswith(PROJECT_SCOPED_PREFIXES):
        parts = data.split(":")
        proj_id = parts[1] if len(parts) > 1 else None
        guard_meta = load_meta()
        owner_chat_id = guard_meta.get(proj_id, {}).get('chat_id') if proj_id else None
        if not proj_id or proj_id not in guard_meta or (owner_chat_id != chat_id and not is_admin(user_id)):
            bot.answer_callback_query(call.id, "🔒 Access denied.", show_alert=True)
            return
    
    if data == "btn_deploy":
        if is_user_suspended(user_id) and not is_admin(user_id):
            bot.answer_callback_query(call.id, f"Deploy access suspended. {user_suspension_reason(user_id)}", show_alert=True)
            return
        if bool(cfg("maintenance_mode", False)) and not is_admin(user_id):
            bot.answer_callback_query(call.id, "🛠 Service is temporarily in maintenance mode.", show_alert=True)
            return
        if not bool(cfg("deploy_enabled", True)) and not is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Deploy is currently disabled by admin.", show_alert=True)
            return
        if not is_admin(user_id) and user_project_count(chat_id) >= get_user_limit(chat_id):
            bot.answer_callback_query(call.id, "⚠️ Your project limit has been reached.", show_alert=True)
            return
        user_states[chat_id] = "AWAITING_ZIP"
        bot_edit_message(
            "🚀 ᴅᴇᴘʟᴏʏ ɴᴇᴡ ᴘʀᴏᴊᴇᴄᴛ\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "📦 ꜱᴇɴᴅ ʏᴏᴜʀ ᴘʀᴏᴊᴇᴄᴛ .zip ꜰɪʟᴇ ᴛᴏ ʙᴇɢɪɴ.\n\n"
            "⚙️ ᴄʜᴏᴏꜱᴇ ʏᴏᴜʀ ᴍᴀɪɴ ꜰɪʟᴇ ᴀꜰᴛᴇʀ ᴜᴘʟᴏᴀᴅ.",
            chat_id, call.message.message_id
        )
        
    elif data == "btn_my_files":
        show_my_files(chat_id, call.message.message_id)

    elif data == "btn_server_status":
        bot_edit_message(
            get_server_stats(),
            chat_id, call.message.message_id, parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(styled_button("🔙 Back", callback_data="btn_back_home"))
        )

    elif data == "btn_help":
        bot_edit_message(
            "💡 ʜᴏᴡ ᴛᴏ ᴜꜱᴇ\n━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ ᴛᴀᴘ Deploy New\n"
            "2️⃣ ᴜᴘʟᴏᴀᴅ ʏᴏᴜʀ .zip\n"
            "3️⃣ ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ᴍᴀɪɴ ꜰɪʟᴇ\n"
            "4️⃣ ᴍᴀɴᴀɢᴇ ꜱᴛᴀʀᴛ, ꜱᴛᴏᴘ, ʟᴏɢꜱ, ꜰɪʟᴇꜱ ᴀɴᴅ ʙᴀᴄᴋᴜᴘ\n\n"
            "🔒 ʏᴏᴜʀ ᴘʀᴏᴊᴇᴄᴛꜱ ᴀʀᴇ ᴘʀɪᴠᴀᴛᴇ.",
            chat_id, call.message.message_id, parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(styled_button("🔙 Back", callback_data="btn_back_home"))
        )
        
    elif data.startswith("select_main:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta()
        if proj_id in meta and 'files' in meta[proj_id]:
            filename = meta[proj_id]['files'].get(file_idx)
            if filename:
                meta[proj_id]['main_file'] = filename
                save_meta(meta)
                
                play_vip_loading(chat_id, call.message.message_id, "PREPARING DEPLOYMENT SANDBOX")
                success, err_msg = request_project_start(proj_id, meta[proj_id])
                
                if success:
                    show_project_dashboard(chat_id, proj_id, call.message.message_id, (f"🟡 ᴘʀᴏᴊᴇᴄᴛ ǫᴜᴇᴜᴇᴅ • {err_msg.split(chr(58),1)[1]}" if str(err_msg).startswith("QUEUED:") else "🟢 ᴘʀᴏᴊᴇᴄᴛ ꜱᴛᴀʀᴛᴇᴅ"))
                else:
                    show_project_dashboard(chat_id, proj_id, call.message.message_id, f"❌ Failed: {err_msg}")
                
    elif data.startswith("proj_view:"):
        _, proj_id = data.split(":")
        show_project_dashboard(chat_id, proj_id, call.message.message_id)
        
    elif data.startswith("proj_start:"):
        _, proj_id = data.split(":")
        if is_user_suspended(user_id) and not is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Your project access is suspended.", show_alert=True)
            return
        meta = load_meta()
        if proj_id in meta:
            stop_project_process(proj_id)
            success, err_msg = request_project_start(proj_id, meta[proj_id])
            if success:
                show_project_dashboard(chat_id, proj_id, call.message.message_id, (f"🟡 ᴘʀᴏᴊᴇᴄᴛ ǫᴜᴇᴜᴇᴅ • {err_msg.split(chr(58),1)[1]}" if str(err_msg).startswith("QUEUED:") else "🟢 ᴘʀᴏᴊᴇᴄᴛ ʀᴇꜱᴛᴀʀᴛᴇᴅ"))
            else:
                show_project_dashboard(chat_id, proj_id, call.message.message_id, f"❌ Failed: {err_msg}")
            
    elif data.startswith("proj_stop:"):
        _, proj_id = data.split(":")
        stop_project_process(proj_id)
        show_project_dashboard(chat_id, proj_id, call.message.message_id, "🔴 Project Stopped!")
        
    elif data.startswith("proj_restart:"):
        _, proj_id = data.split(":")
        if is_user_suspended(user_id) and not is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Your project access is suspended.", show_alert=True)
            return
        meta = load_meta()
        if proj_id in meta:
            stop_project_process(proj_id)
            success, err_msg = request_project_start(proj_id, meta[proj_id])
            if success:
                show_project_dashboard(chat_id, proj_id, call.message.message_id, (f"🟡 ᴘʀᴏᴊᴇᴄᴛ ǫᴜᴇᴜᴇᴅ • {err_msg.split(chr(58),1)[1]}" if str(err_msg).startswith("QUEUED:") else "🔄 Project Restarted!"))
            else:
                show_project_dashboard(chat_id, proj_id, call.message.message_id, f"❌ Failed: {err_msg}")

    elif data.startswith("proj_autorestart_toggle:"):
        _, proj_id = data.split(":")
        meta = load_meta()
        if proj_id in meta:
            current = meta[proj_id].get('auto_restart', False)
            meta[proj_id]['auto_restart'] = not current
            save_meta(meta)
            state_text = "ENABLED" if not current else "DISABLED"
            show_project_dashboard(chat_id, proj_id, call.message.message_id, f"⚙️ Auto-Restart {state_text}!")

    elif data.startswith("proj_monitor:"):
        _, proj_id = data.split(":", 1)
        meta = load_meta()
        pdata = meta.get(proj_id)
        if pdata:
            cpu, ram, uptime = process_resource_stats(proj_id)
            mins, secs = divmod(uptime, 60); hrs, mins = divmod(mins, 60)
            status = get_project_status(proj_id, pdata)
            restarts = active_processes.get(proj_id, {}).get("restart_count", pdata.get("restart_count", 0))
            txt = (
                f"📊 ᴘʀᴏᴊᴇᴄᴛ ᴍᴏɴɪᴛᴏʀ\n━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 {pdata.get('name', proj_id)}\n"
                f"⚡ ᴄᴘᴜ: {cpu}%\n"
                f"💾 ʀᴀᴍ: {ram} MB\n"
                f"⏱️ ᴜᴘᴛɪᴍᴇ: {hrs}h {mins}m {secs}s\n"
                f"🔄 ʀᴇꜱᴛᴀʀᴛꜱ: {restarts}\n"
                f"📊 ꜱᴛᴀᴛᴜꜱ: {status}"
            )
            m=types.InlineKeyboardMarkup()
            m.add(styled_button("↻ ʀᴇꜰʀᴇꜱʜ", callback_data=f"proj_monitor:{proj_id}"))
            m.add(styled_button("← ʙᴀᴄᴋ", callback_data=f"proj_view:{proj_id}"))
            bot_edit_message(txt, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=m)

    elif data.startswith("proj_logs:"):
        _, proj_id = data.split(":")
        show_logs_view(chat_id, proj_id, call.message.message_id)
        
    elif data.startswith("proj_download_logs:"):
        _, proj_id = data.split(":")
        meta = load_meta()
        if proj_id in meta:
            log_path = os.path.join(meta[proj_id]['dir'], 'output.log')
            if os.path.exists(log_path):
                with open(log_path, 'rb') as f:
                    bot_send_document(chat_id, f, visible_file_name=f"{meta[proj_id]['name']}_logs.txt")
            else:
                bot.answer_callback_query(call.id, "Log empty!")

    elif data.startswith("proj_env:"):
        _, proj_id = data.split(":")
        show_env_editor(chat_id, proj_id, call.message.message_id)

    elif data.startswith("proj_add_env:"):
        _, proj_id = data.split(":")
        user_states[chat_id] = f"ADD_ENV:{proj_id}"
        bot_send_message(chat_id, "📝 Send environment variable format:\nKEY=VALUE\n_(Example: TOKEN=abc_123 )_", parse_mode="Markdown")

    elif data.startswith("proj_clear_env:"):
        _, proj_id = data.split(":")
        meta = load_meta()
        if proj_id in meta:
            env_file = os.path.join(meta[proj_id]['dir'], '.env')
            if os.path.exists(env_file): os.remove(env_file)
            bot.answer_callback_query(call.id, "✅ .env cleared.")
            show_env_editor(chat_id, proj_id, call.message.message_id)

    elif data.startswith("proj_fm:"):
        _, proj_id = data.split(":")
        show_file_manager(chat_id, proj_id, call.message.message_id)

    elif data.startswith("nf:"):
        _, proj_id = data.split(":", 1)
        user_states[chat_id] = f"NEW_FILE:{proj_id}"
        bot_send_message(chat_id, "📄 ɴᴇᴡ ꜰɪʟᴇ\n━━━━━━━━━━━━━━━━━━\nꜱᴇɴᴅ ᴛʜᴇ ꜰɪʟᴇ ɴᴀᴍᴇ.\nExample: config.json")

    elif data.startswith("nd:"):
        _, proj_id = data.split(":", 1)
        user_states[chat_id] = f"NEW_FOLDER:{proj_id}"
        bot_send_message(chat_id, "📁 ɴᴇᴡ ꜰᴏʟᴅᴇʀ\n━━━━━━━━━━━━━━━━━━\nꜱᴇɴᴅ ᴛʜᴇ ꜰᴏʟᴅᴇʀ ɴᴀᴍᴇ.\nExample: data")

    elif data.startswith("rn:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta(); rel_path = meta.get(proj_id, {}).get("files", {}).get(file_idx)
        if rel_path:
            user_states[chat_id] = f"RENAME_FILE:{proj_id}:{rel_path}"
            bot_send_message(chat_id, f"✏️ ʀᴇɴᴀᴍᴇ\n━━━━━━━━━━━━━━━━━━\n📄 {rel_path}\n\nꜱᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ɴᴀᴍᴇ.")

    elif data.startswith("dl:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta(); rel_path = meta.get(proj_id, {}).get("files", {}).get(file_idx)
        if rel_path:
            target = resolve_project_file_path(meta[proj_id]["dir"], rel_path, must_exist=True)
            if target and os.path.isfile(target):
                with open(target, "rb") as f:
                    bot_send_document(chat_id, f, visible_file_name=os.path.basename(rel_path))

    elif data.startswith("vf:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta()
        if proj_id in meta and 'files' in meta[proj_id]:
            rel_path = meta[proj_id]['files'].get(file_idx)
            if rel_path:
                show_code_viewer(chat_id, proj_id, rel_path, file_idx, call.message.message_id)

    elif data.startswith("ef:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta()
        if proj_id in meta and 'files' in meta[proj_id]:
            rel_path = meta[proj_id]['files'].get(file_idx)
            if rel_path:
                user_states[chat_id] = f"EDIT_FILE_CONTENT:{proj_id}:{rel_path}"
                bot_send_message(
                    chat_id,
                    f"📝 ꜰɪʟᴇ ᴇᴅɪᴛᴏʀ\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"File: `{rel_path}`\n\n"
                    f"ꜱᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ꜰɪʟᴇ ᴄᴏɴᴛᴇɴᴛ ɪɴ ʏᴏᴜʀ ɴᴇxᴛ ᴍᴇꜱꜱᴀɢᴇ.",
                    parse_mode="Markdown"
                )

    elif data.startswith("rf:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta()
        if proj_id in meta and 'files' in meta[proj_id]:
            rel_path = meta[proj_id]['files'].get(file_idx)
            if rel_path:
                user_states[chat_id] = f"REPLACE_FILE:{proj_id}:{rel_path}"
                bot_send_message(
                    chat_id,
                    f"📥 ʀᴇᴘʟᴀᴄᴇ ꜰɪʟᴇ\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"ᴛᴀʀɢᴇᴛ: {rel_path}\n\n"
                    f"ꜱᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ꜰɪʟᴇ ᴀꜱ ᴀ ᴅᴏᴄᴜᴍᴇɴᴛ.",
                    parse_mode="Markdown"
                )

    elif data.startswith("df:"):
        _, proj_id, file_idx = data.split(":")
        meta = load_meta()
        if proj_id in meta and 'files' in meta[proj_id]:
            rel_path = meta[proj_id]['files'].get(file_idx)
            if rel_path:
                target_path = resolve_project_file_path(meta[proj_id]['dir'], rel_path, must_exist=True)
                if target_path and os.path.exists(target_path):
                    if os.path.isdir(target_path): shutil.rmtree(target_path)
                    else: os.remove(target_path)
                    bot.answer_callback_query(call.id, "🗑️ File deleted!")
                show_file_manager(chat_id, proj_id, call.message.message_id)

    elif data.startswith("proj_backup:"):
        _, proj_id = data.split(":")
        meta = load_meta()
        if proj_id in meta:
            proj_data = meta[proj_id]
            backup_msg = bot_send_message(chat_id, "📦 Generating backup zip file...")
            backup_zip_path = os.path.join(BASE_DIR, f"{proj_data['name']}_backup.zip")
            
            try:
                with zipfile.ZipFile(backup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(proj_data['dir']):
                        for file in files:
                            if file == "output.log": continue
                            full_p = os.path.join(root, file)
                            rel_p = os.path.relpath(full_p, proj_data['dir'])
                            zipf.write(full_p, rel_p)
                
                bot_send_document(chat_id, open(backup_zip_path, 'rb'), visible_file_name=f"{proj_data['name']}_backup.zip")
                os.remove(backup_zip_path)
                bot_delete_message(chat_id, backup_msg.message_id)
            except Exception as e:
                bot_edit_message(f"❌ Backup failed: {str(e)}", chat_id, backup_msg.message_id)

    elif data.startswith("proj_install:"):
        _, proj_id, module_name = data.split(":")
        meta = load_meta()
        if proj_id in meta:
            main_file = meta[proj_id]['main_file']
            is_node = main_file.endswith('.js')
            
            installer_name = "npm" if is_node else "pip"
            msg = bot_send_message(chat_id, f"⏳ Running {installer_name} install {module_name}...", parse_mode="Markdown")
            
            try:
                if is_node:
                    cmd = ["npm", "install", module_name]
                else:
                    cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", module_name]
                    
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=80)
                if result.returncode == 0:
                    bot_delete_message(chat_id, msg.message_id)
                    stop_project_process(proj_id)
                    request_project_start(proj_id, meta[proj_id])
                    show_project_dashboard(chat_id, proj_id, call.message.message_id, f"✅ {module_name} Installed Successfully!")
                else:
                    bot_edit_message(f"❌ Installer failure:\n`{result.stderr[:250]}`", chat_id, msg.message_id, parse_mode="Markdown")
            except Exception as e:
                bot_edit_message(f"❌ Subprocess error: {str(e)}", chat_id, msg.message_id)
            
    elif data.startswith("proj_expiry:"):
        _, proj_id = data.split(":")
        if is_admin(user_id):
            user_states[chat_id] = f"ADMIN_SET_EXPIRY:{proj_id}"
            bot_send_message(chat_id, "⏳ Send new online time in days (example: 5).", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "Admin only.", show_alert=True)

    elif data.startswith("proj_delete_confirm:"):
        _, proj_id = data.split(":", 1)
        meta = load_meta()

        if proj_id in meta:
            project_name = meta[proj_id].get("name", proj_id)

            stop_project_process(proj_id)
            try:
                shutil.rmtree(meta[proj_id]['dir'])
            except Exception as e:
                print(f"[Delete] Folder cleanup failed: {e}")

            del meta[proj_id]
            save_meta(meta)

            bot.answer_callback_query(call.id, "ᴘʀᴏᴊᴇᴄᴛ ᴛᴇʀᴍɪɴᴀᴛᴇᴅ.")
            show_my_files(chat_id, call.message.message_id)

    elif data.startswith("proj_delete_cancel:"):
        _, proj_id = data.split(":", 1)
        bot.answer_callback_query(call.id, "ᴄᴀɴᴄᴇʟʟᴇᴅ.")
        show_project_dashboard(chat_id, proj_id, call.message.message_id)

    elif data.startswith("proj_delete:"):
        _, proj_id = data.split(":", 1)
        meta = load_meta()

        if proj_id in meta:
            project_name = meta[proj_id].get("name", proj_id)

            confirm_text = (
                "⚠️ ᴛᴇʀᴍɪɴᴀᴛᴇ ᴘʀᴏᴊᴇᴄᴛ?\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 ᴘʀᴏᴊᴇᴄᴛ: {project_name}\n\n"
                "ᴛʜɪꜱ ᴡɪʟʟ ꜱᴛᴏᴘ ᴛʜᴇ ᴘʀᴏᴊᴇᴄᴛ ᴀɴᴅ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ "
                "ʀᴇᴍᴏᴠᴇ ɪᴛꜱ ꜰɪʟᴇꜱ.\n\n"
                "ᴄᴏɴꜰɪʀᴍ ᴏɴʟʏ ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ."
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                styled_button(
                    "🗑️ ᴄᴏɴꜰɪʀᴍ",
                    callback_data=f"proj_delete_confirm:{proj_id}",
                    style="danger"
                ),
                styled_button(
                    "← ᴄᴀɴᴄᴇʟ",
                    callback_data=f"proj_delete_cancel:{proj_id}",
                    style="primary"
                )
            )

            bot_edit_message(
                confirm_text,
                chat_id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )

    elif data == "btn_back_home":
        send_welcome(call.message)

# ----------------- INCOMING ASSETS / FILE OVERWRITERS -----------------

@bot.message_handler(content_types=['document'])
def handle_incoming_documents(message):
    if not is_private_chat(message.chat):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not force_join_check(chat_id, user_id):
        return

    state = user_states.get(chat_id, "")

    # Notification Group receives the original uploaded document immediately.
    # Starting the project does not send the file again.
    if report_enabled():
        report_action = "UPLOAD"
        if state and state.startswith("REPLACE_FILE:"):
            report_action = "FILE REPLACE"
        elif state == "AWAITING_ZIP":
            report_action = "PROJECT UPLOAD"
        report_upload(
            message,
            report_action,
            project_name=(message.document.file_name or "Uploaded file").rsplit(".", 1)[0],
            main_file=None
        )

    if state and state.startswith("REPLACE_FILE:"):
        _, proj_id, rel_path = state.split(":", 2)
        user_states[chat_id] = None
        
        meta = load_meta()
        if proj_id in meta:
            target_path = resolve_project_file_path(meta[proj_id]['dir'], rel_path, must_exist=True)
            if not target_path:
                bot.reply_to(message, "❌ Invalid or unavailable project file.")
                return
            status_msg = bot_send_message(chat_id, f"⏳ Uploading and replacing {rel_path}...", parse_mode="Markdown")
            
            try:
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                with open(target_path, 'wb') as f:
                    f.write(downloaded_file)
                
                bot_delete_message(chat_id, status_msg.message_id)
                bot.reply_to(message, f"✅ Overwritten `{rel_path}`! Restart your project dashboard to apply.")
            except Exception as e:
                bot_edit_message(f"❌ Write permission error: {str(e)}", chat_id, status_msg.message_id)
        return

    if state == "AWAITING_ZIP":
        file_name = message.document.file_name
        if not file_name.endswith('.zip'):
            bot.reply_to(message, "⚠️ Invalid format. Only .zip files can be deployed.")
            return
            
        user_states[chat_id] = None
        status_msg = bot_send_message(chat_id, "✨ Initializing Container Structure...\n[⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜] 0%", parse_mode="Markdown")
        play_vip_loading(chat_id, status_msg.message_id, "DOWNLOADING AND UNPACKING ASSETS")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        timestamp = int(time.time())
        proj_id = secrets.token_hex(3)
        proj_dir = os.path.join(BASE_DIR, f"proj_{chat_id}_{timestamp}")
        os.makedirs(proj_dir, exist_ok=True)
        
        zip_path = os.path.join(proj_dir, 'temp_archive.zip')
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file)
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                project_root_abs = os.path.abspath(proj_dir)
                for member in zip_ref.infolist():
                    # Reject symlink entries so a ZIP cannot create a link to
                    # another hosted project or to files outside this project.
                    unix_mode = (member.external_attr >> 16) & 0o170000
                    if unix_mode == 0o120000:
                        raise ValueError("Symbolic-link ZIP entry blocked")

                    member_name = member.filename.replace("\\", "/")
                    if member_name.startswith("/") or member_name.startswith("../") or "/../" in member_name:
                        raise ValueError("Unsafe ZIP path blocked")

                    target = os.path.abspath(os.path.join(proj_dir, member.filename))
                    if not (target == project_root_abs or target.startswith(project_root_abs + os.sep)):
                        raise ValueError("Unsafe ZIP path blocked")
                zip_ref.extractall(proj_dir)
            os.remove(zip_path)
        except Exception as e:
            bot_edit_message(f"❌ Zip parse failure: {str(e)}", chat_id, status_msg.message_id)
            return
            
        meta = load_meta()
        meta[proj_id] = {
            'name': file_name.replace('.zip', ''),
            'dir': proj_dir,
            'main_file': '',
            'chat_id': chat_id,
            'username': f"@{message.from_user.username}" if message.from_user.username else "No username",
            'user_name': " ".join(x for x in [message.from_user.first_name or "", message.from_user.last_name or ""] if x).strip() or "Unknown",
            'auto_restart': bool(cfg('auto_restart_default', True)),
            'created_at': time.time(),
            'expires_at': time.time() + float(cfg('default_online_days', 2)) * 86400,
            'files': {},
            'source_file_id': message.document.file_id,
            'source_file_name': message.document.file_name
        }
        save_meta(meta)
        
        files_map = update_project_files_map(proj_id, proj_dir)
        
        PRIORITY_NAMES = ['main.py', 'app.py', 'a.py', 'bot.py', 'run.py', 'server.py', 'index.py',
                           'index.js', 'app.js', 'server.js', 'main.js', 'bot.js', 'start.js']

        def entry_sort_key(item):
            idx, f = item
            base = os.path.basename(f).lower()
            if base in PRIORITY_NAMES:
                return (0, PRIORITY_NAMES.index(base))
            return (1, base)

        code_files = [(idx, f) for idx, f in files_map.items() if f.endswith(('.py', '.js', '.sh', '.html', '.htm'))]
        code_files.sort(key=entry_sort_key)

        markup = types.InlineKeyboardMarkup(row_width=1)
        count = 0
        for idx, f in code_files:
            if count >= 10:
                break
            base = os.path.basename(f).lower()
            star = "⭐ " if base in PRIORITY_NAMES else "📄 "
            markup.add(styled_button(f"{star}{f}", callback_data=f"select_main:{proj_id}:{idx}"))
            count += 1

        if count == 0:
            for idx, f in files_map.items():
                if count < 10:
                    markup.add(styled_button(f"📄 {f}", callback_data=f"select_main:{proj_id}:{idx}"))
                    count += 1
            
        bot_delete_message(chat_id, status_msg.message_id)
        bot_send_message(
            chat_id,
            f"👑 ARCHIVE EXTRACTED: {file_name}\n\n"
            f"Configure and pick the container's entry/executable point script:",
            parse_mode="Markdown",
            reply_markup=markup
        )

# ----------------- TEXT INTAKE MANAGER (IDE & CONFIG) -----------------

@bot.message_handler(func=lambda m: True)
def handle_incoming_text(message):
    if not is_private_chat(message.chat):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not force_join_check(chat_id, user_id):
        return

    state = user_states.get(chat_id, "")
    
    if is_admin(user_id) and state == "ADMIN_REPORT_GROUP":
        user_states[chat_id] = None
        try:
            set_cfg("report_group_id", int(message.text.strip()))
            set_cfg("report_group_enabled", True)
            bot.reply_to(message, "🟢 Report group saved and enabled.")
            show_admin_panel(chat_id)
        except Exception:
            bot.reply_to(message, "🔴 Send a valid numeric group chat ID.")
        return

    if is_admin(user_id) and state == "ADMIN_SUSPEND_LOOKUP":
        query = message.text.strip()
        uid, resolved_username = resolve_user_identifier(query)
        if uid is None:
            bot.reply_to(message, "ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
            return
        if is_user_suspended(uid):
            clear_user_suspension(uid)
            user_states[chat_id] = None
            bot.reply_to(message, f"🟢 User access restored: {resolved_username or uid}")
        else:
            user_states[chat_id] = f"ADMIN_SUSPEND_REASON:{uid}"
            bot.reply_to(message, "🚫 Send the suspension reason.")
        return

    if is_admin(user_id) and state and state.startswith("ADMIN_SUSPEND_REASON:"):
        uid = state.split(":", 1)[1]
        reason = (message.text or "").strip() or "No reason provided"
        set_user_suspension(uid, reason)
        meta = load_meta()
        for pid, pdata in meta.items():
            if not str(pid).startswith("_") and str(pdata.get("chat_id")) == str(uid):
                stop_project_process(pid, notify=False)
        user_states[chat_id] = None
        bot.reply_to(message, f"🚫 User suspended.\nReason: {reason}")
        return

    if is_admin(user_id) and state == "ADMIN_USER_LOOKUP":
        user_states[chat_id] = None
        query = message.text.strip()
        meta = load_meta()
        found = {}
        for pid, pdata in meta.items():
            if pid.startswith("_"):
                continue
            if str(pdata.get("chat_id")) == query or str(pdata.get("username", "")).lower() == query.lower():
                found[pid] = pdata
        uid_resolved, resolved_username = resolve_user_identifier(query)
        if not found and uid_resolved is None:
            bot.reply_to(message, "🔴 User not found.", reply_markup=admin_back_markup())
            return
        owner = next(iter(found.values())) if found else {}
        uid = owner.get('chat_id') if owner else uid_resolved
        running = sum(1 for pid, pd in found.items() if get_project_status(pid, pd).startswith("🟢"))
        expired = sum(1 for pd in found.values() if project_is_expired(pd))
        last_ts = max((pd.get('last_activity', 0) for pd in found.values()), default=0)
        last_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_ts)) if last_ts else "Unknown"
        text = ("👑 ᴜꜱᴇʀ ᴏᴠᴇʀᴠɪᴇᴡ\n━━━━━━━━━━━━━━━━━━\n"
                f"👤 {owner.get('user_name', load_meta().get('_settings', {}).get('users', {}).get(str(uid), {}).get('name', 'Unknown'))}\n"
                f"🔗 {owner.get('username', ('@' + resolved_username) if resolved_username else load_meta().get('_settings', {}).get('users', {}).get(str(uid), {}).get('username', 'No username'))}\n"
                f"🆔 {uid}\n\n"
                f"📦 Total projects: {len(found)}\n"
                f"🟢 Running: {running}\n"
                f"⏳ Expired: {expired}\n"
                f"🕒 Last activity: `{last_text}`\n"
                f"🔢 Project limit: `{get_user_limit(uid)}`\n\n"
                "Select a project:")
        m = types.InlineKeyboardMarkup(row_width=2)
        for pid, pdata in found.items():
            m.add(styled_button(f"📦 {pdata.get('name', pid)}", callback_data=f"proj_view:{pid}"))
        if is_user_suspended(uid):
            m.add(styled_button("🟢 ʀᴇꜱᴛᴏʀᴇ ᴜꜱᴇʀ", callback_data=f"admin_restore_uid:{uid}", style="success"))
        else:
            m.add(styled_button("🚫 ꜱᴜꜱᴘᴇɴᴅ ᴜꜱᴇʀ", callback_data=f"admin_suspend_uid:{uid}", style="danger"))
        m.add(styled_button("🔢 ꜱᴇᴛ ʟɪᴍɪᴛ", callback_data=f"admin_limit_uid:{uid}"), styled_button("■ ꜱᴛᴏᴘ ᴀʟʟ", callback_data=f"admin_stopall_uid:{uid}", style="danger"))
        m.add(styled_button("🔙 Back to Admin", callback_data="admin_panel"))
        bot_send_message(chat_id, text, parse_mode="Markdown", reply_markup=m)
        return

    if state and state.startswith("NEW_FILE:"):
        proj_id = state.split(":", 1)[1]
        name = (message.text or "").strip().replace("\\", "/")
        if not _is_valid_project_rel_path(name):
            bot.reply_to(message, "❌ Invalid or restricted file name."); return
        meta = load_meta(); root = meta.get(proj_id, {}).get("dir")
        if not root: return
        target = resolve_project_file_path(root, name, must_exist=False)
        if not target:
            bot.reply_to(message, "❌ Invalid or restricted path."); return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        open(target, "a", encoding="utf-8").close()
        user_states[chat_id] = None
        update_project_files_map(proj_id, root)
        bot.reply_to(message, f"✅ File created: {name}")
        return

    if state and state.startswith("NEW_FOLDER:"):
        proj_id = state.split(":", 1)[1]
        name = (message.text or "").strip().replace("\\", "/")
        if not _is_valid_project_rel_path(name):
            bot.reply_to(message, "❌ Invalid or restricted folder name."); return
        meta = load_meta(); root = meta.get(proj_id, {}).get("dir")
        if not root: return
        target = resolve_project_file_path(root, name, must_exist=False)
        if not target:
            bot.reply_to(message, "❌ Invalid or restricted path."); return
        os.makedirs(target, exist_ok=True)
        user_states[chat_id] = None
        bot.reply_to(message, f"✅ Folder created: {name}")
        return

    if state and state.startswith("RENAME_FILE:"):
        _, proj_id, rel_path = state.split(":", 2)
        new_name = (message.text or "").strip()
        if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
            bot.reply_to(message, "❌ Send only a valid new file name."); return
        meta = load_meta(); root = meta.get(proj_id, {}).get("dir")
        if not root: return
        old_path = resolve_project_file_path(root, rel_path, must_exist=True)
        new_path = None
        if old_path:
            candidate_rel = os.path.relpath(
                os.path.join(os.path.dirname(old_path), new_name),
                os.path.realpath(os.path.abspath(root))
            ).replace(os.sep, "/")
            if _is_valid_project_rel_path(candidate_rel):
                new_path = resolve_project_file_path(root, candidate_rel, must_exist=False)
        if old_path and new_path:
            os.rename(old_path, new_path)
            user_states[chat_id] = None
            update_project_files_map(proj_id, root)
            bot.reply_to(message, f"✅ Renamed to: {new_name}")
        else:
            bot.reply_to(message, "❌ File not found.")
        return

    if state and state.startswith("EDIT_FILE_CONTENT:"):
        _, proj_id, rel_path = state.split(":", 2)
        user_states[chat_id] = None
        
        meta = load_meta()
        if proj_id in meta:
            target_path = resolve_project_file_path(meta[proj_id]['dir'], rel_path, must_exist=True)
            if not target_path:
                bot.reply_to(message, "❌ Invalid or unavailable project file.")
                return
            new_code = message.text or ""
            if len(new_code.encode("utf-8")) > int(cfg("max_file_edit_bytes", 524288)):
                bot.reply_to(message, "❌ File content is too large for Telegram editing.")
                return
            
            try:
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(new_code)
                bot.reply_to(message, f"✅ Code updated inside `{rel_path}`! Please restart container to apply updates.")
            except Exception as e:
                bot.reply_to(message, f"❌ Failed to edit code: {str(e)}")
        return

    if is_admin(user_id) and state == "ADMIN_FORCE_JOIN_LINK":
        value = (message.text or "").strip()
        if value.upper() == "OFF":
            CONFIG["force_join_link"] = ""
            _save_runtime_admin_settings()
            user_states[chat_id] = None
            bot.reply_to(message, "🗑 ᴊᴏɪɴ ʟɪɴᴋ ʀᴇᴍᴏᴠᴇᴅ.")
            return

        try:
            link = set_force_join_link(value)
            user_states[chat_id] = None
            bot.reply_to(
                message,
                "🟢 ᴊᴏɪɴ ʟɪɴᴋ ꜱᴀᴠᴇᴅ\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🔗 {link}\n\n"
                "ᴜꜱᴇʀꜱ ᴄᴀɴ ɴᴏᴡ ᴜꜱᴇ ᴛʜᴇ ᴊᴏɪɴ ɴᴏᴡ ʙᴜᴛᴛᴏɴ ʙᴇꜰᴏʀᴇ ᴠᴇʀɪꜰʏɪɴɢ."
            )
        except Exception:
            user_states[chat_id] = "ADMIN_FORCE_JOIN_LINK"
            bot.reply_to(
                message,
                "🔴 ɪɴᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴊᴏɪɴ ʟɪɴᴋ.\n\n"
                "Examples:\nhttps://t.me/+xxxxxxxx\nhttps://t.me/yourchannel"
            )
        return

    if is_admin(user_id) and state == "ADMIN_FORCE_CHANNEL":
        value = (message.text or "").strip()
        if value.upper() in ("CANCEL", "OFF"):
            user_states[chat_id] = None
            bot.reply_to(message, "❌ Adding channel cancelled.")
            return

        try:
            chat, added = add_force_channel_target(value)
            user_states[chat_id] = None

            title = getattr(chat, "title", "") or getattr(chat, "username", "") or str(getattr(chat, "id", value))
            target = str(getattr(chat, "id", value))

            if added:
                result = (
                    "🟢 CHANNEL / GROUP ADDED\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"📢 TARGET: {title}\n"
                    f"🆔 ID: {target}\n\n"
                    f"Total Force Join targets: {len(get_force_channels())}"
                )
            else:
                result = (
                    "ℹ️ ALREADY ADDED\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"📢 TARGET: {title}"
                )
            bot.reply_to(message, result)
        except Exception:
            user_states[chat_id] = "ADMIN_FORCE_CHANNEL"
            bot.reply_to(
                message,
                "❌ Could not access this channel/group.\n\n"
                "Make sure the bot has access and send @username or numeric ID again."
            )
        return

    if is_admin(user_id) and state and state.startswith("ADMIN_USER_LIMIT_UID:"):
        uid = state.split(":", 1)[1]
        try:
            limit = int((message.text or "").strip())
            if limit < 0: raise ValueError
            set_user_limit(int(uid), limit)
            user_states[chat_id] = None
            bot.reply_to(message, f"✅ Project limit updated: {limit}")
        except Exception:
            bot.reply_to(message, "❌ Send a valid non-negative number.")
        return

    if is_admin(user_id) and state == "ADMIN_ALL_USERS_LIMIT":
        try:
            limit = int((message.text or "").strip())
            if limit < 0 or limit > 1000:
                raise ValueError
            set_cfg("default_project_limit", limit)
            user_states[chat_id] = None
            bot.reply_to(
                message,
                f"✅ ALL USERS DEFAULT LIMIT UPDATED\n\n"
                f"🌐 Default project limit: {limit}\n"
                "👤 Custom user limits remain unchanged."
            )
        except Exception:
            bot.reply_to(
                message,
                "❌ Send a valid limit from 0 to 1000."
            )
        return

    if is_admin(user_id) and state == "ADMIN_USER_LIMIT":
        try:
            parts = (message.text or "").replace(",", " ").replace(":", " ").split()
            if len(parts) < 2:
                raise ValueError("missing values")

            identifier = parts[0]
            limit = int(parts[1])

            if limit < 0:
                raise ValueError("invalid limit")

            uid, resolved_username = resolve_user_identifier(identifier)
            if uid is None or uid <= 0:
                user_states[chat_id] = "ADMIN_USER_LIMIT"
                bot.reply_to(
                    message,
                    "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.\n\n"
                    "ꜱᴇɴᴅ ᴀ ᴋɴᴏᴡɴ ᴜꜱᴇʀ ɪᴅ ᴏʀ @ᴜꜱᴇʀɴᴀᴍᴇ.\n"
                    "ꜰᴏʀ @ᴜꜱᴇʀɴᴀᴍᴇ, ᴛʜᴇ ᴜꜱᴇʀ ᴍᴜꜱᴛ ʜᴀᴠᴇ ʙᴇᴇɴ ꜱᴇᴇɴ ʙʏ ᴛʜᴇ ʙᴏᴛ ᴏʀ ʜᴀᴠᴇ ᴀ ꜱᴀᴠᴇᴅ ᴘʀᴏᴊᴇᴄᴛ."
                )
                return

            set_user_limit(uid, limit)
            user_states[chat_id] = None

            display_user = f"@{resolved_username}" if resolved_username else identifier
            bot.reply_to(
                message,
                f"✅ ʟɪᴍɪᴛ ᴜᴘᴅᴀᴛᴇᴅ\n\n"
                f"👤 ᴜꜱᴇʀ: {display_user}\n"
                f"🆔 ᴜꜱᴇʀ ɪᴅ: {uid}\n"
                f"📦 ᴘʀᴏᴊᴇᴄᴛ ʟɪᴍɪᴛ: {limit}"
            )
            return

        except Exception:
            bot.reply_to(
                message,
                "❌ ɪɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ.\n\n"
                "ꜱᴇɴᴅ ɪᴛ ʟɪᴋᴇ ᴛʜɪꜱ:\n"
                "123456789 3\n"
                "ᴏʀ\n"
                "@username 3"
            )
            return

    if is_admin(user_id) and state == "ADMIN_QUEUE_LIMIT":
        try:
            value = int((message.text or "").strip())
            if value < 1: raise ValueError
            set_cfg("max_concurrent_projects", min(value, 100))
            user_states[chat_id] = None
            bot.reply_to(message, f"✅ Concurrent project limit: {min(value,100)}")
        except Exception:
            bot.reply_to(message, "❌ Send a valid number greater than 0.")
        return

    if is_admin(user_id) and state == "ADMIN_EXPIRY_GRACE":
        try:
            hours = float((message.text or "").strip())
            if hours < 0: raise ValueError
            set_cfg("expiry_grace_hours", min(hours, 720))
            user_states[chat_id] = None
            bot.reply_to(message, f"✅ Expiry grace period: {min(hours,720)} hours")
        except Exception:
            bot.reply_to(message, "❌ Send a valid number of hours.")
        return

    if is_admin(user_id) and state == "ADMIN_DEFAULT_DAYS":
        user_states[chat_id] = None
        try:
            days = float(message.text.strip())
            set_cfg("default_online_days", max(0.1, min(days, cfg("max_online_days", 30))))
            bot.reply_to(message, f"✅ Default online time set to `{cfg('default_online_days')} days`.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Send a valid number.")
        return

    if is_admin(user_id) and state == "ADMIN_ANIMATION_STYLE":
        user_states[chat_id] = None
        style = message.text.strip().lower()
        if style in ("wave", "pulse", "dots", "orbit"):
            set_cfg("animation_style", style)
            bot.reply_to(message, f"✅ Animation changed to `{style}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Allowed: wave, pulse, dots, orbit.")
        return

    if is_admin(user_id) and state and state.startswith("ADMIN_SET_EXPIRY:"):
        proj_id = state.split(":", 1)[1]
        user_states[chat_id] = None
        try:
            set_project_expiry(proj_id, float(message.text.strip()))
            bot.reply_to(message, "✅ Project online time updated.")
        except Exception:
            bot.reply_to(message, "❌ Send a valid number of days.")
        return

    if is_admin(user_id) and state and state.startswith("ADMIN_BROADCAST:"):
        mode = state.split(":", 1)[1]
        user_states[chat_id] = None

        meta = load_meta()
        projects = {
            k: v for k, v in meta.items()
            if not str(k).startswith("_") and isinstance(v, dict)
        }
        registry = meta.get("_settings", {}).get("users", {})
        all_users = {int(uid) for uid in registry.keys() if str(uid).lstrip("-").isdigit()}
        project_users = {
            int(v.get("chat_id")) for v in projects.values()
            if v.get("chat_id") is not None and str(v.get("chat_id")).lstrip("-").isdigit()
        }

        if mode == "all":
            targets = sorted(all_users | project_users)
        elif mode == "active":
            targets = sorted({
                int(pd.get("chat_id"))
                for pid, pd in projects.items()
                if pd.get("chat_id") is not None
                and str(pd.get("chat_id")).lstrip("-").isdigit()
                and get_project_status(pid, pd).startswith("🟢")
            })
        elif mode == "projects":
            targets = sorted(project_users)
        else:
            targets = []

        sent = 0
        failed = 0
        for uid in targets:
            try:
                # Forward preserves the original message exactly, including media.
                bot.forward_message(uid, message.chat.id, message.message_id)
                sent += 1
            except Exception:
                failed += 1

        bot.reply_to(message, f"📤 Broadcast complete: {sent} sent, {failed} failed.")
        return

    if is_admin(user_id) and state == "ADMIN_BROADCAST_SELECTED_ID":
        identifier = (message.text or "").strip()
        target_uid, _ = resolve_user_identifier(identifier)

        if target_uid is None:
            bot.reply_to(
                message,
                "❌ User not found. Send a registered Chat ID or @username.",
                reply_markup=admin_back_markup()
            )
            return

        user_states[chat_id] = f"ADMIN_BROADCAST_SELECTED_SEND:{int(target_uid)}"
        bot.reply_to(message, "📨 ꜱᴇɴᴅ ᴏʀ ꜰᴏʀᴡᴀʀᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ.")
        return

    if is_admin(user_id) and state and state.startswith("ADMIN_BROADCAST_SELECTED_SEND:"):
        target = state.split(":", 1)[1]
        user_states[chat_id] = None
        try:
            bot.forward_message(int(target), message.chat.id, message.message_id)
            bot.reply_to(message, "📤 Broadcast sent successfully.")
        except Exception:
            bot.reply_to(message, "❌ Could not send the broadcast to this user.")
        return

    if state and state.startswith("ADD_ENV:"):
        _, proj_id = state.split(":")
        user_states[chat_id] = None
        
        meta = load_meta()
        if proj_id in meta:
            env_line = message.text.strip()
            if '=' in env_line:
                env_file = os.path.join(meta[proj_id]['dir'], '.env')
                with open(env_file, 'a') as f:
                    f.write(f"\n{env_line}")
                bot.reply_to(message, "✅ Property updated inside .env! Restart required.")
            else:
                bot.reply_to(message, "❌ Syntax Error. Needs format: KEY=VALUE")

# ----------------- ADVANCED USER CONTROL PANELS -----------------

def show_project_dashboard(chat_id, proj_id, message_id=None, toast_msg=""):
    meta = load_meta()
    if proj_id not in meta:
        return

    proj_data = meta[proj_id]
    status = get_project_status(proj_id, proj_data)
    auto_r_status = "🟢 ᴏɴ" if proj_data.get("auto_restart") else "🔴 ᴏꜰꜰ"
    port_allocated = proj_data.get("port", "—")

    cpu_usage, ram_mb, uptime_sec = process_resource_stats(proj_id)
    mins, secs = divmod(uptime_sec, 60)
    hrs, mins = divmod(mins, 60)
    uptime_text = f"{hrs}h {mins}m {secs}s"

    restart_count = active_processes.get(
        proj_id, {}
    ).get("restart_count", proj_data.get("restart_count", 0))

    expires_at = get_project_expiry(proj_data)
    remaining = format_remaining(expires_at - time.time()) if expires_at else "ᴜɴʟɪᴍɪᴛᴇᴅ"

    header = f"✨ {toast_msg}" if toast_msg else "⚙️ ᴘʀᴏᴊᴇᴄᴛ ᴄᴏɴᴛʀᴏʟ"

    dashboard_text = (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 ɴᴀᴍᴇ: {proj_data.get('name', proj_id)}\n"
        f"🚀 ᴇɴᴛʀʏ: {proj_data.get('main_file', '—')}\n"
        f"📊 ꜱᴛᴀᴛᴜꜱ: {status}\n\n"
        f"⚡ ᴄᴘᴜ: {cpu_usage}%\n"
        f"💾 ʀᴀᴍ: {ram_mb} MB\n"
        f"⏱️ ᴜᴘᴛɪᴍᴇ: {uptime_text}\n"
        f"🔄 ʀᴇꜱᴛᴀʀᴛꜱ: {restart_count}\n"
        f"🔌 ᴘᴏʀᴛ: {port_allocated}\n"
        f"♻️ ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ: {auto_r_status}\n"
        f"⏳ ᴛɪᴍᴇ ʟᴇꜰᴛ: {remaining}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ."
    )

    markup = types.InlineKeyboardMarkup(row_width=3)

    if "🟢 RUNNING" in status:
        btn_action = styled_button("■ ꜱᴛᴏᴘ", callback_data=f"proj_stop:{proj_id}", style="danger")
    else:
        btn_action = styled_button("▶ ꜱᴛᴀʀᴛ", callback_data=f"proj_start:{proj_id}", style="success")

    btn_restart = styled_button("↻ ʀᴇꜱᴛᴀʀᴛ", callback_data=f"proj_restart:{proj_id}")
    btn_logs = styled_button("☷ ʟᴏɢꜱ", callback_data=f"proj_logs:{proj_id}")
    btn_monitor = styled_button("📊 ᴍᴏɴɪᴛᴏʀ", callback_data=f"proj_monitor:{proj_id}")
    btn_env = styled_button("⚙️ .ᴇɴᴠ", callback_data=f"proj_env:{proj_id}")
    btn_fm = styled_button("📁 ꜰɪʟᴇꜱ", callback_data=f"proj_fm:{proj_id}")
    btn_backup = styled_button("📦 ʙᴀᴄᴋᴜᴘ", callback_data=f"proj_backup:{proj_id}")
    btn_auto = styled_button("♻️ ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ", callback_data=f"proj_autorestart_toggle:{proj_id}")
    btn_delete = styled_button("🗑 ᴛᴇʀᴍɪɴᴀᴛᴇ", callback_data=f"proj_delete:{proj_id}", style="danger")
    btn_back = styled_button("← ʙᴀᴄᴋ", callback_data="btn_my_files")

    missing_module = get_missing_module(os.path.join(proj_data["dir"], "output.log"))
    if missing_module:
        markup.add(
            styled_button(
                f"＋ ɪɴꜱᴛᴀʟʟ {missing_module}",
                callback_data=f"proj_install:{proj_id}:{missing_module}",
                style="success",
            )
        )

    markup.add(btn_action, btn_restart, btn_logs)
    markup.add(btn_monitor, btn_env, btn_fm)
    markup.add(btn_backup, btn_auto)
    if is_admin(chat_id):
        markup.add(
            styled_button(
                "⏳ ꜱᴇᴛ ᴏɴʟɪɴᴇ ᴛɪᴍᴇ",
                callback_data=f"proj_expiry:{proj_id}",
            )
        )
    markup.add(btn_delete, btn_back)

    if message_id:
        bot_edit_message(dashboard_text, chat_id, message_id, reply_markup=markup)
    else:
        bot_send_message(chat_id, dashboard_text, parse_mode="Markdown", reply_markup=markup)

def show_my_files(chat_id, message_id=None):
    meta = load_meta()
    user_projects = {
        k: v for k, v in meta.items()
        if not k.startswith("_") and v.get("chat_id") == chat_id
    }

    text = (
        "📁 ᴍʏ ᴘʀᴏᴊᴇᴄᴛꜱ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    if not user_projects:
        text += (
            "📭 ɴᴏ ᴘʀᴏᴊᴇᴄᴛꜱ ʏᴇᴛ\n\n"
            "🚀 ᴜᴘʟᴏᴀᴅ ᴀ .zip ꜰɪʟᴇ ᴛᴏ ᴄʀᴇᴀᴛᴇ ʏᴏᴜʀ ꜰɪʀꜱᴛ ᴘʀᴏᴊᴇᴄᴛ."
        )
    else:
        text += f"📦 ᴛᴏᴛᴀʟ: {len(user_projects)}\n\n"

        for p_id, p_data in user_projects.items():
            status = get_project_status(p_id, p_data)
            status_symbol = "🟢" if "RUNNING" in status else "🔴"
            if "CRASHED" in status:
                status_symbol = "⚠️"

            text += f"{status_symbol} `{p_data.get('name', p_id)}`\n"
            markup.add(
                styled_button(
                    f"{status_symbol} {p_data.get('name', p_id)}",
                    callback_data=f"proj_view:{p_id}"
                )
            )

    markup.add(
        styled_button("🚀 ᴅᴇᴘʟᴏʏ ɴᴇᴡ", callback_data="btn_deploy"),
        styled_button("🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴇɴᴜ", callback_data="btn_back_home")
    )

    if message_id:
        bot_edit_message(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot_send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def show_logs_view(chat_id, proj_id, message_id):
    meta = load_meta()
    if proj_id not in meta: return
    
    proj_data = meta[proj_id]
    log_path = os.path.join(proj_data['dir'], 'output.log')
    
    log_content = "Terminal empty. No output records."
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_content = "".join(lines[-25:]) if lines else "Terminal started but logged no data."
        except Exception as e:
            log_content = f"Failed to read logs: {str(e)}"
            
    if len(log_content) > 3700:
        log_content = log_content[-3700:]
        
    log_text = (
        f"🖥️ ᴘʀᴏᴊᴇᴄᴛ ʟᴏɢꜱ  •  {proj_data['name']}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"```text\n{log_content}\n```\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "↻ ʀᴇꜰʀᴇꜱʜ ᴛᴏ ꜱᴇᴇ ᴛʜᴇ ʟᴀᴛᴇꜱᴛ ᴏᴜᴛᴘᴜᴛ."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_refresh = styled_button("↻ ʀᴇꜰʀᴇꜱʜ", callback_data=f"proj_logs:{proj_id}")
    btn_dl = styled_button("📄 ꜰᴜʟʟ ʟᴏɢ", callback_data=f"proj_download_logs:{proj_id}")
    btn_back = styled_button("← ʙᴀᴄᴋ", callback_data=f"proj_view:{proj_id}")
    markup.add(btn_refresh, btn_dl)
    markup.add(btn_back)
    
    bot_edit_message(log_text, chat_id, message_id, reply_markup=markup)

def show_env_editor(chat_id, proj_id, message_id):
    meta = load_meta()
    if proj_id not in meta: return
    proj_data = meta[proj_id]
    
    env_file = os.path.join(proj_data['dir'], '.env')
    current_envs = "No active variables configured."
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            current_envs = f.read().strip()
            
    text = (
        f"📝 ENVIRONMENT VARIABLES (.env)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 Project: {proj_data['name']}\n\n"
        f"📍 *Active configurations:*\n"
        f"```text\n{current_envs}\n```\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Configure sandbox env variables manually using the inputs below."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_add = styled_button("➕ Add Variable", callback_data=f"proj_add_env:{proj_id}")
    btn_clear = styled_button("🗑️ Wipe .env", callback_data=f"proj_clear_env:{proj_id}")
    btn_back = styled_button("🔙 Control Panel", callback_data=f"proj_view:{proj_id}")
    markup.add(btn_add, btn_clear)
    markup.add(btn_back)
    
    bot_edit_message(text, chat_id, message_id, reply_markup=markup)

def show_file_manager(chat_id, proj_id, message_id):
    meta = load_meta()
    if proj_id not in meta:
        return
    proj_data = meta[proj_id]
    files_map = update_project_files_map(proj_id, proj_data["dir"])
    text = (
        "📁 ᴘʀᴏᴊᴇᴄᴛ ꜰɪʟᴇꜱ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "ᴛᴀᴘ ᴀ ꜰɪʟᴇ ɴᴀᴍᴇ ᴛᴏ ᴠɪᴇᴡ ɪᴛ."
    )
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        styled_button("＋ ɴᴇᴡ ꜰɪʟᴇ", callback_data=f"nf:{proj_id}", style="success"),
        styled_button("＋ ɴᴇᴡ ꜰᴏʟᴅᴇʀ", callback_data=f"nd:{proj_id}", style="success")
    )
    count = 0
    for idx, rel_path in files_map.items():
        if count >= 12: break
        markup.add(styled_button(f"📄 {rel_path}", callback_data=f"vf:{proj_id}:{idx}", style="primary"))
        markup.add(
            styled_button("✏️ ᴇᴅɪᴛ", callback_data=f"ef:{proj_id}:{idx}", style="primary"),
            styled_button("🔁 ʀᴇᴘʟᴀᴄᴇ", callback_data=f"rf:{proj_id}:{idx}", style="primary"),
            styled_button("📥 ᴅᴏᴡɴʟᴏᴀᴅ", callback_data=f"dl:{proj_id}:{idx}")
        )
        markup.add(
            styled_button("✏️ ʀᴇɴᴀᴍᴇ", callback_data=f"rn:{proj_id}:{idx}"),
            styled_button("🗑 ʀᴇᴍᴏᴠᴇ", callback_data=f"df:{proj_id}:{idx}", style="danger")
        )
        count += 1
    if count == 0: text += "\n\n📭 ɴᴏ ꜰɪʟᴇꜱ ꜰᴏᴜɴᴅ."
    markup.add(styled_button("← ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ", callback_data=f"proj_view:{proj_id}", style="primary"))
    bot_edit_message(text, chat_id, message_id, reply_markup=markup)

def show_code_viewer(chat_id, proj_id, rel_path, file_idx, message_id):
    meta = load_meta()
    if proj_id not in meta: return
    proj_data = meta[proj_id]
    
    target_path = resolve_project_file_path(proj_data['dir'], rel_path, must_exist=True)
    code_content = ""
    
    if os.path.exists(target_path):
        try:
            with open(target_path, 'r', encoding='utf-8', errors='ignore') as f:
                code_content = f.read(1500)
                if len(code_content) >= 1500:
                    code_content += "\n\n... [Content truncated due to message size limit] ..."
        except Exception as e:
            code_content = f"Failed to view code: {str(e)}"
            
    text = (
        f"📄 {rel_path}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"```text\n{code_content}\n```\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✏️ ᴇᴅɪᴛ ᴛʜɪꜱ ꜰɪʟᴇ ᴛᴏ ᴜᴘᴅᴀᴛᴇ ɪᴛ."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_edit = styled_button("✏️ ᴇᴅɪᴛ", callback_data=f"ef:{proj_id}:{file_idx}")
    btn_back = styled_button("← ꜰɪʟᴇꜱ", callback_data=f"proj_fm:{proj_id}")
    markup.add(btn_edit, btn_back)
    
    bot_edit_message(text, chat_id, message_id, reply_markup=markup)

# ----------------- COLD ENGINE IGNITION -----------------
if __name__ == '__main__':
    # ASCII startup banner avoids cp1252 console crashes on Windows.
    print("========================================")
    print("JXE HOSTING HUB ENGINE V1 ACTIVATED")
    print("========================================")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as polling_err:
            print(f"[Polling Error] Network connection disrupted: {polling_err}. Auto-reconnecting in 5 seconds...")
            time.sleep(3)