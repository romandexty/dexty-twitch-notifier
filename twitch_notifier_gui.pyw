import asyncio
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone

import requests
from PySide6.QtCore import QEasingCurve, QObject, QRect, QEvent, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from updates_ui import UpdatesDialog, APP_VERSION
from public_twitch import PublicTwitch, PUBLIC_CLIENT_ID, SignInRequired
from setup_ui import SetupDialog as ConnectionsDialog
from i18n import tr, FOLDER

from connections_ui import (load_connections, save_connections,
                            apply_pending_token, import_legacy, wait_for_parent)

DEFAULT_STREAMERS = []


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
# Installed binaries keep mutable files outside their installation directory.
DATA_DIR = str(FOLDER)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
ERROR_LOG = os.path.join(DATA_DIR, "error.log")
CUSTOM_ICON = os.path.join(DATA_DIR, "icon_DextyTwitchNotif.png")
if not os.path.isfile(CUSTOM_ICON):
    CUSTOM_ICON = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), "icon_DextyTwitchNotif.png")


DEFAULT_CONFIG = {
    "streamers": DEFAULT_STREAMERS,
    "telegram_notifications": False,
    "poll_interval": 15,
    "start_with_windows": False,
    "minimize_to_tray": True,
    "confirm_channel_removal": True,
}


class ConfigManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.data = {}
        self.load()

    def load(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with self.lock:
            data = dict(DEFAULT_CONFIG)
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data.update(loaded)
                except Exception:
                    pass

            # Clean up the streamer list while preserving order.
            cleaned = []
            seen = set()
            for name in data.get("streamers", DEFAULT_STREAMERS):
                name = str(name).strip()
                if name and name.lower() not in seen:
                    cleaned.append(name)
                    seen.add(name.lower())
            data["streamers"] = cleaned
            self.data = data
            self.save()

    def save(self):
        with self.lock:
            tmp = CONFIG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_FILE)

    def get(self, key, default=None):
        with self.lock:
            value = self.data.get(key, default)
            if isinstance(value, list):
                return list(value)
            if isinstance(value, dict):
                return dict(value)
            return value

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            self.save()

    def streamers(self):
        return self.get("streamers", [])

    def add_streamer(self, login):
        login = login.strip().lstrip("@").strip()
        import re
        login = re.sub(r"^https?://(?:www\.)?twitch\.tv/", "", login, flags=re.I).split("?")[0].rstrip("/")
        if not login:
            return False, tr('Введите Twitch-логин.')
        if not re.fullmatch(r"[A-Za-z0-9_]{1,25}", login):
            return False, tr('В Twitch-логине не должно быть пробелов.')
        current = self.streamers()
        if login.lower() in {x.lower() for x in current}:
            return False, tr('Этот стример уже есть в списке.')
        current.append(login)
        self.set("streamers", current)
        return True, ""

    def remove_streamer(self, login):
        current = self.streamers()
        new_list = [x for x in current if x.lower() != login.lower()]
        if len(new_list) == len(current):
            return False
        self.set("streamers", new_list)
        return True


class AppSignals(QObject):
    snapshot = Signal(dict)
    twitch_status = Signal(str)
    telegram_status = Signal(str)
    last_check = Signal(str)
    log_message = Signal(str)


