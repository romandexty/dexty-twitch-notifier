"""Local connection settings and explicit legacy-data import. No network calls."""
import ast
import json
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QWidget, QMessageBox)

KEYS = ('twitch_client_id', 'twitch_client_secret', 'telegram_bot_token', 'telegram_chat_id')
LEGACY_KEYS = dict(zip(('TWITCH_APP_ID','TWITCH_APP_SECRET','TG_BOT_TOKEN','TG_CHAT_ID'), KEYS))

def wait_for_parent(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 30000) != 0:
                raise RuntimeError('Предыдущий экземпляр программы ещё завершается.')
        finally:
            kernel.CloseHandle(handle)

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def load_connections(folder):
    stored = read_json(Path(folder)/'connections.json')
    return {key: str(stored.get(key, '')).strip() for key in KEYS}

def save_connections(folder, values, token_update=None):
    data = {key: values.get(key, '').strip() for key in KEYS}
    if token_update is not None:
        data['_token_update'] = token_update
    atomic_json(Path(folder)/'connections.json', data)

def apply_pending_token(folder):
    path = Path(folder)/'connections.json'
    data = read_json(path)
    if '_token_update' not in data:
        return
    update = data['_token_update']
    if update.get('reset'):
        (Path(folder)/'token.json').unlink(missing_ok=True)
    else:
        atomic_json(Path(folder)/'token.json', update)
    data.pop('_token_update')
    atomic_json(path, data)

def import_legacy(source, target):
    """Read data, never execute the old Python script; never overwrite new settings."""
    import shutil
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        return
    target.mkdir(parents=True, exist_ok=True)
    for name in ('config.json', 'token.json', 'connections.json'):
        old, new = source/name, target/name
        if old.is_file() and not new.exists():
            value = json.loads(old.read_text(encoding='utf-8-sig'))
            if not isinstance(value, dict):
                raise ValueError('Некорректный файл ' + name)
            atomic_json(new, value)
    icon = source/'icon_DextyTwitchNotif.png'
    if icon.is_file() and not (target/icon.name).exists():
        shutil.copyfile(icon, target/icon.name)
    connections_file = target/'connections.json'
    if not connections_file.exists():
        script = source/'twitch_notifier_gui.pyw'
        if script.is_file():
            values = {}
            for node in ast.parse(script.read_text(encoding='utf-8-sig')).body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    for assignment in node.targets:
                        if isinstance(assignment, ast.Name) and assignment.id in LEGACY_KEYS:
                            if isinstance(node.value.value, str):
                                values[LEGACY_KEYS[assignment.id]] = node.value.value
            if values:
                save_connections(target, values)

