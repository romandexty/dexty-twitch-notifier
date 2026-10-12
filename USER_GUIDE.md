# First launch / Первый запуск

## English

1. Run the installer and choose your installation language.
2. Open **Dexty Twitch Notifier** from the Start menu.
3. Choose **English** or **Русский** in setup, then click **Next**.
4. Click **Get sign-in code**. A code appears in the app. Click Copy code, then Open Twitch.
5. Enter that code on Twitch, sign in and approve the connection. Wait for the app to show **Twitch connected**. You never enter your Twitch password into this app.
6. Click **Next** after Twitch connects. On the Telegram step, choose **Skip Telegram** or follow the Telegram steps below.
7. Continue to the final step and click **Save and open app**. The app restarts to apply your settings.
8. Paste a Twitch username or channel URL into the main window and click **+ Add**. A successful check changes the Twitch status to connected and updates the last-check time. “Offline” alone is not proof that an entered username exists.
9. Close the window to keep monitoring in the tray. Single-click the tray icon for the compact popup; double-click for the main window. Right-click → **Quit** stops the app.

### Optional Telegram

1. Click **BotFather**, or open the verified `@BotFather` account in Telegram.
2. Send `/newbot` and follow its instructions. Copy the bot token into the app's **Bot Token** field.
3. Click **I have a bot token**, paste the token, then click **Check bot and continue**. Next click **Open my bot**, press **Start** in Telegram and send a message.
4. Leave **Chat ID** empty and click **Find my chat and send test**. This explicitly sends one test message. If exactly one private chat appears in the bot's recent updates, the app fills in Chat ID.
5. If discovery fails, send the bot another message and retry. A bot already used by another polling app or a webhook may need a separate dedicated bot. If several chats are found, enter your intended Chat ID explicitly; the app will not guess.
6. Save. Telegram is enabled when both fields are present. The main-window checkbox can disable it later.

### Troubleshooting

- Expired Twitch code: click Connect again. A revoked or expired session requires reconnecting in **Manage connections** (or **Set up**).
- Twitch reconnecting: check your internet connection. An API failure must not be interpreted as all channels being offline.
- Telegram errors: confirm you pressed Start in the correct bot, used its current token and entered the intended Chat ID.
- Language: open **Manage connections** (or **Set up**), choose your language and save; the app restarts.
- Window closed: look in Windows' hidden tray icons. Use the tray menu to quit completely.

## Русский

1. Запустите установщик версии 1.0.0 и выберите язык установки.
2. Откройте **Dexty Twitch Notifier** через меню «Пуск».
3. Выберите язык программы на экране настройки и нажмите «Далее».
4. Нажмите **«Получить код входа»**, затем «Копировать код» и «Открыть Twitch».
5. Введите код на Twitch, войдите и подтвердите подключение. Дождитесь надписи **«Twitch подключён»** в программе. Пароль Twitch вводится только на сайте Twitch.
6. После подключения Twitch нажмите «Далее». Подключите Telegram или выберите «Пропустить Telegram».
7. На последнем шаге нажмите **«Сохранить и открыть программу»**. Программа перезапустится, чтобы применить настройки.
8. Добавьте логин или ссылку на канал через **«+ Добавить»**. Успешное подключение видно по статусу Twitch и времени последней проверки. Надпись «Не в эфире» сама по себе не подтверждает существование логина.
9. Закрытие окна оставляет программу в трее. Один клик по значку открывает компактное окно, двойной — главное. Правый клик → **«Выход»** завершает программу.

### Telegram — по желанию

1. Откройте проверенный аккаунт `@BotFather`, отправьте `/newbot` и создайте бота.
2. Вставьте полученный токен в **Bot Token**.
3. Нажмите «У меня есть токен бота», вставьте токен и нажмите «Проверить бота и продолжить». Затем откройте бота кнопкой, нажмите «Старт» в Telegram и отправьте сообщение.
4. Оставьте **Chat ID** пустым и нажмите **«Найти мой чат и отправить тест»**. Кнопка отправляет одно тестовое сообщение. Если программа видит единственный личный чат в последних обновлениях бота, Chat ID заполнится автоматически.
5. Если чат не найден, отправьте боту ещё одно сообщение и повторите тест. Лучше использовать отдельного бота для этой программы. Если найдено несколько чатов, укажите нужный Chat ID самостоятельно.
6. Сохраните настройки. Telegram включится, если заполнены оба поля. Позже его можно отключить галочкой в главном окне.

Если код Twitch истёк, подключитесь заново. Для смены языка откройте «Управление подключениями» или «Настроить», выберите язык и сохраните. Ошибка Twitch означает проблему подключения, а не обязательно отсутствие стримов.




## Updates / Обновления

Click Updates in the main window to check GitHub for the latest stable release. Open download page opens GitHub in your browser. Install updates over the existing version to retain settings.

Нажмите «Обновления» в главном окне для проверки последнего стабильного релиза на GitHub. «Открыть страницу загрузки» открывает GitHub в браузере. Устанавливайте обновление поверх текущей версии, чтобы сохранить настройки.

When removing a channel, select Don’t ask again and confirm removal to skip future confirmations. Cancelling does not save this preference.

При удалении канала отметьте «Больше не спрашивать» и подтвердите удаление, чтобы отключить последующие подтверждения. При отмене эта настройка не сохраняется.
