"""macOS login startup without Windows registry calls."""
from pathlib import Path
import os
import plistlib
import sys

AGENT_NAME = "me.dexty.twitch-notifier.plist"

def app_bundle(executable=None):
    for parent in Path(executable or sys.executable).resolve().parents:
        if parent.suffix == '.app':
            return parent
    return None

def set_mac_startup(enabled, home=None, executable=None):
    target = Path(home or Path.home()) / 'Library' / 'LaunchAgents' / AGENT_NAME
    try:
        if not enabled:
            target.unlink(missing_ok=True)
            return True
        bundle = app_bundle(executable)
        if bundle is None:
            return False
        # Resolve to the installed application; never save a temporary build path.
        if not (bundle.parent == Path('/Applications') or bundle.parent == Path(home or Path.home()) / 'Applications'):
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {'Label': 'me.dexty.twitch-notifier',
                'ProgramArguments': ['/usr/bin/open', '-g', str(bundle), '--args', '--background'],
                'RunAtLoad': True}
        temp = target.with_suffix('.plist.tmp')
        temp.write_bytes(plistlib.dumps(data))
        os.replace(temp, target)
        return True
    except OSError:
        return False
