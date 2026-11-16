"""Display the existing web deck viewer in an embedded Windows window."""

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import webview

from .mtg_deck_viewer import DeckViewerHandler, HOST


class EmbeddedDeckViewerHandler(DeckViewerHandler):
    if getattr(sys, "frozen", False):
        page_path = Path(sys._MEIPASS) / "mtg_deck_viewer.html"
        preview_page_path = Path(sys._MEIPASS) / "card_preview.html"


def fit_preview_window(window) -> None:
    from System import Action
    from System.Drawing import Size

    def fit() -> None:
        scale = window.native.DeviceDpi / 96
        window.native.ClientSize = Size(round(360 * scale), round(502 * scale))

    window.native.Invoke(Action(fit))


class ClipboardApi:
    def __init__(self, preview_url: str) -> None:
        self._window = None
        self._preview_url = preview_url
        self._preview = None
        self._preview_lock = threading.Lock()

    def read_clipboard(self) -> str:
        from System import Func, String
        from System.Windows.Forms import Clipboard

        return self._window.native.Invoke(Func[String](Clipboard.GetText))

    def write_clipboard(self, text: str) -> None:
        from System import Action
        from System.Windows.Forms import Clipboard

        self._window.native.Invoke(Action(lambda: Clipboard.SetText(text)))

    def open_preview(self) -> None:
        with self._preview_lock:
            if self._preview is not None:
                self._preview.show()
                return
            preview = webview.create_window(
                "カードプレビュー - MTG Deck Viewer", self._preview_url,
                width=376, height=540, resizable=False,
            )
            if preview is None:
                raise RuntimeError("プレビューウィンドウを作成できませんでした。")
            self._preview = preview
            preview.events.loaded += lambda: fit_preview_window(preview)
            preview.events.closed += lambda: self._clear_preview(preview)

    def _clear_preview(self, preview) -> None:
        with self._preview_lock:
            if self._preview is preview:
                self._preview = None

    def update_preview(self, name: str, image_url: str) -> bool:
        with self._preview_lock:
            preview = self._preview
        if preview is None:
            return False
        card = json.dumps({"name": name, "imageUrl": image_url}, ensure_ascii=True)
        preview.evaluate_js(f"showCard({card})")
        return True


def main() -> None:
    server = ThreadingHTTPServer((HOST, 0), EmbeddedDeckViewerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
        url = f"http://{HOST}:{server.server_port}/"
        clipboard = ClipboardApi(f"{url}preview")
        window = webview.create_window(
            "MTG Deck Viewer - HTML版", url, width=1100, height=850, min_size=(600, 450),
            js_api=clipboard,
        )
        clipboard._window = window
        webview.start(gui="edgechromium")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