class TwitchMonitor:
    def __init__(self, config: ConfigManager, signals: AppSignals):
        self.config = config
        self.signals = signals
        self.connections = load_connections(DATA_DIR)
        self.connections["twitch_client_id"] = PUBLIC_CLIENT_ID
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.paused = False
        self.pause_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.states = {}
        self.display_names = {}
        self.details = {}
        self.tg_notified = {}
        self.is_first_check = True
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.refresh_event.set()

    def refresh_now(self):
        self.refresh_event.set()

    def set_paused(self, paused: bool):
        with self.pause_lock:
            self.paused = paused
        if not paused:
            self.refresh_now()

    def is_paused(self):
        with self.pause_lock:
            return self.paused

    def _log(self, message):
        # Do not write connection secrets into diagnostic logs.
        for key in ("twitch_client_secret", "telegram_bot_token"):
            value = self.connections.get(key)
            if value:
                message = str(message).replace(value, "[hidden]")
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except Exception:
            pass
        self.signals.log_message.emit(message)

    def _sync_state_keys(self, streamers):
        active = {s.lower() for s in streamers}
        with self.state_lock:
            for login in active:
                self.states.setdefault(login, False)
                self.tg_notified.setdefault(login, False)
                self.details.setdefault(login, {})
            for login in list(self.states.keys()):
                if login not in active:
                    self.states.pop(login, None)
                    self.tg_notified.pop(login, None)
                    self.details.pop(login, None)
                    self.display_names.pop(login, None)

    def _build_snapshot(self):
        streamers = self.config.streamers()
        self._sync_state_keys(streamers)
        rows = []
        with self.state_lock:
            for configured_name in streamers:
                login = configured_name.lower()
                info = dict(self.details.get(login, {}))
                rows.append(
                    {
                        "login": login,
                        "configured_name": configured_name,
                        "display_name": self.display_names.get(login, configured_name),
                        "online": bool(self.states.get(login, False)),
                        "title": info.get("title", ""),
                        "game": info.get("game", ""),
                        "viewer_count": info.get("viewer_count"),
                        "started_at": info.get("started_at", ""),
                    }
                )
        return {"streamers": rows, "paused": self.is_paused()}

    def _emit_snapshot(self):
        self.signals.snapshot.emit(self._build_snapshot())

    def _send_tg_message(self, text, login=None):
        if not self.config.get("telegram_notifications", True):
            return
        if not self.connections.get("telegram_bot_token") or not self.connections.get("telegram_chat_id"):
            self.signals.telegram_status.emit("not_configured")
            return

        def _send():
            url = f"https://api.telegram.org/bot{self.connections['telegram_bot_token']}/sendMessage"
            success = False
            for _ in range(12):
                if self.stop_event.is_set():
                    return
                try:
                    resp = requests.post(
                        url,
                        data={"chat_id": self.connections["telegram_chat_id"], "text": text},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        success = True
                        break
                except Exception:
                    pass
                self.stop_event.wait(10)

            self.signals.telegram_status.emit("connected" if success else "error")
            if login:
                with self.state_lock:
                    self.tg_notified[login] = bool(success)

        threading.Thread(target=_send, daemon=True).start()

    async def _fetch_streams(self, twitch, logins, timeout=10.0):
        async def _fetch():
            result = []
            if not logins:
                return result
            async for stream in twitch.get_streams(user_login=logins):
                result.append(stream)
            return result

        return await asyncio.wait_for(_fetch(), timeout=timeout)

    async def _fetch_users(self, twitch, logins, timeout=10.0):
        async def _fetch():
            result = []
            if not logins:
                return result
            async for user in twitch.get_users(logins=logins):
                result.append(user)
            return result

        return await asyncio.wait_for(_fetch(), timeout=timeout)

    async def _authenticate(self, twitch):
        await twitch.validate()

    def _started_at_to_iso(self, value):
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass
        return str(value)

    async def _run_session(self):
        twitch = None
        try:
            self.signals.twitch_status.emit("connecting")
            twitch = PublicTwitch(PUBLIC_CLIENT_ID, TOKEN_FILE)
            await self._authenticate(twitch)
            self.signals.twitch_status.emit("connected")

            if self.is_first_check:
                self._send_tg_message(tr('✅ Twitch Notifier запущен!'))

            user_refresh_counter = 0

            while not self.stop_event.is_set():
                if self.is_paused():
                    self._emit_snapshot()
                    self.refresh_event.wait(1.0)
                    self.refresh_event.clear()
                    continue

                streamers = self.config.streamers()
                self._sync_state_keys(streamers)

                try:
                    # Refresh display names periodically and immediately after list changes.
                    if user_refresh_counter <= 0:
                        try:
                            users = await self._fetch_users(twitch, streamers)
                            found = set()
                            with self.state_lock:
                                for user in users:
                                    login = user.login.lower()
                                    found.add(login)
                                    self.display_names[login] = user.display_name
                            # Do not remove invalid names automatically; the UI keeps the user's entry.
                        except Exception as exc:
                            self._log(f"User lookup warning: {exc}")
                        user_refresh_counter = 20
                    else:
                        user_refresh_counter -= 1

                    streams = await self._fetch_streams(twitch, streamers)
                    current_online = set()

                    for stream in streams:
                        login = stream.user_login.lower()
                        current_online.add(login)
                        with self.state_lock:
                            was_online = bool(self.states.get(login, False))
                            self.states[login] = True
                            self.display_names[login] = stream.user_name
                            self.details[login] = {
                                "title": getattr(stream, "title", "") or "",
                                "game": getattr(stream, "game_name", "") or "",
                                "viewer_count": getattr(stream, "viewer_count", None),
                                "started_at": self._started_at_to_iso(
                                    getattr(stream, "started_at", None)
                                ),
                            }
                            if not was_online:
                                self.tg_notified[login] = False

                            should_notify = (self.tg_notified.get(login) is False
                                and self.config.get("telegram_notifications", False)
                                and bool(self.connections.get("telegram_bot_token"))
                                and bool(self.connections.get("telegram_chat_id")))
                            if should_notify:
                                self.tg_notified[login] = "PENDING"

                        if should_notify:
                            if self.is_first_check:
                                self._send_tg_message(
                                    tr("🟢 [Уже в эфире] {name} сейчас стримит!\n").format(name=stream.user_name) + f"https://twitch.tv/{login}",
                                    login,
                                )
                            else:
                                self._send_tg_message(
                                    tr("🔥 {name} запустил стрим!\n").format(name=stream.user_name) + f"https://twitch.tv/{login}",
                                    login,
                                )

                    with self.state_lock:
                        for login in list(self.states.keys()):
                            if self.states.get(login) and login not in current_online:
                                self.states[login] = False
                                self.tg_notified[login] = False
                                self.details[login] = {}

                    self.is_first_check = False
                    self.signals.twitch_status.emit("connected")
                    self.signals.last_check.emit(datetime.now().strftime("%H:%M:%S"))
                    self._emit_snapshot()

                except Exception as exc:
                    self.signals.twitch_status.emit("error")
                    self._log(f"Polling error: {exc}")
                    raise

                interval = max(5, int(self.config.get("poll_interval", 15) or 15))
                # Wait in a thread-friendly way; refresh_now wakes the loop early.
                self.refresh_event.wait(interval)
                self.refresh_event.clear()

        finally:
            if twitch:
                try:
                    await asyncio.wait_for(twitch.close(), timeout=2.0)
                except Exception:
                    pass

    def _thread_main(self):
        telegram_state = ("disabled" if not self.config.get("telegram_notifications", True)
                          else "ready" if self.connections.get("telegram_bot_token")
                          and self.connections.get("telegram_chat_id") else "not_configured")
        self.signals.telegram_status.emit(telegram_state)
        if not os.path.exists(TOKEN_FILE):
            self.signals.twitch_status.emit("not_configured")
            self._emit_snapshot()
            return
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass

        while not self.stop_event.is_set():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_session())
            except SignInRequired:
                self.signals.twitch_status.emit("not_configured")
                return
            except Exception as exc:
                self._log(f"Core restart: {exc}")
                self.signals.twitch_status.emit("error")
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

            if not self.stop_event.is_set():
                self.stop_event.wait(5)


def create_default_icon():
    if os.path.exists(CUSTOM_ICON):
        return QIcon(CUSTOM_ICON)

    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#9146FF"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(30)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "T")
    painter.end()
    return QIcon(pix)


