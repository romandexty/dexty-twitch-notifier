import asyncio
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
import i18n
from public_twitch import PublicTwitch, SignInRequired, PUBLIC_CLIENT_ID, begin_sign_in
from setup_ui import SetupDialog

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from PySide6.QtGui import QFontDatabase
        if sys.platform == 'win32':
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        loader = importlib.machinery.SourceFileLoader('notifier', str(Path(__file__).with_name('twitch_notifier_gui.pyw')))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.module = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.module)

    def test_bilingual_interface_and_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            self.module.DATA_DIR = folder
            self.module.CONFIG_FILE = str(Path(folder) / 'config.json')
            for language in ('en', 'ru'):
                i18n.LANGUAGE = language
                config = self.module.ConfigManager()
                self.assertEqual(config.streamers(), [])
                self.assertFalse(config.get('telegram_notifications'))
                window = self.module.MainWindow(config)
                window.show()
                self.app.processEvents()
                self.assertEqual(window.edit_btn.text(), 'Edit list' if language == 'en' else 'Редактировать список')
                setup = SetupDialog(folder, window)
                setup.show()
                self.app.processEvents()
                self.assertFalse(setup.client.isVisible())
                for page in range(4):
                    setup.pages.setCurrentIndex(page)
                    setup.update_navigation()
                    self.app.processEvents()
                    setup.grab().save(str(Path(os.environ['DEXTY_DATA_DIR']).parent / ('setup-' + language + '-' + str(page) + '.png')))
                setup.skip_telegram_step()
                self.assertEqual(setup.bot.text(), '')
                self.assertEqual(setup.chat.text(), '')
                setup.reject()
                ok, error = config.add_streamer('https://www.twitch.tv/example_name?foo=bar')
                self.assertTrue(ok, error)
                self.assertEqual(config.streamers(), ['example_name'])
                self.assertFalse(config.add_streamer('bad/name')[0])
                config.set('streamers', [])
                window.exiting = True
                window.close()

    def test_removal_preference_persists_only_after_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.module.DATA_DIR = folder
            self.module.CONFIG_FILE = str(Path(folder) / 'config.json')
            config = self.module.ConfigManager()
            config.set('streamers', ['one', 'two'])
            window = self.module.MainWindow(config)
            window.edit_btn.setChecked(True)
            box = self.module.QMessageBox
            def decide(dialog, remove):
                dialog.checkBox().setChecked(True)
                role = box.DestructiveRole if remove else box.RejectRole
                dialog._chosen = next(b for b in dialog.buttons() if dialog.buttonRole(b) == role)
            with patch.object(box, 'exec', lambda d: decide(d, False)), patch.object(box, 'clickedButton', lambda d: d._chosen):
                window.remove_streamer('one')
            self.assertEqual(config.streamers(), ['one', 'two'])
            self.assertTrue(config.get('confirm_channel_removal'))
            with patch.object(box, 'exec', lambda d: decide(d, True)), patch.object(box, 'clickedButton', lambda d: d._chosen):
                window.remove_streamer('one')
            self.assertEqual(config.streamers(), ['two'])
            self.assertFalse(self.module.ConfigManager().get('confirm_channel_removal'))
            with patch.object(box, 'exec', side_effect=AssertionError('Unexpected confirmation')):
                window.remove_streamer('two')
            self.assertEqual(config.streamers(), [])
            window.exiting = True
            window.close()

    def test_update_popup_states_and_release_validation(self):
        import updates_ui
        with patch.object(updates_ui.UpdatesDialog, 'start_check'):
            for language in ('en', 'ru'):
                i18n.LANGUAGE = language
                dialog = updates_ui.UpdatesDialog()
                for version, success in [('1.0.1', True), ('1.0.2', True), ('1.0.0', True), ('', False)]:
                    dialog.show_result(version, success)
                    self.assertTrue(dialog.status.text())
                    self.assertTrue(dialog.retry.isEnabled())
                    self.assertFalse(dialog.download.isHidden())
                with patch.object(updates_ui.webbrowser, 'open') as opened:
                    dialog.download.click()
                    opened.assert_called_once_with(updates_ui.RELEASES_URL)
                dialog.close()
        self.assertGreater(updates_ui.version_tuple('v1.0.10'), updates_ui.version_tuple('1.0.2'))
        with patch.object(updates_ui.requests, 'get') as get:
            get.return_value.json.return_value = {'tag_name': 'v1.0.2'}
            self.assertEqual(updates_ui.latest_version(), '1.0.2')
            get.return_value.json.return_value = {'tag_name': 'v2.0.0', 'prerelease': True}
            with self.assertRaises(ValueError):
                updates_ui.latest_version()

    def test_public_refresh_saves_rotating_token_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'token.json'
            client = PublicTwitch(PUBLIC_CLIENT_ID, path)
            client.tokens = {'access_token': 'old', 'refresh_token': 'old-refresh'}
            calls = []
            def request(method, url, **kwargs):
                calls.append(kwargs)
                return {'access_token': 'new', 'refresh_token': 'new-refresh'}
            client._request = request
            asyncio.run(client.refresh())
            self.assertNotIn('client_secret', calls[0]['data'])
            self.assertIn('new-refresh', path.read_text())

    def test_returning_user_reviews_without_resetting_credentials(self):
        from connections_ui import atomic_json
        with tempfile.TemporaryDirectory() as folder:
            atomic_json(Path(folder) / 'token.json', {'access_token': 'test-access', 'refresh_token': 'test-refresh'})
            atomic_json(Path(folder) / 'connections.json', {'twitch_client_id': PUBLIC_CLIENT_ID, 'telegram_bot_token': '123:test', 'telegram_chat_id': '42'})
            setup = SetupDialog(folder)
            self.assertEqual(setup.pages.currentIndex(), 4)
            self.assertTrue(setup.twitch_ready())
            setup.show()
            self.app.processEvents()
            setup.grab().save(str(Path(os.environ['DEXTY_DATA_DIR']).parent / 'review-connections.png'))
            self.assertIn('42', setup.chat.text())
            setup.device = {'user_code': 'TEST123'}
            setup.copy_code()
            self.assertEqual(QApplication.clipboard().text(), 'TEST123')
            setup.edit_service(1)
            setup.change_page(1)
            self.assertEqual(setup.pages.currentIndex(), 4)
            with patch('i18n.set_language'):
                setup.save()
            self.assertIsNone(setup.token_update)
            self.assertEqual(setup.values['telegram_bot_token'], '123:test')
            self.assertEqual(setup.values['telegram_chat_id'], '42')

    def test_telegram_steps_advance_after_validation_and_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            setup = SetupDialog(folder)
            setup.edit_telegram()
            self.assertEqual(setup.telegram_pages.currentIndex(), 0)
            setup.have_token.click()
            self.assertEqual(setup.telegram_pages.currentIndex(), 1)
            setup.completed('bot', 'test_bot')
            self.assertEqual(setup.telegram_pages.currentIndex(), 2)
            setup.completed('telegram', '42')
            self.assertEqual(setup.telegram_pages.currentIndex(), 3)
            self.assertTrue(setup.telegram_verified)
            self.assertEqual(setup.chat.text(), '42')
            setup.reject()

    def test_polling_batches_large_lists(self):
        client = PublicTwitch(PUBLIC_CLIENT_ID, 'not-a-real-file')
        client.tokens = {'access_token': 'test'}
        import time
        client.validated_at = time.monotonic()
        calls = []
        def request(method, url, **kwargs):
            calls.append(kwargs['params'])
            return {'data': []}
        client._request = request
        asyncio.run(client._get('streams', 'user_login', ['user%d' % i for i in range(205)]))
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(calls[0]), 101)

if __name__ == '__main__':
    unittest.main()
