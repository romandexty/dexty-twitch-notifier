"""Manual, anonymous GitHub release checks; no automatic installation."""
import re
import threading
import webbrowser
import requests
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from i18n import tr

APP_VERSION = "1.0.1"
RELEASES_URL = "https://github.com/romandexty/dexty-twitch-notifier/releases/latest"
API_URL = "https://api.github.com/repos/romandexty/dexty-twitch-notifier/releases/latest"

def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("Unsupported release version")
    return tuple(map(int, match.groups()))

def latest_version():
    response = requests.get(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "DextyTwitchNotifier/" + APP_VERSION}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("draft") or data.get("prerelease"):
        raise ValueError("Not a stable release")
    tag = data["tag_name"]
    version_tuple(tag)
    return tag.lstrip("v")

class UpdatesDialog(QDialog):
    checked = Signal(str, bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Обновления"))
        self.setMinimumWidth(420)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.current = QLabel(tr("Установленная версия: {version}").format(version=APP_VERSION))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.current)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.retry = QPushButton(tr("Проверить обновления"))
        self.retry.clicked.connect(self.start_check)
        self.download = QPushButton(tr("Открыть страницу загрузки"))
        self.download.clicked.connect(lambda: webbrowser.open(RELEASES_URL))
        row.addWidget(self.retry)
        row.addWidget(self.download)
        layout.addLayout(row)
        close = QPushButton(tr("Закрыть"))
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.checked.connect(self.show_result)
        self.start_check()

    def start_check(self):
        if not self.retry.isEnabled():
            return
        self.retry.setEnabled(False)
        self.download.setVisible(False)
        self.status.setText(tr("Проверяем последнюю версию на GitHub…"))
        def worker():
            try:
                result = latest_version()
                self.checked.emit(result, True)
            except Exception:
                self.checked.emit("", False)
        threading.Thread(target=worker, daemon=True).start()

    def show_result(self, version, success):
        self.retry.setEnabled(True)
        self.download.setVisible(True)
        if not success:
            self.status.setText(tr("Не удалось проверить обновления. Проверьте интернет или откройте страницу загрузки."))
        elif version_tuple(version) > version_tuple(APP_VERSION):
            self.status.setText(tr("Доступна новая версия: {version}. Скачайте установщик со страницы релиза.").format(version=version))
        elif version_tuple(version) == version_tuple(APP_VERSION):
            self.status.setText(tr("У вас последняя версия: {version}.").format(version=version))
        else:
            self.status.setText(tr("Новых обновлений нет. Последняя опубликованная версия: {version}; ваша версия новее.").format(version=version))
