"""Small, explicit Russian/English catalog; language changes apply on restart."""
import json
import os
from pathlib import Path

FOLDER = Path(os.environ.get('DEXTY_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'DextyTwitchNotifier')
FOLDER.mkdir(parents=True, exist_ok=True)
LANGUAGE_FILE = FOLDER / 'language.json'
try:
    LANGUAGE = json.loads(LANGUAGE_FILE.read_text(encoding='utf-8')).get('language', 'en')
except (OSError, ValueError):
    LANGUAGE = 'en'

EN = {
    'Обновления': 'Updates',
    'Установленная версия: {version}': 'Installed version: {version}',
    'Проверить обновления': 'Check for updates',
    'Открыть страницу загрузки': 'Open download page',
    'Закрыть': 'Close',
    'Проверяем последнюю версию на GitHub…': 'Checking the latest version on GitHub…',
    'Не удалось проверить обновления. Проверьте интернет или откройте страницу загрузки.': 'Could not check for updates. Check your internet connection or open the download page.',
    'Доступна новая версия: {version}. Скачайте установщик со страницы релиза.': 'New version available: {version}. Download the installer from the release page.',
    'У вас последняя версия: {version}.': 'You have the latest version: {version}.',
    'Новых обновлений нет. Последняя опубликованная версия: {version}; ваша версия новее.': 'No newer update is available. Latest published version: {version}; your installed version is newer.',

    "Больше не спрашивать": "Don’t ask again",
    'Настроить': 'Set up', 'Управление подключениями': 'Manage connections',
    'Завершить настройку': 'Finish setup', 'Настройки': 'Settings',
    'Введите Twitch-логин.': 'Enter a Twitch username.',
    'В Twitch-логине не должно быть пробелов.': 'A Twitch username cannot contain spaces.',
    'Этот стример уже есть в списке.': 'This streamer is already in your list.',
    '✅ Twitch Notifier запущен!': '✅ Twitch Notifier is running!',
    'Обновить': 'Refresh', 'Управление стримерами': 'Manage streamers',
    'Пауза': 'Paused', 'Список стримеров пуст': 'Your list is empty. Add a Twitch username to begin.',
    'Dexty Twitch Notifier — Личный мониторинг стримов Twitch': 'Dexty Twitch Notifier — Your Twitch stream monitor',
    'Добавление стримера': 'Add a streamer',
    'Twitch-логин, например dima_wallhacks': 'Twitch username or channel URL',
    '+ Добавить': '+ Add', 'Статус': 'Status', 'Стример': 'Streamer', 'Стрим': 'Stream',
    'Уведомления в Telegram': 'Telegram notifications',
    'Запускать вместе с Windows': 'Start with Windows',
    'Пауза мониторинга': 'Pause monitoring', 'Обновить сейчас': 'Refresh now',
    'Редактировать список': 'Edit list', 'Подключения': 'Setup / Language',
    'Twitch API: подключение…': 'Twitch API: connecting…',
    'Telegram: подключение…': 'Telegram: connecting…',
    'Последняя проверка: —': 'Last checked: —',
    'Удалить стримера?': 'Remove streamer?',
    'Его можно будет снова добавить по Twitch-логину.': 'You can add this streamer again using their Twitch username.',
    'Удалить': 'Remove', 'Отмена': 'Cancel', 'Не в эфире': 'Offline',
    'Twitch API: ● не настроено': 'Twitch API: ● setup needed',
    'Twitch API: ● подключено': 'Twitch API: ● connected',
    'Twitch API: ◐ подключение…': 'Twitch API: ◐ connecting…',
    'Twitch API: ● ошибка, переподключение…': 'Twitch API: ● reconnecting…',
    'Telegram: ● не настроено': 'Telegram: ● setup needed',
    'Telegram: ○ выключено': 'Telegram: ○ off', 'Telegram: ● настроено': 'Telegram: ● configured',
    'Telegram: ● подключено': 'Telegram: ● connected',
    'Telegram: ◐ подключение…': 'Telegram: ◐ connecting…', 'Telegram: ● ошибка': 'Telegram: ● error',
    'Открыть Twitch Notifier': 'Open Twitch Notifier', 'Telegram уведомления': 'Telegram notifications',
    'Выход': 'Quit', 'Dexty Twitch Notifier — пауза': 'Dexty Twitch Notifier — paused',
    'Dexty Twitch Notifier — никто не стримит': 'Dexty Twitch Notifier — no live streams',
    'Не удалось сохранить': 'Could not save',
    'Проверьте доступ к папке настроек и свободное место на диске.': 'Check access to your settings folder and available disk space.',
    'Не удалось открыть локальный канал программы.': 'Could not open the local application channel.',
    'Удалить {login} из списка?': 'Remove {login} from your list?',
    'Последняя проверка: {value}': 'Last checked: {value}',
    'Онлайн: {names}': 'Live: {names}',
    '{hours}ч {mins:02d}м': '{hours}h {mins:02d}m', '{mins}м': '{mins}m',
    '🟢 [Уже в эфире] {name} сейчас стримит!\n': '🟢 [Already live] {name} is streaming!\n',
    '🔥 {name} запустил стрим!\n': '🔥 {name} just went live!\n',
}

def tr(text):
    return EN.get(text, text) if LANGUAGE == 'en' else text

def choose(english, russian):
    return english if LANGUAGE == 'en' else russian

def set_language(language):
    global LANGUAGE
    LANGUAGE = language if language in ('en', 'ru') else 'en'
    tmp = LANGUAGE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'language': LANGUAGE}), encoding='utf-8')
    os.replace(tmp, LANGUAGE_FILE)
