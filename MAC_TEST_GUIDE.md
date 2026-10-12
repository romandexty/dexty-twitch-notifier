# macOS 1.0.1 preview — testing only

Separate Apple Silicon (arm64) and Intel (x86_64) builds. Requires macOS 15 or later. No Python installation is needed.

## Install

1. Download the DMG for your processor. Apple menu > About This Mac shows Apple M-series (arm64) or Intel (x86_64).
2. Open the DMG and drag Dexty Twitch Notifier into Applications.
3. Eject the disk image, then open the application from Applications.
4. Complete the English/Russian guide, sign in on Twitch, optionally connect Telegram and add channels.

This preview is ad-hoc signed for local integrity but is NOT Developer ID signed or notarized. macOS may block a downloaded build. Do not disable Gatekeeper or remove quarantine attributes. Stop and report the message; a normal public release needs signing/notarization or an approved tester opening it through macOS security settings.

The menu-bar icon opens a menu. Choose Open Twitch Notifier for the main window or Open stream popup for the compact list. Closing a window keeps monitoring; Quit exits completely. Start at login works after installation in Applications and takes effect at your next login.

Settings and tokens: `~/Library/Application Support/DextyTwitchNotifier`. Keep them private. Login-startup file: `~/Library/LaunchAgents/me.dexty.twitch-notifier.plist`. Disable Start at login before removing the app. No credentials are included in the download.

## Test checklist

- First launch, English/Russian setup, Twitch sign-in and reconnect after restart.
- Add live/offline channels; browser links, refresh, pause and list removal.
- Cancel removal, confirm removal and Don’t ask again across relaunches.
- Menu-bar main window and stream popup, hide/reopen and Quit.
- Launch a second copy: it should open the existing instance.
- Telegram test and a real stream-start alert; macOS notification permissions where offered.
- Updates popup, download link and disconnected-network error.
- Start at login, logout/login, then disable startup and verify at the next login.
- Retina scaling, long stream titles and both app languages.

No macOS end-user testing has been completed yet. The current GitHub stable release remains the Windows build; the Updates popup shows its version and release page. Mac-specific public downloads will be added only after testing.
