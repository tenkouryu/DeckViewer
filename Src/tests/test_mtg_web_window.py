import importlib.util
import unittest
from unittest.mock import patch
from urllib.request import urlopen


@unittest.skipUnless(importlib.util.find_spec("webview"), "pywebview is not installed")
class EmbeddedWindowTests(unittest.TestCase):
    def test_server_lifecycle_and_html(self):
        from mtg import mtg_web_window

        with patch.object(mtg_web_window.webview, "create_window") as create, \
             patch.object(mtg_web_window.webview, "start") as start:
            def check_page(**kwargs):
                url = create.call_args.args[1]
                with urlopen(url, timeout=5) as response:
                    self.assertIn(b"MTG Deck Viewer", response.read())
                self.assertEqual(kwargs["gui"], "edgechromium")
                self.assertTrue(mtg_web_window.webview.settings["ALLOW_DOWNLOADS"])

            start.side_effect = check_page
            mtg_web_window.main()
            url = create.call_args.args[1]
            with self.assertRaises(OSError):
                urlopen(url, timeout=2)
