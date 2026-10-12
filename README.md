# Dexty Twitch Notifier

A compact Windows tray app for following Twitch streams, with optional Telegram notifications.

[Русский](README.ru.md) · [Installation and setup](USER_GUIDE.md)

## Status

**1.0.0** — available for Windows 10 and 11 (64-bit).

[**Download the Windows installer**](https://github.com/romandexty/dexty-twitch-notifier/releases/download/v1.0.0/Dexty_Twitch_Notifier_Setup_v1.0.0.exe)

Python is not required. Install the app, then follow the guided Twitch and optional Telegram setup.

## Screenshots
<img width="389" height="616" alt="shot_261012_172340" src="https://github.com/user-attachments/assets/94a6b720-67ed-4b02-a4dc-9507ec549d1d" />
<img width="910" height="629" alt="shot_261012_172346" src="https://github.com/user-attachments/assets/89a0e70e-98e3-4364-85f8-24d42badb593" />

## Features

- English and Russian setup and interface.
- Browser-based Twitch sign-in. Users do not need developer credentials.
- Add Twitch usernames or channel links; live channels appear first.
- Click a channel row to open Twitch.
- Compact tray popup, manual refresh, pause and editable streamer list.
- Optional Telegram notifications using your own bot, with a test button and private Chat ID discovery.
- Optional Windows startup; closing the window keeps the app in the tray. Use **Quit** to exit.

## Install

Use the Windows installer attached to the project's release. Python is not needed. The installer lets you choose English or Russian; choose the app language in its setup screen as well.

The installer defaults to Program Files and requests administrator permission. Settings are stored separately for each Windows user.

## Development

Python 3.12, PySide6 / Qt and requests. Install `requirements.txt`, then run `python twitch_notifier_gui.pyw`. Run `python -m unittest test_release -v` for focused offline checks. On Windows, run `BUILD.ps1` to produce the executable and bilingual installer. Inno Setup 6 must be installed for installer compilation.

The Public Twitch Client ID identifies this app; it is safe to distribute. No client secret is used. Twitch sign-in uses the device authorization flow with no requested email scope. The public stream and user endpoints are polled in batches of up to 100 channels.

## Local data and privacy

Settings and personal connection tokens are stored locally in `%LOCALAPPDATA%\DextyTwitchNotifier`. These JSON files are not encrypted by the app. Do not share them or include them in screenshots, bug reports or GitHub uploads. The app communicates with Twitch and, when enabled, Telegram. Telegram bot tokens belong to the individual user. No analytics are implemented.

Removing the app leaves its settings available for reinstalling. To erase them, quit the app and delete only the `DextyTwitchNotifier` data folder.

## Project background

Created by Dexty to solve a personal workflow need. Product direction, interaction choices and iterative testing by Dexty; implementation developed with AI assistance.

This is an independent project and is not affiliated with Twitch or Telegram.

## Licensing

The author's source license has not yet been selected. Source visibility alone does not grant permission to redistribute or modify the author's code. Third-party components retain their own licenses; see `ThirdPartyNotices`. PySide6 / Qt are distributed as separate libraries. Retain their notices and applicable LGPL rights when distributing the app.




