"""Create a native .app and drag-to-Applications DMG on a Mac."""
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)

def main():
    if sys.platform != 'darwin':
        raise SystemExit('Run this build on macOS, or use the GitHub macOS workflow.')
    iconset = ROOT / 'build' / 'Dexty.iconset'
    iconset.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = '@2x' if scale == 2 else ''
            run('sips', '-z', size * scale, size * scale,
                ROOT / 'icon_DextyTwitchNotif.png', '--out', iconset / f'icon_{size}x{size}{suffix}.png', stdout=subprocess.DEVNULL)
    run('iconutil', '-c', 'icns', iconset, '-o', ROOT / 'build' / 'Dexty.icns')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', 'DextyTwitchNotifier-mac.spec')
    bundle = ROOT / 'dist' / 'Dexty Twitch Notifier.app'
    executable = bundle / 'Contents' / 'MacOS' / 'DextyTwitchNotifier'
    report = ROOT / 'mac-self-test.json'
    run(executable, '--self-test', report)
    result = json.loads(report.read_text())
    if result.get('ok') is not True or result.get('frozen') is not True:
        raise SystemExit('Packaged self-test failed')
    run('codesign', '--verify', '--deep', '--strict', bundle)
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    arch = platform.machine()
    dmg = output / f'Dexty_Twitch_Notifier_v1.0.1_macOS_{arch}_Preview.dmg'
    with tempfile.TemporaryDirectory(prefix='dexty-dmg-') as folder:
        stage = Path(folder)
        run('ditto', bundle, stage / bundle.name)
        (stage / 'Applications').symlink_to('/Applications')
        run('ditto', ROOT / 'MAC_TEST_GUIDE.md', stage / 'READ_ME_FIRST.md')
        run('hdiutil', 'create', '-volname', 'Dexty Twitch Notifier', '-srcfolder', stage,
            '-ov', '-format', 'UDZO', dmg)
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    (output / f'SHA256SUMS-{arch}.txt').write_text(digest + '  ' + dmg.name + '\n')
    print('Built:', dmg)

if __name__ == '__main__':
    main()
