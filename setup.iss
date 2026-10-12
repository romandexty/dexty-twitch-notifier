#define AppName "Dexty Twitch Notifier"
[Setup]
AppId={{1FE13B26-89D6-48F2-B71D-BDCEFD367D93}
AppName={#AppName}
AppVersion=1.0.1
AppPublisher=Dexty
DefaultDirName={autopf}\Dexty Twitch Notifier
DefaultGroupName={#AppName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=output
OutputBaseFilename=Dexty_Twitch_Notifier_Setup_v1.0.1
SetupIconFile=Dexty.ico
UninstallDisplayIcon={app}\DextyTwitchNotifier.exe
AppMutex=Local\DextyTwitchNotifier
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[CustomMessages]
english.DesktopIcon=Create a desktop shortcut
russian.DesktopIcon=Создать ярлык на рабочем столе
english.Launch=Launch app and set up connections
russian.Launch=Открыть программу и настроить подключения
[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked
[Files]
Source: "dist\DextyTwitchNotifier\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{commonprograms}\{#AppName}"; Filename: "{app}\DextyTwitchNotifier.exe"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\DextyTwitchNotifier.exe"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "DextyTwitchNotifier"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\DextyTwitchNotifier.exe"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent runasoriginaluser





[Messages]
english.FinishedLabel=Installation is complete. Next: launch the app to connect Twitch and optionally Telegram. You can choose Set up later. Existing connections are kept when updating.
russian.FinishedLabel=Установка завершена. Далее: откройте программу, чтобы подключить Twitch и, по желанию, Telegram. Можно выбрать «Настроить позже». При обновлении сохранённые подключения остаются.


