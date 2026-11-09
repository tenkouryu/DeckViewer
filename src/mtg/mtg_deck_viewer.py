#!/usr/bin/env python3
"""Serve a local deck-list viewer backed by Scryfall."""

import argparse
import json
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .mtg_card_search import fetch_cards_by_identifiers


HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 512 * 1024
MAX_UNIQUE_CARDS = 300
QUANTITY_PREFIX = re.compile(r"^(?:(\d+)\s*x?\s+)?(.+?)$")
PRINTING_SUFFIX = re.compile(
    r"\s+(?:\((?P<set_paren>[A-Za-z0-9]{2,6})\)|"
    r"\[(?P<set_bracket>[A-Za-z0-9]{2,6})\])"
    r"\s+(?P<collector>\S+)(?:\s+\*[^*\r\n]+\*)?$"
)
SECTION_HEADERS = {
    "deck": "Mainboard",
    "mainboard": "Mainboard",
    "デッキ": "Mainboard",
    "メインボード": "Mainboard",
    "sideboard": "Sideboard",
    "サイドボード": "Sideboard",
    "commander": "Commander",
    "統率者": "Commander",
    "companion": "Companion",
    "相棒": "Companion",
}


def parse_decklist(text: str) -> list[dict]:
    cards = []
    positions = {}
    section = "Mainboard"
    in_metadata = False

    for line_number, raw_line in enumerate(text.removeprefix("\ufeff").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        header = line.rstrip(":：").strip().casefold()
        if header == "about":
            in_metadata = True
            continue
        if header in SECTION_HEADERS:
            section = SECTION_HEADERS[header]
            in_metadata = False
            continue
        if in_metadata:
            continue

        match = QUANTITY_PREFIX.fullmatch(line)
        if not match:
            continue
        quantity = int(match.group(1) or "1")
        raw_name = match.group(2).strip()
        printing = PRINTING_SUFFIX.search(raw_name)
        name = raw_name[: printing.start()].strip() if printing else raw_name
        if not name or quantity < 1:
            continue
        set_code = (
            (printing.group("set_paren") or printing.group("set_bracket")).casefold()
            if printing
            else None
        )
        collector_number = printing.group("collector") if printing else None

        key = (section, name.casefold(), set_code, collector_number)
        if key in positions:
            cards[positions[key]]["quantity"] += quantity
        else:
            positions[key] = len(cards)
            cards.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "section": section,
                    "line": line_number,
                    "set": set_code,
                    "collector_number": collector_number,
                }
            )

    if len(cards) > MAX_UNIQUE_CARDS:
        raise ValueError(f"Please limit a deck list to {MAX_UNIQUE_CARDS} unique cards.")
    return cards


def resolve_deck(cards: list[dict]) -> list[dict]:
    identifiers_by_key = {}
    for entry in cards:
        if entry["set"] and entry["collector_number"]:
            key = ("printing", entry["set"], entry["collector_number"].casefold())
            identifier = {
                "set": entry["set"],
                "collector_number": entry["collector_number"],
            }
        else:
            key = ("name", entry["name"].casefold())
            identifier = {"name": entry["name"]}
        identifiers_by_key.setdefault(key, identifier)
    cards_by_identifier = fetch_cards_by_identifiers(list(identifiers_by_key.values()))
    fallback_names = {}
    for entry in cards:
        if (
            entry["set"]
            and entry["collector_number"]
            and (
                "printing",
                entry["set"],
                entry["collector_number"].casefold(),
            ) not in cards_by_identifier
        ):
            fallback_names.setdefault(entry["name"].casefold(), entry["name"])
    fallback_cards = (
        fetch_cards_by_identifiers([{"name": name} for name in fallback_names.values()])
        if fallback_names
        else {}
    )
    results = []
    for entry in cards:
        if entry["set"] and entry["collector_number"]:
            key = ("printing", entry["set"], entry["collector_number"].casefold())
        else:
            key = ("name", entry["name"].casefold())
        card = cards_by_identifier.get(key)
        if not card and entry["set"] and entry["collector_number"]:
            card = fallback_cards.get(("name", entry["name"].casefold()))
        results.append(
            {
                **entry,
                "card": card,
                "error": None if card else "Card not found in Scryfall.",
                "notice": None,
            }
        )
    return results


class DeckViewerHandler(BaseHTTPRequestHandler):
    page_path = Path(__file__).resolve().parent.parent.parent / "mtg_deck_viewer.html"

    def send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if self.path != "/":
            self.send_error(404)
            return

        try:
            body = self.page_path.read_bytes()
        except OSError as error:
            self.send_json(500, {"error": f"Could not read the app page: {error}"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/deck":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 1 or content_length > MAX_REQUEST_BYTES:
                raise ValueError("The deck-list file must be smaller than 512 KB.")
            payload = json.loads(self.rfile.read(content_length))
            text = payload.get("text") if isinstance(payload, dict) else None
            if not isinstance(text, str):
                raise ValueError("The request must contain deck-list text.")
            cards = parse_decklist(text)
            if not cards:
                raise ValueError("No cards found. Check the deck-list format.")
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
            return

        try:
            results = resolve_deck(cards)
        except (RuntimeError, KeyError) as error:
            status = 429 if "returned HTTP 429" in str(error) else 502
            self.send_json(status, {"error": str(error)})
            return

        self.send_json(200, {"cards": results})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the local MTG deck card viewer.")
    parser.add_argument("--port", type=int, default=8765, help="local web server port")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    try:
        server = ThreadingHTTPServer((HOST, args.port), DeckViewerHandler)
    except OSError as error:
        parser.exit(1, f"Could not start the local server: {error}\n")

    url = f"http://{HOST}:{server.server_port}/"
    print(f"MTG Deck Viewer: {url}\nPress Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MTG Deck Viewer.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