def format_duration(started_at):
    if not started_at:
        return ""
    try:
        value = started_at.replace("Z", "+00:00")
        start = datetime.fromisoformat(value)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start.astimezone(timezone.utc)
        minutes = max(0, int(delta.total_seconds() // 60))
        hours, mins = divmod(minutes, 60)
        if hours:
            return tr("{hours}ч {mins:02d}м").format(hours=hours, mins=mins)
        return tr("{mins}м").format(mins=mins)
    except Exception:
        return ""


def set_start_with_windows(enabled: bool):
    if sys.platform != "win32":
        return
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}" --background'
                else:
                    python_exe = sys.executable
                    command = f'"{python_exe}" "{os.path.abspath(__file__)}" --background'
                winreg.SetValueEx(
                    key, "DextyTwitchNotifier", 0, winreg.REG_SZ, command
                )
            else:
                try:
                    winreg.DeleteValue(key, "DextyTwitchNotifier")
                except FileNotFoundError:
                    pass
    except Exception:
        pass


class StatusDot(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.set_status(False)

    def set_status(self, online):
        color = "#38d47a" if online else "#697386"
        self.setStyleSheet(
            f"background:{color}; border-radius:6px; min-width:12px; min-height:12px;"
        )


class FlashButton(QPushButton):
    """A normal button with a short green fade after it is clicked.

    Only paint-related properties are animated.  Font weight, padding, border
    width and geometry stay untouched, so neither the label nor its parent
    window can jump by a few pixels while the feedback animation is running.
    """

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._flash_animation = QVariantAnimation(self)
        self._flash_animation.setDuration(700)
        self._flash_animation.setStartValue(QColor("#22c55e"))
        self._flash_animation.setEndValue(QColor("#232329"))
        self._flash_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._flash_animation.valueChanged.connect(self._apply_flash_color)
        self._flash_animation.finished.connect(self._clear_flash_style)
        self.clicked.connect(self.flash)

    def flash(self):
        self._flash_animation.stop()
        self._flash_animation.start()

    def _apply_flash_color(self, color):
        if not isinstance(color, QColor):
            color = QColor(color)
        border = color.lighter(120).name()
        # Deliberately do not change padding/font/radius here. Those values
        # affect sizeHint() and used to make both the text and popup twitch.
        self.setStyleSheet(
            f"background-color:{color.name()};border-color:{border};color:white;"
        )

    def _clear_flash_style(self):
        self.setStyleSheet("")


class RemoveDelegate(QStyledItemDelegate):
    """Paint an inset cross in the edit gutter, without embedded cell widgets."""
    def __init__(self, window):
        super().__init__(window.table)
        self.window = window
        self.pressed_login = None

    @staticmethod
    def hit_rect(rect):
        return QRect(rect.center().x() - 13, rect.center().y() - 13, 26, 26)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self.window._edit_progress)
        painter.setPen(QPen(QColor("#f87171"), 2.2, Qt.SolidLine, Qt.RoundCap))
        center = option.rect.center()
        painter.drawLine(center.x()-5, center.y()-5, center.x()+5, center.y()+5)
        painter.drawLine(center.x()+5, center.y()-5, center.x()-5, center.y()+5)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not self.window.edit_btn.isChecked():
            self.pressed_login = None
            return False
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return False
        if event.button() != Qt.LeftButton:
            return False
        inside = self.hit_rect(option.rect).contains(event.position().toPoint())
        login = index.data(Qt.UserRole)
        if event.type() == QEvent.MouseButtonPress:
            self.pressed_login = login if inside else None
        else:
            pressed = self.pressed_login
            self.pressed_login = None
            if inside and login and pressed == login:
                # Defer rebuilding the model until Qt finishes this mouse event.
                QTimer.singleShot(0, lambda value=str(login): self.window.remove_streamer(value))
        return True


class StreamerCard(QFrame):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("streamerCard")
        self.setStyleSheet(
            "QFrame#streamerCard{background:#18181b;border:1px solid #2b2b31;border-radius:10px;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        dot = StatusDot()
        dot.set_status(item.get("online", False))
        top.addWidget(dot)
        name = QLabel(item.get("display_name") or item.get("configured_name"))
        name.setStyleSheet("font-weight:700;font-size:13px;color:#f4f4f5;")
        top.addWidget(name)
        top.addStretch()
        badge = QLabel("LIVE" if item.get("online") else "OFFLINE")
        badge.setStyleSheet(
            "font-size:10px;font-weight:700;color:%s;" %
            ("#38d47a" if item.get("online") else "#8b8b95")
        )
        top.addWidget(badge)
        layout.addLayout(top)

        if item.get("online"):
            game = item.get("game") or "Twitch"
            duration = format_duration(item.get("started_at", ""))
            meta = game + (f" · {duration}" if duration else "")
            meta_label = QLabel(meta)
            meta_label.setStyleSheet("color:#a1a1aa;font-size:11px;")
            layout.addWidget(meta_label)
            title = item.get("title") or ""
            if title:
                title_label = QLabel(title)
                title_label.setWordWrap(True)
                title_label.setStyleSheet("color:#d4d4d8;font-size:12px;")
                layout.addWidget(title_label)

        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            webbrowser.open(f"https://twitch.tv/{self.item.get('login')}")
        super().mousePressEvent(event)


class TrayPopup(QWidget):
    manage_requested = Signal()
    refresh_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(390)
        self.snapshot_data = {"streamers": [], "paused": False}
        self.last_check_text = "—"
        self.twitch_state = "connecting"
        self.telegram_state = "connecting"
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("popupPanel")
        panel.setStyleSheet(
            "QFrame#popupPanel{background:#0f0f12;border:1px solid #303038;border-radius:16px;}"
        )
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Twitch Notifier")
        title.setStyleSheet("font-size:16px;font-weight:800;color:white;")
        header.addWidget(title)
        header.addStretch()
        self.online_count = QLabel("0 online")
        self.online_count.setStyleSheet("color:#a1a1aa;font-size:11px;")
        header.addWidget(self.online_count)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}")
        self.cards_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(7)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_widget)
        layout.addWidget(self.scroll)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.twitch_service = QLabel("Twitch ●")
        self.telegram_service = QLabel("Telegram ●")
        for label in (self.twitch_service, self.telegram_service):
            label.setStyleSheet("color:#8b8b95;font-size:11px;font-weight:600;")
        footer.addWidget(self.twitch_service)
        footer.addWidget(self.telegram_service)
        footer.addStretch()
        self.last_check = QLabel("Check: —")
        self.last_check.setStyleSheet("color:#a1a1aa;font-size:11px;font-weight:500;")
        footer.addWidget(self.last_check)
        layout.addLayout(footer)

        buttons = QHBoxLayout()
        self.refresh_btn = FlashButton(tr('Обновить'))
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        manage = QPushButton(tr('Управление стримерами'))
        manage.setFixedHeight(32)
        manage.setObjectName("primary")
        manage.clicked.connect(self._manage)
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(manage)
        layout.addLayout(buttons)

        self.setStyleSheet(
            "QPushButton{background:#232329;color:#ededf0;border:1px solid #34343c;"
            "border-radius:8px;padding:7px 10px;font-size:11px;}"
            "QPushButton:hover{background:#2c2c34;}"
            "QPushButton#primary{background:#9146ff;border-color:#9146ff;color:white;font-weight:700;}"
            "QPushButton#primary:hover{background:#a970ff;}"
        )

    def _manage(self):
        self.hide()
        self.manage_requested.emit()

    def set_snapshot(self, data):
        self.snapshot_data = data
        self._rebuild_cards()

    def _rebuild_cards(self):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        streamers = list(self.snapshot_data.get("streamers", []))
        streamers.sort(key=lambda x: (not x.get("online", False), x.get("display_name", "").lower()))
        online_count = sum(1 for x in streamers if x.get("online"))
        paused = self.snapshot_data.get("paused", False)
        self.online_count.setText(tr('Пауза') if paused else f"{online_count} online")
        for entry in streamers:
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, StreamerCard(entry))
        if not streamers:
            empty = QLabel(tr('Список стримеров пуст'))
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#8b8b95;padding:30px;")
            self.cards_layout.insertWidget(0, empty)

        QTimer.singleShot(0, self._resize_to_content)

    def _resize_to_content(self):
        # Make the popup naturally grow with the streamer list. A scrollbar is
        # used only as a last-resort safety if the list is physically taller
        # than the available screen. Keep the visible popup anchored in place
        # so a refresh cannot make the whole window hop by a few pixels.
        old_pos = self.pos() if self.isVisible() else None
        self.cards_widget.adjustSize()
        self.cards_layout.activate()
        content_h = max(1, self.cards_layout.sizeHint().height())
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(content_h + 2)
        self.adjustSize()

        try:
            from PySide6.QtGui import QCursor
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        except Exception:
            screen = QApplication.primaryScreen()

        if screen:
            max_popup_h = int(screen.availableGeometry().height() * 0.90)
            if self.height() > max_popup_h:
                overflow = self.height() - max_popup_h
                self.scroll.setFixedHeight(max(140, content_h - overflow - 4))
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.adjustSize()

        if old_pos is not None:
            self.move(old_pos)

    def set_last_check(self, value):
        self.last_check_text = value
        self.last_check.setText(f"Check: {value}")

    def set_services(self, twitch_state=None, telegram_state=None):
        if twitch_state is not None:
            self.twitch_state = twitch_state
        if telegram_state is not None:
            self.telegram_state = telegram_state

        status_style = {
            "not_configured": ("●", "#facc15"),
            "disabled": ("○", "#8b8b95"),
            "ready": ("●", "#4ade80"),
            "connected": ("●", "#4ade80"),
            "connecting": ("◐", "#facc15"),
            "error": ("●", "#f87171"),
        }
        twitch_symbol, twitch_color = status_style.get(self.twitch_state, ("●", "#8b8b95"))
        telegram_symbol, telegram_color = status_style.get(self.telegram_state, ("●", "#8b8b95"))
        self.twitch_service.setText(f"Twitch {twitch_symbol}")
        self.twitch_service.setStyleSheet(
            f"color:{twitch_color};font-size:11px;font-weight:600;"
        )
        self.telegram_service.setText(f"Telegram {telegram_symbol}")
        self.telegram_service.setStyleSheet(
            f"color:{telegram_color};font-size:11px;font-weight:600;"
        )

    def show_near_cursor(self):
        screen = QApplication.screenAt(QApplication.instance().primaryScreen().geometry().center())
        cursor_pos = QApplication.instance().primaryScreen().availableGeometry().bottomRight()
        try:
            from PySide6.QtGui import QCursor
            cursor_pos = QCursor.pos()
            screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        except Exception:
            screen = QApplication.primaryScreen()

        self.adjustSize()
        geo = screen.availableGeometry()
        x = min(max(geo.left() + 8, cursor_pos.x() - self.width() + 20), geo.right() - self.width() - 8)
        y = cursor_pos.y() - self.height() - 12
        if y < geo.top() + 8:
            y = cursor_pos.y() + 16
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


