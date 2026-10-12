"""First-run guide and returning-user connection review."""
import threading
import time
import re
import webbrowser
from pathlib import Path
import requests
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QStackedWidget, QWidget, QCheckBox)
import i18n
from connections_ui import load_connections, read_json
from public_twitch import PUBLIC_CLIENT_ID, begin_sign_in, poll_sign_in

class Results(QObject):
    done = Signal(str, object)

class SetupDialog(QDialog):
    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.original = load_connections(folder)
        self.values = None
        self.token_update = None
        self.language_changed = False
        self.cancelled = threading.Event()
        self.busy = False
        self.device = None
        self.telegram_verified = False
        self.bot_username = ''
        self.saved_twitch = bool(read_json(Path(folder) / 'token.json').get('access_token'))
        self.review_mode = self.saved_twitch or bool(self.original.get('telegram_bot_token'))
        self.results = Results(self)
        self.results.done.connect(self.completed)
        self.setMinimumWidth(650)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        self.progress = QLabel()
        self.progress.setStyleSheet('color:#c4a4f2;font-size:14px;font-weight:600;')
        root.addWidget(self.progress)
        self.pages = QStackedWidget()
        layouts = []
        for _ in range(5):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 8, 0, 8)
            layout.setSpacing(14)
            self.pages.addWidget(page)
            layouts.append(layout)
        root.addWidget(self.pages)
        self.language = QComboBox()
        self.language.addItem('English', 'en')
        self.language.addItem('Русский', 'ru')
        self.language.setCurrentIndex(0 if i18n.LANGUAGE == 'en' else 1)
        self.welcome = self.label(layouts[0])
        layouts[0].addWidget(QLabel('Language / Язык'))
        layouts[0].addWidget(self.language)
        layouts[0].addStretch()
        self.client = QLineEdit(PUBLIC_CLIENT_ID, self)
        self.client.hide()
        self.intro = self.label(layouts[1])
        self.connect_button = self.button(layouts[1], self.connect_twitch)
        self.code_row = QWidget()
        code_layout = QHBoxLayout(self.code_row)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.code_label = QLabel()
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code_label.setStyleSheet('font-size:20px;font-weight:700;color:#c4a4f2;')
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.copy_code)
        self.open_twitch = QPushButton()
        self.open_twitch.clicked.connect(lambda: webbrowser.open('https://www.twitch.tv/activate'))
        for widget in (self.code_label, self.copy_button, self.open_twitch):
            code_layout.addWidget(widget)
        layouts[1].addWidget(self.code_row)
        self.code_row.hide()
        self.status = self.label(layouts[1])
        layouts[1].addStretch()
        self.telegram_intro = self.label(layouts[2])
        self.telegram_pages = QStackedWidget()
        layouts[2].addWidget(self.telegram_pages)
        telegram_layouts = []
        for _ in range(4):
            page = QWidget()
            inner = QVBoxLayout(page)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(12)
            telegram_layouts.append(inner)
            self.telegram_pages.addWidget(page)
        self.create_help = self.label(telegram_layouts[0])
        self.botfather = self.button(telegram_layouts[0], lambda: webbrowser.open('https://t.me/BotFather'))
        self.copy_command = self.button(telegram_layouts[0], lambda: QApplication.clipboard().setText('/newbot'))
        self.have_token = self.button(telegram_layouts[0], lambda: self.set_telegram_step(1))
        self.token_help = self.label(telegram_layouts[1])
        self.bot = QLineEdit(self.original.get('telegram_bot_token', ''))
        self.bot.setEchoMode(QLineEdit.Password)
        self.bot.textEdited.connect(self.token_edited)
        telegram_layouts[1].addWidget(self.bot)
        self.paste_token = self.button(telegram_layouts[1], self.paste_bot_token)
        self.validate_bot = self.button(telegram_layouts[1], self.check_bot)
        self.chat_help = self.label(telegram_layouts[2])
        self.open_bot = self.button(telegram_layouts[2], self.open_telegram_bot)
        self.test_button = self.button(telegram_layouts[2], self.test_telegram)
        self.manual_chat = QCheckBox()
        telegram_layouts[2].addWidget(self.manual_chat)
        self.chat = QLineEdit(self.original.get('telegram_chat_id', ''))
        self.chat.setVisible(False)
        self.manual_chat.toggled.connect(self.chat.setVisible)
        telegram_layouts[2].addWidget(self.chat)
        self.success_help = self.label(telegram_layouts[3])
        self.telegram_status = self.label(layouts[2])
        layouts[2].addStretch()
        self.ready = self.label(layouts[3])
        layouts[3].addStretch()
        self.review_summary = self.label(layouts[4])
        self.reconnect = self.button(layouts[4], lambda: self.edit_service(1))
        self.change_telegram = self.button(layouts[4], self.edit_telegram)
        self.review_language = QComboBox()
        self.review_language.addItems(['English', 'Русский'])
        self.review_language.setCurrentIndex(self.language.currentIndex())
        self.review_language.currentIndexChanged.connect(self.language.setCurrentIndex)
        layouts[4].addWidget(QLabel('Language / Язык'))
        layouts[4].addWidget(self.review_language)
        layouts[4].addStretch()
        navigation = QHBoxLayout()
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = QPushButton()
        self.back_button.clicked.connect(self.go_back)
        self.skip_telegram = QPushButton()
        self.skip_telegram.clicked.connect(self.skip_telegram_step)
        self.next_button = QPushButton()
        self.next_button.setObjectName('primary')
        self.next_button.clicked.connect(lambda: self.change_page(1))
        self.save_button = QPushButton()
        self.save_button.setObjectName('primary')
        self.save_button.clicked.connect(self.save)
        navigation.addWidget(self.cancel_button)
        navigation.addStretch()
        for widget in (self.back_button, self.skip_telegram, self.next_button, self.save_button):
            navigation.addWidget(widget)
        root.addLayout(navigation)
        self.language.currentIndexChanged.connect(self.labels)
        self.pages.setCurrentIndex(4 if self.review_mode else 0)
        self.labels()

    def label(self, layout):
        label = QLabel()
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def button(self, layout, callback):
        button = QPushButton()
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def text(self, en, ru):
        return en if self.language.currentData() == 'en' else ru

    def labels(self):
        self.setWindowTitle(self.text('Dexty Twitch Notifier — Connections', 'Dexty Twitch Notifier — Подключения'))
        self.welcome.setText(self.text('Set up your notifier\n\nFirst connect Twitch. Then add Telegram alerts if you want them. You can skip either service and return later.', 'Настройка уведомлений\n\nСначала подключите Twitch. Затем добавьте Telegram, если нужны уведомления. Любой сервис можно пропустить и настроить позже.'))
        self.intro.setText(self.text('1. Click Get sign-in code below.\n2. Click Copy code, then Open Twitch. Paste the code on Twitch.\n3. Sign in and approve. Return here and wait for confirmation.\n\nYour password is entered only on Twitch. This app stores a personal access token on your computer.', '1. Нажмите «Получить код входа».\n2. Нажмите «Копировать код», затем «Открыть Twitch». Вставьте код на Twitch.\n3. Войдите и подтвердите доступ. Вернитесь сюда и дождитесь подтверждения.\n\nПароль вводится только на Twitch. Программа хранит личный токен доступа на вашем компьютере.'))
        self.connect_button.setText(self.text('Get sign-in code', 'Получить код входа'))
        self.copy_button.setText(self.text('Copy code', 'Копировать код'))
        self.open_twitch.setText(self.text('Open Twitch ↗', 'Открыть Twitch ↗'))
        self.create_help.setText(self.text('Create a bot in Telegram\n\nOpen the verified BotFather account. Send /newbot and follow its instructions. BotFather gives you a token: copy it, then continue below.\n\nAlready have your own bot? Continue with its token.', 'Создайте бота в Telegram\n\nОткройте проверенный аккаунт BotFather. Отправьте /newbot и следуйте его инструкциям. BotFather выдаст токен: скопируйте его и продолжите ниже.\n\nУже есть свой бот? Используйте его токен.'))
        self.botfather.setText(self.text('1. Open BotFather ↗', '1. Открыть BotFather ↗'))
        self.copy_command.setText(self.text('Copy /newbot command', 'Копировать команду /newbot'))
        self.have_token.setText(self.text('2. I have a bot token →', '2. У меня есть токен бота →'))
        self.token_help.setText(self.text('Paste the token from BotFather\n\nThis token lets the app send messages through your bot. It stays on this computer. We will check the bot before continuing.', 'Вставьте токен от BotFather\n\nТокен позволяет программе отправлять сообщения через вашего бота. Он хранится на этом компьютере. Перед продолжением проверим бота.'))
        self.bot.setPlaceholderText(self.text('Token from BotFather', 'Токен от BotFather'))
        self.paste_token.setText(self.text('Paste token from clipboard', 'Вставить токен из буфера'))
        self.validate_bot.setText(self.text('Check bot and continue →', 'Проверить бота и продолжить →'))
        self.chat_help.setText(self.text('Activate your bot chat\n\n1. Click Open my bot.\n2. In Telegram, press Start, then send any message, such as hello.\n3. Return here and click Find my chat and send test.\n\nThe app will identify your private chat and send one test notification.', 'Активируйте чат со своим ботом\n\n1. Нажмите «Открыть моего бота».\n2. В Telegram нажмите «Старт», затем отправьте любое сообщение, например «привет».\n3. Вернитесь сюда и нажмите «Найти мой чат и отправить тест».\n\nПрограмма определит ваш личный чат и отправит одно тестовое уведомление.'))
        self.open_bot.setText(self.text('1. Open my bot ↗', '1. Открыть моего бота ↗'))
        self.test_button.setText(self.text('2. Find my chat and send test', '2. Найти мой чат и отправить тест'))
        self.manual_chat.setText(self.text('Advanced: enter the recipient Chat ID manually', 'Дополнительно: ввести Chat ID получателя вручную'))
        self.chat.setPlaceholderText('Chat ID')
        self.success_help.setText(self.text('✓ Test notification sent\n\nTelegram is ready. Click Next to review your setup.', '✓ Тестовое уведомление отправлено\n\nTelegram готов. Нажмите «Далее», чтобы проверить настройки.'))
        self.reconnect.setText(self.text('Reconnect / change Twitch account', 'Переподключить / сменить аккаунт Twitch'))
        self.change_telegram.setText(self.text('Set up / change Telegram', 'Настроить / изменить Telegram'))
        self.back_button.setText(self.text('Back', 'Назад'))
        self.skip_telegram.setText(self.text('Skip Telegram', 'Пропустить Telegram'))
        self.cancel_button.setText(self.text('Close', 'Закрыть') if self.review_mode else self.text('Set up later', 'Настроить позже'))
        self.save_button.setText(self.text('Save changes', 'Сохранить изменения') if self.review_mode else self.text('Save and start', 'Сохранить и начать'))
        self.update_navigation()

    def twitch_ready(self):
        return self.saved_twitch or bool(self.token_update and self.token_update.get('access_token'))

    def summary(self):
        twitch = self.text('✓ Twitch: connection saved', '✓ Twitch: подключение сохранено') if self.twitch_ready() else self.text('○ Twitch: not connected', '○ Twitch: не подключён')
        if self.telegram_verified:
            telegram = self.text('✓ Telegram: test delivered', '✓ Telegram: тест доставлен')
        elif self.bot.text().strip() and self.chat.text().strip():
            telegram = self.text('✓ Telegram: recipient saved', '✓ Telegram: получатель сохранён')
        else:
            telegram = self.text('○ Telegram: skipped (optional)', '○ Telegram: пропущен (необязательно)')
        return twitch + '\n\n' + telegram

    def update_navigation(self):
        index = self.pages.currentIndex()
        names = self.text(['Language', 'Twitch', 'Telegram (optional)', 'Review setup', 'Manage connections'], ['Язык', 'Twitch', 'Telegram (необязательно)', 'Проверка настроек', 'Управление подключениями'])
        self.progress.setText(names[4] if index == 4 else self.text('Step ', 'Шаг ') + str(index + 1) + ' / 4 — ' + names[index])
        if index == 2:
            self.telegram_intro.setText(self.text('Telegram — step ', 'Telegram — шаг ') + str(self.telegram_pages.currentIndex() + 1) + ' / 4')
        self.review_summary.setText(self.text('Your saved connections\n\n', 'Сохранённые подключения\n\n') + self.summary() + self.text('\n\nNo need to repeat setup. Change only the service you need. Saved does not mean a live connection check has just run.', '\n\nПовторять настройку не нужно. Меняйте только нужный сервис. Сохранённое подключение не означает, что сейчас выполнена проверка связи.'))
        self.ready.setText(self.summary() + self.text('\n\nSave your changes. Add streamers in the main window using a Twitch username or channel URL.', '\n\nСохраните изменения. Добавляйте стримеров в главном окне по логину или ссылке Twitch.'))
        self.back_button.setVisible(index in (1, 2, 3))
        self.next_button.setVisible(index in (0, 1) or index == 2 and self.telegram_pages.currentIndex() == 3)
        self.next_button.setText(self.text('Skip Twitch for now', 'Пропустить Twitch') if index == 1 and not self.twitch_ready() else self.text('Next', 'Далее'))
        self.skip_telegram.setVisible(index == 2 and self.telegram_pages.currentIndex() != 3)
        self.save_button.setVisible(index in (3, 4))

    def change_page(self, direction):
        if self.review_mode and direction > 0 and self.pages.currentIndex() in (1, 2):
            self.pages.setCurrentIndex(4)
        else:
            self.pages.setCurrentIndex(max(0, min(3, self.pages.currentIndex() + direction)))
        self.update_navigation()

    def go_back(self):
        if self.pages.currentIndex() == 2 and self.telegram_pages.currentIndex() > 0:
            self.set_telegram_step(self.telegram_pages.currentIndex() - 1)
        elif self.review_mode:
            self.pages.setCurrentIndex(4)
            self.update_navigation()
        else:
            self.change_page(-1)

    def edit_service(self, page):
        self.pages.setCurrentIndex(page)
        self.update_navigation()

    def edit_telegram(self):
        self.set_telegram_step(1 if self.bot.text().strip() else 0)
        self.edit_service(2)

    def set_telegram_step(self, step):
        self.telegram_pages.setCurrentIndex(step)
        self.telegram_status.clear()
        self.update_navigation()

    def skip_telegram_step(self):
        self.bot.clear()
        self.chat.clear()
        self.telegram_verified = False
        self.pages.setCurrentIndex(4 if self.review_mode else 3)
        self.update_navigation()

    def token_edited(self):
        self.bot_username = ''
        self.chat.clear()
        self.telegram_verified = False

    def paste_bot_token(self):
        self.bot.setText(QApplication.clipboard().text().strip())
        self.token_edited()

    def copy_code(self):
        if self.device:
            QApplication.clipboard().setText(self.device['user_code'])
            self.copy_button.setText(self.text('Copied ✓', 'Скопировано ✓'))

    def run(self, kind, function):
        if self.busy:
            return
        self.busy = True
        for widget in (self.connect_button, self.validate_bot, self.test_button, self.save_button, self.next_button, self.back_button, self.skip_telegram, self.bot, self.chat, self.paste_token):
            widget.setEnabled(False)
        def work():
            try:
                value = function()
            except Exception as exc:
                value = exc
            if not self.cancelled.is_set():
                self.results.done.emit(kind, value)
        threading.Thread(target=work, daemon=True).start()

    def completed(self, kind, value):
        self.busy = False
        for widget in (self.connect_button, self.validate_bot, self.test_button, self.save_button, self.next_button, self.back_button, self.skip_telegram, self.bot, self.chat, self.paste_token):
            widget.setEnabled(True)
        if isinstance(value, Exception):
            target = self.telegram_status if kind in ('bot', 'telegram') else self.status
            if isinstance(value, ValueError) and str(value) == 'chat_missing':
                target.setText(self.text('Your chat was not found. Click Open my bot, press Start and send a new message. Return and retry. If this bot is used by another notifier, quit that notifier first.', 'Чат не найден. Нажмите «Открыть моего бота», затем «Старт» и отправьте новое сообщение. Вернитесь и повторите тест. Если бот используется другим уведомителем, сначала закройте его.'))
            else:
                target.setText(self.text('Could not connect. Check your internet connection and the entered token, then retry.', 'Не удалось подключиться. Проверьте интернет и введённый токен, затем повторите попытку.'))
            return
        if kind == 'device':
            self.device = value
            self.device_deadline = time.monotonic() + value['expires_in']
            self.poll_interval = max(5, value.get('interval', 5))
            self.code_label.setText(value['user_code'])
            self.code_row.show()
            self.status.setText(self.text('Copy the code, open Twitch, approve, then return here. Waiting for approval…', 'Скопируйте код, откройте Twitch, подтвердите и вернитесь сюда. Ожидаем подтверждение…'))
            self.connect_button.setEnabled(False)
            QTimer.singleShot(self.poll_interval * 1000, self.poll)
        elif kind == 'poll':
            if value is None or value.get('slow_down'):
                if value:
                    self.poll_interval += 5
                self.connect_button.setEnabled(False)
                QTimer.singleShot(self.poll_interval * 1000, self.poll)
            else:
                self.token_update = value
                self.status.setText(self.text('✓ Twitch connected. Click Next to continue.', '✓ Twitch подключён. Нажмите «Далее».'))
                self.code_row.hide()
        elif kind == 'bot':
            self.bot_username = value
            self.set_telegram_step(2)
        elif kind == 'telegram':
            self.chat.setText(value)
            self.telegram_verified = True
            self.set_telegram_step(3)
        self.update_navigation()

    def connect_twitch(self):
        self.status.setText(self.text('Getting a sign-in code…', 'Получаем код входа…'))
        self.run('device', lambda: begin_sign_in(PUBLIC_CLIENT_ID))

    def poll(self):
        if self.cancelled.is_set():
            return
        if self.busy:
            QTimer.singleShot(1000, self.poll)
            return
        if time.monotonic() > self.device_deadline:
            self.connect_button.setEnabled(True)
            self.code_row.hide()
            self.status.setText(self.text('Code expired. Get a new sign-in code.', 'Код истёк. Получите новый код входа.'))
            return
        code = self.device['device_code']
        self.run('poll', lambda: poll_sign_in(PUBLIC_CLIENT_ID, code))

    def check_bot(self):
        token = self.bot.text().strip()
        if ':' not in token:
            self.telegram_status.setText(self.text('Paste the full token from BotFather first.', 'Сначала вставьте полный токен от BotFather.'))
            return
        self.telegram_status.setText(self.text('Checking your bot…', 'Проверяем бота…'))
        def check():
            data = requests.get('https://api.telegram.org/bot' + token + '/getMe', timeout=12).json()
            username = data.get('result', {}).get('username', '')
            if not data.get('ok') or not re.fullmatch('[A-Za-z0-9_]+', username):
                raise ValueError('invalid_bot')
            return username
        self.run('bot', check)

    def open_telegram_bot(self):
        if self.bot_username:
            webbrowser.open('https://t.me/' + self.bot_username)

    def test_telegram(self):
        token = self.bot.text().strip()
        chat = self.chat.text().strip() if self.manual_chat.isChecked() else self.original.get('telegram_chat_id', '') if token == self.original.get('telegram_bot_token') else ''
        self.telegram_status.setText(self.text('Finding your chat and sending a test…', 'Ищем чат и отправляем тест…'))
        def test():
            target = chat
            if not target:
                data = requests.get('https://api.telegram.org/bot' + token + '/getUpdates', timeout=12).json()
                chats = {str(x['message']['chat']['id']) for x in data.get('result', []) if x.get('message', {}).get('chat', {}).get('type') == 'private'}
                if not data.get('ok') or len(chats) != 1:
                    raise ValueError('chat_missing')
                target = chats.pop()
            data = requests.post('https://api.telegram.org/bot' + token + '/sendMessage', data={'chat_id': target, 'text': 'Dexty Twitch Notifier — Test / Проверка'}, timeout=12).json()
            if not data.get('ok'):
                raise ValueError('send_failed')
            return target
        self.run('telegram', test)

    def save(self):
        bot, chat = self.bot.text().strip(), self.chat.text().strip()
        if bool(bot) != bool(chat):
            self.edit_telegram()
            self.telegram_status.setText(self.text('Complete the Telegram test or choose Skip Telegram.', 'Завершите тест Telegram или выберите «Пропустить Telegram».'))
            return
        self.values = {'twitch_client_id': PUBLIC_CLIENT_ID, 'twitch_client_secret': '', 'telegram_bot_token': bot, 'telegram_chat_id': chat}
        self.language_changed = i18n.LANGUAGE != self.language.currentData()
        i18n.set_language(self.language.currentData())
        self.accept()

    def done(self, result):
        self.cancelled.set()
        super().done(result)
