#!/usr/bin/env python3
"""Search MTG cards through the Scryfall API and print selected card data as JSON."""

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


API_URL = "https://api.scryfall.com/cards/search"
COLLECTION_URL = "https://api.scryfall.com/cards/collection"
USER_AGENT = "MTGCardSearch/1.0 (Python urllib)"
COLLECTION_INTERVAL = 0.5
_collection_lock = threading.Lock()
_last_collection_request = 0.0


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def image_url(card: dict) -> str | None:
    images = card.get("image_uris")
    if images:
        return images.get("normal")

    faces = card.get("card_faces", [])
    for face in faces:
        images = face.get("image_uris")
        if images and images.get("normal"):
            return images["normal"]
    return None


def summarize_face(face: dict) -> dict:
    images = face.get("image_uris") or {}
    return {
        "name": face.get("name"),
        "type": face.get("type_line"),
        "rules_text": face.get("oracle_text"),
        "image_url": images.get("normal"),
    }


def summarize_card(card: dict) -> dict:
    result = {
        "name": card.get("name"),
        "type": card.get("type_line"),
        "rules_text": card.get("oracle_text"),
        "set": card.get("set_name"),
        "image_url": image_url(card),
    }
    if card.get("card_faces"):
        result["faces"] = [summarize_face(face) for face in card["card_faces"]]
    return result


def fetch_page(url: str) -> dict:
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "api.scryfall.com":
        raise RuntimeError("The API returned an unexpected pagination URL.")

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error).get("details", str(error))
        except (json.JSONDecodeError, AttributeError):
            detail = str(error)
        raise RuntimeError(f"Scryfall API returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not connect to the Scryfall API: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("Scryfall returned invalid JSON.") from error


def identifier_key(identifier: dict) -> tuple[str, ...]:
    if "set" in identifier and "collector_number" in identifier:
        return (
            "printing",
            str(identifier["set"]).casefold(),
            str(identifier["collector_number"]).casefold(),
        )
    return ("name", str(identifier["name"]).casefold())


def fetch_cards_by_identifiers(identifiers: list[dict]) -> dict[tuple[str, ...], dict]:
    global _last_collection_request

    cards_by_key = {}
    for offset in range(0, len(identifiers), 75):
        batch = identifiers[offset : offset + 75]
        request = Request(
            COLLECTION_URL,
            data=json.dumps(
                {"identifiers": batch}
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with _collection_lock:
                delay = COLLECTION_INTERVAL - (time.monotonic() - _last_collection_request)
                if delay > 0:
                    time.sleep(delay)
                _last_collection_request = time.monotonic()
                with urlopen(request, timeout=30) as response:
                    page = json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get("details", str(error))
            except (json.JSONDecodeError, AttributeError):
                detail = str(error)
            raise RuntimeError(
                f"Scryfall API returned HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Could not connect to the Scryfall API: {error.reason}"
            ) from error
        except json.JSONDecodeError as error:
            raise RuntimeError("Scryfall returned invalid JSON.") from error

        for card in page["data"]:
            summary = summarize_card(card)
            summary["scryfall_url"] = card.get("scryfall_uri")
            summary["set_code"] = card.get("set")
            summary["collector_number"] = card.get("collector_number")
            summary["digital"] = card.get("digital")
            aliases = [card["name"]]
            aliases.extend(face["name"] for face in card.get("card_faces", []))
            for name in aliases:
                cards_by_key[("name", name.casefold())] = summary
            if card.get("set") and card.get("collector_number"):
                cards_by_key[
                    (
                        "printing",
                        card["set"].casefold(),
                        str(card["collector_number"]).casefold(),
                    )
                ] = summary

    return cards_by_key


def fetch_cards_by_names(names: list[str]) -> dict[str, dict]:
    identifiers = [{"name": name} for name in names]
    cards = fetch_cards_by_identifiers(identifiers)
    return {
        name.casefold(): cards[identifier_key({"name": name})]
        for name in names
        if identifier_key({"name": name}) in cards
    }


def search_cards(query: str, limit: int | None) -> list[dict]:
    url = f"{API_URL}?{urlencode({'q': query})}"
    cards = []

    while url and (limit is None or len(cards) < limit):
        if cards:
            time.sleep(0.1)
        page = fetch_page(url)
        remaining = None if limit is None else limit - len(cards)
        cards.extend(summarize_card(card) for card in page["data"][:remaining])
        url = page.get("next_page") if page.get("has_more") else None

    return cards


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search MTG cards using Scryfall's public card search API."
    )
    parser.add_argument(
        "query",
        help='Scryfall search syntax, for example: \'name:"Lightning Bolt"\'',
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="maximum number of results (default: all matching results)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this file instead of standard output",
    )
    args = parser.parse_args()

    try:
        cards = search_cards(args.query, args.limit)
        output = json.dumps(cards, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(output)
    except (RuntimeError, KeyError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
