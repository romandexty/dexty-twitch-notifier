# Build only on macOS, using the runner's native CPU architecture.
a = Analysis(['twitch_notifier_gui.pyw'], pathex=[], binaries=[],
             datas=[('icon_DextyTwitchNotif.png', '.'), ('LICENSE', '.'),
                    ('ThirdPartyNotices', 'ThirdPartyNotices')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DextyTwitchNotifier',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DextyTwitchNotifier')
app = BUNDLE(coll, name='Dexty Twitch Notifier.app', icon='build/Dexty.icns',
             bundle_identifier='me.dexty.twitch-notifier', version='1.0.1',
             info_plist={'CFBundleShortVersionString': '1.0.1',
                         'LSMinimumSystemVersion': '15.0',
                         'LSUIElement': True,
                         'NSHighResolutionCapable': True})