class MainWindow(QMainWindow):
    connections_requested = Signal()
    refresh_requested = Signal()
    paused_changed = Signal(bool)
    telegram_changed = Signal(bool)
    startup_changed = Signal(bool)

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.snapshot_data = {"streamers": [], "paused": False}
        self.twitch_state = "connecting"
        self.telegram_state = "connecting"
        self.last_check_text = "—"
        self.exiting = False
        # Horizontal auto-sizing is grow-only.  If the user makes the window
        # wider by hand, refreshes must never silently shrink it again.
        self._auto_resizing = False
        self._user_width_floor = 780
        self.setWindowTitle("Dexty Twitch Notifier")
        self.resize(780, 440)
        self.setMinimumWidth(680)
        self.setWindowIcon(create_default_icon())
        self._edit_progress = 0.0
        self._build_ui()
        self._edit_animation = QVariantAnimation(self)
        self._edit_animation.setDuration(200)
        self._edit_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._edit_animation.valueChanged.connect(self._apply_edit_progress)
        self._edit_animation.finished.connect(self._resize_to_content)
        self._load_settings_to_ui()
        self.rebuild_table()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 12, 22, 12)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignTop)

        caption = QLabel(tr('Dexty Twitch Notifier — Личный мониторинг стримов Twitch'))
        caption.setStyleSheet("color:#9d9da8;font-size:11px;")
        root.addWidget(caption)

        add_row = QHBoxLayout()
        add_label = QLabel(tr('Добавление стримера'))
        add_label.setStyleSheet(
            "background:#211a2e;color:#c4a4f2;border:1px solid #3b2c50;"
            "border-radius:8px;padding:8px 10px;font-size:11px;font-weight:600;"
        )
        add_row.addWidget(add_label)
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText(tr('Twitch-логин, например dima_wallhacks'))
        self.login_input.returnPressed.connect(self.add_streamer)
        add_btn = QPushButton(tr('+ Добавить'))
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.add_streamer)
        add_row.addWidget(self.login_input, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        self.empty_hint = QLabel(tr("Список стримеров пуст"))
        self.empty_hint.setWordWrap(True)
        root.addWidget(self.empty_hint)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", tr('Статус'), tr('Стример'), tr('Стрим')])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Subtle grid lines make the columns easier to scan without
        # turning the table into a heavy spreadsheet.
        self.table.setShowGrid(True)
        self.table.setGridStyle(Qt.SolidLine)
        self.table.setAlternatingRowColors(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.viewport().setCursor(Qt.PointingHandCursor)
        header_view = self.table.horizontalHeader()
        header_view.setMinimumSectionSize(1)
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnHidden(0, True)
        self.remove_delegate = RemoveDelegate(self)
        self.table.setItemDelegateForColumn(0, self.remove_delegate)
        root.addWidget(self.table, 0)

        settings = QFrame()
        settings.setObjectName("settingsCard")
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(14, 12, 14, 12)
        self.telegram_checkbox = QCheckBox(tr('Уведомления в Telegram'))
        self.telegram_checkbox.toggled.connect(self.on_telegram_toggle)
        self.startup_checkbox = QCheckBox(tr('Запускать вместе с Windows'))
        self.startup_checkbox.toggled.connect(self.on_startup_toggle)
        self.pause_checkbox = QCheckBox(tr('Пауза мониторинга'))
        self.pause_checkbox.toggled.connect(self.on_pause_toggle)
        settings_layout.addWidget(self.telegram_checkbox)
        settings_layout.addWidget(self.startup_checkbox)
        settings_layout.addWidget(self.pause_checkbox)
        settings_layout.addStretch()
        self.refresh_btn = FlashButton(tr('Обновить сейчас'))
        self.refresh_btn.setObjectName("settingsRefresh")
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.setMinimumWidth(126)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        settings_layout.addWidget(self.refresh_btn)
        self.edit_btn = QPushButton(tr('Редактировать список'))
        self.edit_btn.setObjectName("editList")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setFixedHeight(32)
        self.edit_btn.toggled.connect(self._toggle_edit_mode)
        settings_layout.addWidget(self.edit_btn)
        root.addWidget(settings)

        status_row = QHBoxLayout()
        self.running_badge = QLabel("● RUNNING")
        self.running_badge.setStyleSheet("color:#4ade80;font-weight:700;font-size:10px;")
        status_row.addWidget(self.running_badge)
        self.twitch_label = QLabel(tr('Twitch API: подключение…'))
        self.telegram_label = QLabel(tr('Telegram: подключение…'))
        self.check_label = QLabel(tr('Последняя проверка: —'))
        for label in (self.twitch_label, self.telegram_label, self.check_label):
            label.setStyleSheet("color:#9696a2;font-size:11px;")
        status_row.addWidget(self.twitch_label)
        status_row.addWidget(self.telegram_label)
        self.connections_btn = QPushButton(tr('Настроить') if not os.path.exists(TOKEN_FILE) else tr('Управление подключениями'))
        self.connections_btn.setStyleSheet("padding:3px 9px;font-size:11px;border-radius:6px;")
        self.connections_btn.clicked.connect(self.connections_requested.emit)
        status_row.addWidget(self.connections_btn)
        self.updates_btn = QPushButton(tr("Обновления"))
        self.updates_btn.setStyleSheet("padding:3px 9px;font-size:11px;border-radius:6px;")
        self.updates_btn.clicked.connect(self.show_updates)
        status_row.addWidget(self.updates_btn)
        status_row.addStretch()
        status_row.addWidget(self.check_label)
        root.addLayout(status_row)

        self.setStyleSheet(
            "QMainWindow,QWidget{background:#0f0f12;color:#ededf0;font-family:'Segoe UI';font-size:12px;}"
            "QLineEdit{background:#18181d;border:1px solid #32323a;border-radius:9px;padding:9px 10px;color:white;}"
            "QLineEdit:focus{border:1px solid #9146ff;}"
            "QPushButton{background:#232329;color:#ededf0;border:1px solid #35353d;border-radius:8px;padding:8px 11px;}"
            "QPushButton:hover{background:#2c2c34;}"
            "QPushButton#primary{background:#9146ff;border-color:#9146ff;color:white;font-weight:700;}"
            "QPushButton#primary:hover{background:#a970ff;}"
            "QPushButton#settingsRefresh,QPushButton#editList{padding:5px 11px;border-radius:8px;}"
            "QPushButton#editList:checked{background:#3b2028;border-color:#b45363;color:#fda4af;}"
            "QTableWidget{background:#151519;border:1px solid #292930;border-radius:10px;gridline-color:#24242a;}"
            "QHeaderView::section{background:#1b1b20;color:#92929c;border:none;border-right:1px solid #2a2a31;padding:9px;font-weight:700;}"
            "QTableWidget::item{padding:8px;}"
            "QFrame#settingsCard{background:#151519;border:1px solid #292930;border-radius:10px;}"
            "QCheckBox{background:transparent;spacing:7px;color:#d7d7dc;}"
        )

    def _load_settings_to_ui(self):
        # Keep settings labels intact when Qt distributes a narrow layout.
        for control in (self.telegram_checkbox, self.startup_checkbox,
                        self.pause_checkbox, self.refresh_btn, self.edit_btn):
            control.ensurePolished()
            control.setMinimumWidth(max(control.sizeHint().width(),
                control.fontMetrics().horizontalAdvance(control.text()) + 40))
        self.telegram_checkbox.blockSignals(True)
        self.telegram_checkbox.setChecked(self.config.get("telegram_notifications", True))
        self.telegram_checkbox.blockSignals(False)
        self.startup_checkbox.blockSignals(True)
        self.startup_checkbox.setChecked(self.config.get("start_with_windows", False))
        self.startup_checkbox.blockSignals(False)

    def on_telegram_toggle(self, checked):
        # The controller mirrors this state to the tray action.
        self.telegram_changed.emit(checked)

    def on_startup_toggle(self, checked):
        # The controller updates both config/Windows startup and the tray action.
        self.startup_changed.emit(checked)

    def on_pause_toggle(self, checked):
        self.paused_changed.emit(checked)

    def _toggle_edit_mode(self, enabled):
        self.remove_delegate.pressed_login = None
        self._edit_animation.stop()
        self._edit_animation.setStartValue(self._edit_progress)
        self._edit_animation.setEndValue(1.0 if enabled else 0.0)
        self._edit_animation.start()

    def _apply_edit_progress(self, value):
        self._edit_progress = float(value)
        width = round(38 * self._edit_progress)
        self.table.setColumnHidden(0, width == 0)
        if width:
            self.table.setColumnWidth(0, width)
        self.table.viewport().update()

    def _on_table_cell_clicked(self, row, column):
        """Open a channel when Status / Streamer / Stream text is clicked."""
        if column not in (1, 2, 3):
            return
        item = self.table.item(row, column)
        if not item:
            return
        login = item.data(Qt.UserRole)
        if login:
            self.open_streamer(str(login))

    def add_streamer(self):
        login = self.login_input.text().strip()
        ok, message = self.config.add_streamer(login)
        if not ok:
            QMessageBox.information(self, "Twitch Notifier", message)
            return
        self.login_input.clear()
        self.refresh_requested.emit()
        self.rebuild_table()

    def remove_streamer(self, login):
        if not self.edit_btn.isChecked():
            return
        if self.config.get("confirm_channel_removal", True):
            answer = QMessageBox(self)
            answer.setWindowTitle(tr('Удалить стримера?'))
            answer.setText(tr("Удалить {login} из списка?").format(login=login))
            answer.setInformativeText(tr('Его можно будет снова добавить по Twitch-логину.'))
            answer.setIcon(QMessageBox.Question)
            remove_button = answer.addButton(tr('Удалить'), QMessageBox.DestructiveRole)
            cancel_button = answer.addButton(tr('Отмена'), QMessageBox.RejectRole)
            answer.setDefaultButton(cancel_button)
            answer.setEscapeButton(cancel_button)
            dont_ask = QCheckBox(tr("Больше не спрашивать"), answer)
            answer.setCheckBox(dont_ask)
            answer.exec()
            if answer.clickedButton() != remove_button:
                return
            if dont_ask.isChecked():
                self.config.set("confirm_channel_removal", False)
        self.config.remove_streamer(login)
        self.refresh_requested.emit()
        self.rebuild_table()

    def show_updates(self):
        UpdatesDialog(self).exec()

    def open_streamer(self, login):
        webbrowser.open(f"https://twitch.tv/{login}")

    def set_snapshot(self, data):
        self.snapshot_data = data
        paused = bool(data.get("paused", False))
        self.pause_checkbox.blockSignals(True)
        self.pause_checkbox.setChecked(paused)
        self.pause_checkbox.blockSignals(False)
        self.running_badge.setText("Ⅱ PAUSED" if paused else "● RUNNING")
        self.running_badge.setStyleSheet(
            ("color:#facc15;" if paused else "color:#4ade80;")
            + "font-weight:700;font-size:10px;"
        )
        self.rebuild_table()

    def rebuild_table(self):
        self.empty_hint.setVisible(not bool(self.snapshot_data.get("streamers")))
        # Replacing cell widgets while the table is painting causes a brief
        # black/right-side flash on Windows. Freeze painting for the tiny
        # rebuild and repaint once when the table is complete.
        self.table.setUpdatesEnabled(False)
        by_login = {
            x.get("login", "").lower(): x
            for x in self.snapshot_data.get("streamers", [])
        }

        # Build rows from the configured list, then sort them:
        # LIVE first, then alphabetically by the visible streamer name.
        rows = []
        for configured_name in self.config.streamers():
            login = configured_name.lower()
            data = by_login.get(
                login,
                {
                    "login": login,
                    "configured_name": configured_name,
                    "display_name": configured_name,
                    "online": False,
                    "title": "",
                    "game": "",
                    "started_at": "",
                },
            )
            rows.append((configured_name, login, data))

        rows.sort(
            key=lambda item: (
                not bool(item[2].get("online", False)),
                (item[2].get("display_name") or item[0]).casefold(),
            )
        )

        self.table.setRowCount(len(rows))

        for row, (configured_name, login, data) in enumerate(rows):

            status = QTableWidgetItem("●  LIVE" if data.get("online") else "○  Offline")
            status.setForeground(QColor("#4ade80" if data.get("online") else "#7d7d88"))
            status.setData(Qt.UserRole, login)
            self.table.setItem(row, 1, status)

            name = QTableWidgetItem(data.get("display_name") or configured_name)
            name.setData(Qt.UserRole, login)
            self.table.setItem(row, 2, name)

            if data.get("online"):
                pieces = []
                if data.get("game"):
                    pieces.append(data["game"])
                duration = format_duration(data.get("started_at", ""))
                if duration:
                    pieces.append(duration)
                text = " · ".join(pieces)
                if data.get("title"):
                    text += (" — " if text else "") + data["title"]
            else:
                text = tr('Не в эфире')
            stream_item = QTableWidgetItem(text)
            stream_item.setData(Qt.UserRole, login)
            stream_item.setForeground(QColor("#c4c4cc" if data.get("online") else "#777781"))
            self.table.setItem(row, 3, stream_item)

            remove_item = QTableWidgetItem("")
            remove_item.setData(Qt.UserRole, login)
            self.table.setItem(row, 0, remove_item)
            self.table.setRowHeight(row, 44)

        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        QTimer.singleShot(0, self._resize_to_content)

    def _resize_to_content(self):
        """Fit height to rows and grow width for long stream titles.

        Width is deliberately *grow-only*: automatic refreshes may make the
        window wider when a title needs it, but they never undo a width the
        user chose manually.  Height still follows the streamer count.
        """
        # Hidden widgets may not have received their final style/layout yet.
        self.ensurePolished()
        current_width = max(self.width(), self._user_width_floor)

        # --- Vertical fit -------------------------------------------------
        header_h = self.table.horizontalHeader().height()
        rows_h = sum(self.table.rowHeight(i) for i in range(self.table.rowCount()))
        table_h = header_h + rows_h + self.table.frameWidth() * 2 + 4
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setFixedHeight(table_h)

        # --- Horizontal fit -----------------------------------------------
        # Status/name fit their text; the stream column uses remaining space.
        self.table.resizeColumnToContents(1)
        self.table.resizeColumnToContents(2)

        metrics = self.table.fontMetrics()
        header_metrics = self.table.horizontalHeader().fontMetrics()
        desired_stream_w = header_metrics.horizontalAdvance(tr('Стрим')) + 36
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 3)
            if item:
                desired_stream_w = max(
                    desired_stream_w,
                    metrics.horizontalAdvance(item.text()) + 34,
                )
        desired_stream_w = max(300, desired_stream_w)

        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            # Keep the left edge where the user placed it and grow primarily
            # to the right. Leave a small safety margin at the screen edge.
            max_window_w = max(680, geo.right() - self.x() - 8)
            max_window_h = int(geo.height() * 0.92)
        else:
            max_window_w = 1600
            max_window_h = 900

        # Root layout has 22 px margins on both sides. Add a few pixels for the
        # table frame and rounding.  This yields the window width needed for a
        # Stream column wide enough to show the longest title without ellipsis,
        # up to the physical screen limit.
        non_stream_w = (
            44
            + self.table.columnWidth(0)
            + self.table.columnWidth(1)
            + self.table.columnWidth(2)
            + self.table.frameWidth() * 2
            + 8
        )
        desired_window_w = non_stream_w + desired_stream_w
        target_w = max(current_width, self.centralWidget().minimumSizeHint().width(),
                       min(max_window_w, max(780, desired_window_w)))

        # QMainWindow.height() already excludes the native title bar/borders.
        # While hidden, centralWidget().height() can be stale. Subtracting it
        # from the window height used to accumulate phantom height on each poll.
        # This window has no menu/toolbars: its client height is the root layout.
        root = self.centralWidget().layout()
        root.invalidate()
        root.activate()
        # Refresh QMainWindow's cached minimum too, so removing rows can shrink
        # the window in this pass rather than waiting for the next update.
        self.layout().invalidate()
        self.layout().activate()
        target_h = root.sizeHint().height()

        if target_h > max_window_h:
            overflow = target_h - max_window_h
            self.table.setFixedHeight(max(150, table_h - overflow - 4))
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            if self.centralWidget().layout():
                self.centralWidget().layout().activate()
            self.layout().invalidate()
            self.layout().activate()
            target_h = max_window_h

        self._auto_resizing = True
        try:
            if self.width() != target_w or self.height() != target_h:
                self.resize(target_w, target_h)
        finally:
            self._auto_resizing = False

    def showEvent(self, event):
        super().showEvent(event)
        # Resolve the actual screen/style on every opening from the tray,
        # before painting. One queued pass handles pending native layout work.
        self._resize_to_content()
        QTimer.singleShot(0, self._resize_to_content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A resize caused by the user becomes the new lower bound for future
        # automatic refreshes. Programmatic auto-sizing is excluded by the flag.
        if self.isVisible() and not self._auto_resizing:
            self._user_width_floor = max(self.minimumWidth(), event.size().width())

    def set_twitch_status(self, state):
        self.twitch_state = state
        mapping = {
            "not_configured": (tr('Twitch API: ● не настроено'), "#facc15"),
            "connected": (tr('Twitch API: ● подключено'), "#4ade80"),
            "connecting": (tr('Twitch API: ◐ подключение…'), "#facc15"),
            "error": (tr('Twitch API: ● ошибка, переподключение…'), "#f87171"),
        }
        text, color = mapping.get(state, (f"Twitch API: {state}", "#9696a2"))
        self.twitch_label.setText(text)
        self.twitch_label.setStyleSheet(f"color:{color};font-size:11px;font-weight:600;")

    def set_telegram_status(self, state):
        self.telegram_state = state
        mapping = {
            "not_configured": (tr('Telegram: ● не настроено'), "#facc15"),
            "disabled": (tr('Telegram: ○ выключено'), "#9696a2"),
            "ready": (tr('Telegram: ● настроено'), "#4ade80"),
            "connected": (tr('Telegram: ● подключено'), "#4ade80"),
            "connecting": (tr('Telegram: ◐ подключение…'), "#facc15"),
            "error": (tr('Telegram: ● ошибка'), "#f87171"),
        }
        text, color = mapping.get(state, (f"Telegram: {state}", "#9696a2"))
        self.telegram_label.setText(text)
        self.telegram_label.setStyleSheet(f"color:{color};font-size:11px;font-weight:600;")

    def set_last_check(self, value):
        self.last_check_text = value
        self.check_label.setText(tr("Последняя проверка: {value}").format(value=value))

    def closeEvent(self, event):
        if self.exiting:
            event.accept()
            return
        if self.config.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
        else:
            event.accept()


class TwitchNotifierApp(QObject):
    def __init__(self, qt_app: QApplication):
        super().__init__()
        self.qt_app = qt_app
        self.restart_requested = False
        self.config = ConfigManager()
        self.signals = AppSignals()
        self.monitor = TwitchMonitor(self.config, self.signals)
        self.main_window = MainWindow(self.config)
        self.popup = TrayPopup()
        self.tray = QSystemTrayIcon(create_default_icon(), self.qt_app)
        self.tray.setToolTip("Dexty Twitch Notifier")

        # A tray double-click normally arrives after the first single-click
        # activation. Delay the single-click popup just long enough to know
        # whether a second click is coming, so the popup never flashes before
        # the main window on a double-click.
        self.tray_click_timer = QTimer(self)
        self.tray_click_timer.setSingleShot(True)
        # The user double-clicks quickly, so waiting the full system double-click
        # interval makes a normal single-click feel sluggish. Half the system
        # interval is enough to catch a fast second click while making the popup
        # appear roughly twice as fast (typically ~200-250 ms on Windows).
        self.tray_click_timer.setInterval(
            max(180, min(280, self.qt_app.doubleClickInterval() // 2))
        )
        self.tray_click_timer.timeout.connect(self._toggle_tray_popup)

        self._build_tray_menu()
        self._connect()
        self.tray.show()
        self.monitor.start()

        if self.config.get("start_with_windows", False):
            set_start_with_windows(True)

    def _connect(self):
        self.signals.snapshot.connect(self.on_snapshot)
        self.signals.twitch_status.connect(self.on_twitch_status)
        self.signals.telegram_status.connect(self.on_telegram_status)
        self.signals.last_check.connect(self.on_last_check)

        self.main_window.connections_requested.connect(self.edit_connections)
        self.main_window.refresh_requested.connect(self.monitor.refresh_now)
        self.main_window.paused_changed.connect(self.on_pause_changed)
        self.main_window.telegram_changed.connect(self.on_telegram_changed)
        self.main_window.startup_changed.connect(self.on_startup_changed)
        self.popup.refresh_requested.connect(self.monitor.refresh_now)
        self.popup.manage_requested.connect(self.show_main_window)
        self.tray.activated.connect(self.on_tray_activated)

    def _build_tray_menu(self):
        menu = QMenu()
        open_action = QAction(tr('Открыть Twitch Notifier'), menu)
        open_action.triggered.connect(self.show_main_window)
        refresh_action = QAction(tr('Обновить сейчас'), menu)
        refresh_action.triggered.connect(self.monitor.refresh_now)
        self.pause_action = QAction(tr('Пауза мониторинга'), menu)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.on_pause_changed)
        menu.addAction(open_action)
        menu.addAction(refresh_action)
        menu.addAction(self.pause_action)
        menu.addSeparator()

        telegram_action = QAction(tr('Telegram уведомления'), menu)
        telegram_action.setCheckable(True)
        telegram_action.setChecked(self.config.get("telegram_notifications", True))
        telegram_action.toggled.connect(self._toggle_telegram_from_tray)
        self.telegram_action = telegram_action
        menu.addAction(telegram_action)

        startup_action = QAction(tr('Запускать вместе с Windows'), menu)
        startup_action.setCheckable(True)
        startup_action.setChecked(self.config.get("start_with_windows", False))
        startup_action.toggled.connect(self._toggle_startup_from_tray)
        self.startup_action = startup_action
        menu.addAction(startup_action)
        menu.addSeparator()

        exit_action = QAction(tr('Выход'), menu)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)

    def on_telegram_changed(self, checked):
        values = self.monitor.connections
        self.on_telegram_status("disabled" if not checked else "ready" if
            values.get("telegram_bot_token") and values.get("telegram_chat_id") else "not_configured")
        self.config.set("telegram_notifications", checked)
        # Mirror the same state into the tray without firing the action again.
        self.telegram_action.blockSignals(True)
        self.telegram_action.setChecked(checked)
        self.telegram_action.blockSignals(False)
        self.main_window.telegram_checkbox.blockSignals(True)
        self.main_window.telegram_checkbox.setChecked(checked)
        self.main_window.telegram_checkbox.blockSignals(False)

    def on_startup_changed(self, checked):
        self.config.set("start_with_windows", checked)
        set_start_with_windows(checked)
        # Mirror the same state into the tray without firing the action again.
        self.startup_action.blockSignals(True)
        self.startup_action.setChecked(checked)
        self.startup_action.blockSignals(False)
        self.main_window.startup_checkbox.blockSignals(True)
        self.main_window.startup_checkbox.setChecked(checked)
        self.main_window.startup_checkbox.blockSignals(False)

    def _toggle_telegram_from_tray(self, checked):
        self.on_telegram_changed(checked)

    def _toggle_startup_from_tray(self, checked):
        self.on_startup_changed(checked)

    def on_pause_changed(self, checked):
        self.monitor.set_paused(checked)
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(checked)
        self.pause_action.blockSignals(False)
        self.main_window.pause_checkbox.blockSignals(True)
        self.main_window.pause_checkbox.setChecked(checked)
        self.main_window.pause_checkbox.blockSignals(False)

    def _toggle_tray_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            self.popup.show_near_cursor()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # Do not show the popup immediately. Windows first reports the
            # initial click even when it is about to become a double-click.
            # The timer is cancelled below if DoubleClick arrives.
            self.tray_click_timer.start()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.tray_click_timer.stop()
            self.popup.hide()
            self.show_main_window()

    def show_main_window(self):
        self.popup.hide()
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def on_snapshot(self, data):
        self.main_window.set_snapshot(data)
        self.popup.set_snapshot(data)
        online = [x for x in data.get("streamers", []) if x.get("online")]
        if data.get("paused"):
            self.tray.setToolTip(tr('Dexty Twitch Notifier — пауза'))
        elif online:
            names = ", ".join(x.get("display_name", x.get("login", "")) for x in online)
            self.tray.setToolTip(tr("Онлайн: {names}").format(names=names)[:127])
        else:
            self.tray.setToolTip(tr('Dexty Twitch Notifier — никто не стримит'))

    def on_twitch_status(self, state):
        self.main_window.set_twitch_status(state)
        self.popup.set_services(twitch_state=state)

    def on_telegram_status(self, state):
        self.main_window.set_telegram_status(state)
        self.popup.set_services(telegram_state=state)

    def on_last_check(self, value):
        self.main_window.set_last_check(value)
        self.popup.set_last_check(value)

    def edit_connections(self):
        self.config.set("setup_seen", True)
        dialog = ConnectionsDialog(DATA_DIR, self.main_window)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        if dialog.values == dialog.original and dialog.token_update is None and not dialog.language_changed:
            return
        try:
            save_connections(DATA_DIR, dialog.values, dialog.token_update)
            self.config.set("telegram_notifications", bool(dialog.values.get("telegram_bot_token") and dialog.values.get("telegram_chat_id")))
        except OSError:
            QMessageBox.warning(self.main_window, tr('Не удалось сохранить'),
                                tr('Проверьте доступ к папке настроек и свободное место на диске.'))
            return
        self.restart_requested = True
        self.exit_app()

    def exit_app(self):
        self.main_window.exiting = True
        self.monitor.stop()
        self.tray.hide()
        QTimer.singleShot(100, self.qt_app.quit)


class SingleInstance(QObject):
    show_requested = Signal()

    def __init__(self, parent=None, name="DextyTwitchNotifier"):
        super().__init__(parent)
        import ctypes
        from ctypes import wintypes
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateMutexW(None, False, "Local\\" + name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.primary = ctypes.get_last_error() != 183
        self.server = None
        # Named pipes are restricted to the current Windows user by Qt.
        pipe_name = name + "-" + os.environ.get("USERNAME", "user")
        if not self.primary:
            client = QLocalSocket(self)
            client.connectToServer(pipe_name)
            if client.waitForConnected(2500):
                client.disconnectFromServer()
            self.close()
            return
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        if not self.server.listen(pipe_name):
            self.close()
            raise RuntimeError(tr('Не удалось открыть локальный канал программы.'))
        self.server.newConnection.connect(self._activate)

    def _activate(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.close()
            client.deleteLater()
        self.show_requested.emit()

    def close(self):
        if self.server is not None:
            self.server.close()
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def self_test(qt_app, report_path):
    """Offline packaging check; never starts the monitor or sends notifications."""
    import tempfile
    import traceback
    from PySide6.QtCore import QEventLoop
    global DATA_DIR, CONFIG_FILE, TOKEN_FILE, ERROR_LOG
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        with tempfile.TemporaryDirectory(prefix="dexty-test-") as folder:
            DATA_DIR = folder
            CONFIG_FILE = os.path.join(folder, "config.json")
            TOKEN_FILE = os.path.join(folder, "token.json")
            ERROR_LOG = os.path.join(folder, "error.log")
            config = ConfigManager()
            config.set("streamers", ["offline_user", "live_user"])
            window = MainWindow(config)
            window.set_snapshot({"paused": False, "streamers": [
                {"login": "live_user", "display_name": "Live User", "online": True,
                 "game": "Test", "title": tr('Проверка установленной программы')}]})
            qt_app.processEvents()
            assert window.table.item(0, 2).text() == "Live User"
            assert window.table.item(0, 3).toolTip() == ""
            assert window.table.isColumnHidden(0)
            window.edit_btn.click()
            loop = QEventLoop()
            QTimer.singleShot(300, loop.quit)
            loop.exec()
            assert window.table.columnWidth(0) == 38
            assert not create_default_icon().isNull()
            popup = TrayPopup()
            popup.set_snapshot(window.snapshot_data)
            qt_app.processEvents()
            assert ConfigManager().streamers() == ["offline_user", "live_user"]
            import certifi
            assert os.path.isfile(certifi.where())
            report.update(ok=True, rows=window.table.rowCount(), icon=True,
                          config_roundtrip=True, certificates=True, network_started=False)
            popup.close()
            window.exiting = True
            window.close()
    except Exception:
        report["error"] = traceback.format_exc()
    with open(report_path, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    if "--restart-from" in sys.argv:
        wait_for_parent(int(sys.argv[sys.argv.index("--restart-from") + 1]))
    if "--import-settings" in sys.argv:
        try:
            import_legacy(sys.argv[sys.argv.index("--import-settings") + 1], DATA_DIR)
        except Exception:
            sys.exit(1)
        sys.exit(0)
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setApplicationName("Dexty Twitch Notifier")
    qt_app.setApplicationVersion(APP_VERSION)
    if "--self-test" in sys.argv:
        sys.exit(self_test(qt_app, sys.argv[sys.argv.index("--self-test") + 1]))
    instance = SingleInstance(qt_app)
    if not instance.primary:
        sys.exit(0)
    qt_app.aboutToQuit.connect(instance.close)
    apply_pending_token(DATA_DIR)
    controller = TwitchNotifierApp(qt_app)
    instance.show_requested.connect(controller.show_main_window)
    if "--background" not in sys.argv:
        QTimer.singleShot(0, controller.show_main_window)
    if not controller.config.get("setup_seen", False):
        QTimer.singleShot(250, controller.edit_connections)
    result = qt_app.exec()
    if controller.restart_requested:
        import subprocess
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(os.path.abspath(__file__))
        command.extend(["--restart-from", str(os.getpid())])
        subprocess.Popen(command, close_fds=True)
    sys.exit(result)








