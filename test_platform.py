import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from platform_support import app_bundle, set_mac_startup, AGENT_NAME
from connections_ui import wait_for_parent

class PlatformTests(unittest.TestCase):
    def test_macos_login_plist_and_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'Applications' / 'Dexty Twitch Notifier.app'
            executable = str(bundle / 'Contents' / 'MacOS' / 'DextyTwitchNotifier')
            self.assertEqual(app_bundle(executable), bundle.resolve())
            self.assertTrue(set_mac_startup(True, home=folder, executable=executable))
            target = Path(folder) / 'Library' / 'LaunchAgents' / AGENT_NAME
            data = plistlib.loads(target.read_bytes())
            self.assertEqual(data['ProgramArguments'], ['/usr/bin/open', '-g', str(bundle.resolve()), '--args', '--background'])
            self.assertTrue(data['RunAtLoad'])
            self.assertTrue(set_mac_startup(False, home=folder))
            self.assertFalse(target.exists())
            self.assertFalse(set_mac_startup(True, home=folder, executable='/tmp/Test.app/Contents/MacOS/Test'))

    def test_posix_parent_exit(self):
        with patch('connections_ui.os.kill', side_effect=ProcessLookupError), patch('sys.platform', 'darwin'):
            wait_for_parent(12345)

    @unittest.skipIf(os.name == 'nt', 'Native POSIX socket test runs on macOS')
    def test_single_instance_and_reopen(self):
        from test_release import ReleaseTests
        ReleaseTests.setUpClass()
        module = ReleaseTests.module
        from PySide6.QtCore import QEventLoop, QTimer
        name = 'DextyTest-' + str(os.getpid())
        first = module.SingleInstance(name=name)
        received = []
        first.show_requested.connect(lambda: received.append(True))
        try:
            self.assertTrue(first.primary)
            second = module.SingleInstance(name=name)
            self.assertFalse(second.primary)
            second.close()
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            self.assertTrue(received)
        finally:
            first.close()
        reopened = module.SingleInstance(name=name)
        self.assertTrue(reopened.primary)
        reopened.close()

if __name__ == '__main__':
    unittest.main()
