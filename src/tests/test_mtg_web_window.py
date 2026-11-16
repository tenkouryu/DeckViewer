import importlib.util
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.request import urlopen


@unittest.skipUnless(importlib.util.find_spec("webview"), "pywebview is not installed")
class EmbeddedWindowTests(unittest.TestCase):
    def test_preview_client_size_matches_card_ratio(self):
        from mtg import mtg_web_window

        native = MagicMock()
        native.DeviceDpi = 144
        native.Invoke.side_effect = lambda callback: callback()
        modules = {
            "System": SimpleNamespace(Action=lambda callback: callback),
            "System.Drawing": SimpleNamespace(Size=lambda width, height: (width, height)),
        }
        with patch.dict(sys.modules, modules):
            mtg_web_window.fit_preview_window(SimpleNamespace(native=native))

        self.assertEqual(native.ClientSize, (540, 753))

    def test_clipboard_operations_run_on_ui_thread(self):
        from mtg import mtg_web_window

        class Func:
            def __class_getitem__(cls, item):
                return lambda callback: callback

        clipboard = MagicMock()
        clipboard.GetText.return_value = "copied text"
        native = MagicMock()
        native.Invoke.side_effect = lambda callback: callback()
        api = mtg_web_window.ClipboardApi("http://127.0.0.1/preview")
        api._window = SimpleNamespace(native=native)

        modules = {
            "System": SimpleNamespace(Action=lambda callback: callback, Func=Func, String=str),
            "System.Windows": SimpleNamespace(),
            "System.Windows.Forms": SimpleNamespace(Clipboard=clipboard),
        }
        with patch.dict(sys.modules, modules):
            api.write_clipboard("copied text")
            self.assertEqual(api.read_clipboard(), "copied text")

        clipboard.SetText.assert_called_once_with("copied text")
        self.assertEqual(native.Invoke.call_count, 2)

    def test_preview_window_open_update_close_and_reopen(self):
        from mtg import mtg_web_window

        api = mtg_web_window.ClipboardApi("http://127.0.0.1/preview")
        with patch.object(mtg_web_window.webview, "create_window") as create:
            preview = create.return_value
            closed = preview.events.closed
            api.open_preview()
            api.open_preview()
            create.assert_called_once()
            preview.show.assert_called_once()
            self.assertTrue(api.update_preview('A "card"', "https://cards.scryfall.io/a.jpg"))
            preview.evaluate_js.assert_called_once_with(
                'showCard({"name": "A \\"card\\"", "imageUrl": "https://cards.scryfall.io/a.jpg"})'
            )
            closed.__iadd__.call_args.args[0]()
            self.assertFalse(api.update_preview("Card", ""))
            api.open_preview()
            self.assertEqual(create.call_count, 2)

    def test_server_lifecycle_and_html(self):
        from mtg import mtg_web_window

        with patch.object(mtg_web_window.webview, "create_window") as create, \
             patch.object(mtg_web_window.webview, "start") as start:
            def check_page(**kwargs):
                url = create.call_args.args[1]
                with urlopen(url, timeout=5) as response:
                    self.assertIn(b"MTG Deck Viewer", response.read())
                with urlopen(f"{url}preview", timeout=5) as response:
                    self.assertIn(b"card-preview-ready", response.read())
                self.assertEqual(kwargs["gui"], "edgechromium")
                self.assertTrue(mtg_web_window.webview.settings["ALLOW_DOWNLOADS"])
                self.assertIs(create.call_args.kwargs["js_api"]._window, create.return_value)

            start.side_effect = check_page
            mtg_web_window.main()
            url = create.call_args.args[1]
            with self.assertRaises(OSError):
                urlopen(url, timeout=2)
