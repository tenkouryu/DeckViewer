"""Display the existing web deck viewer in an embedded Windows window."""

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import webview

from .mtg_deck_viewer import DeckViewerHandler, HOST


class EmbeddedDeckViewerHandler(DeckViewerHandler):
    page_path = (
        Path(sys._MEIPASS) / "mtg_deck_viewer.html"
        if getattr(sys, "frozen", False)
        else DeckViewerHandler.page_path
    )


def main() -> None:
    server = ThreadingHTTPServer((HOST, 0), EmbeddedDeckViewerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
        url = f"http://{HOST}:{server.server_port}/"
        webview.create_window("MTG Deck Viewer - HTML版", url, width=1100, height=850, min_size=(600, 450))
        webview.start(gui="edgechromium")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
