import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mtg.mtg_card_search import fetch_cards_by_identifiers, summarize_card
from mtg.mtg_deck_viewer import DeckViewerHandler, parse_decklist


class DecklistTests(unittest.TestCase):
    def test_arena_sections_and_printings(self):
        text = (
            "\ufeffCommander\n1 Golos, Tireless Pilgrim (M20) 226\n\n"
            "Deck\n4 Bonecrusher Giant (ELD) 115\n\n"
            "Companion\n1 Lurrus of the Dream-Den (IKO) 226\n\n"
            "Sideboard\n2 Negate (M20) 69"
        )
        entries = parse_decklist(text)
        self.assertEqual(
            [(entry["section"], entry["name"], entry["quantity"]) for entry in entries],
            [
                ("Commander", "Golos, Tireless Pilgrim", 1),
                ("Mainboard", "Bonecrusher Giant", 4),
                ("Companion", "Lurrus of the Dream-Den", 1),
                ("Sideboard", "Negate", 2),
            ],
        )
        self.assertEqual(
            [(entry["set"], entry["collector_number"]) for entry in entries],
            [("m20", "226"), ("eld", "115"), ("iko", "226"), ("m20", "69")],
        )

    def test_japanese_arena_sections(self):
        text = (
            "統率者\n1 砕骨の巨人 (ELD) 115\n"
            "デッキ\n2 島 (M20) 265\n"
            "相棒\n1 夢の巣のルールス (IKO) 226\n"
            "サイドボード\n1 否認 (M20) 69"
        )
        entries = parse_decklist(text)
        self.assertEqual(
            [entry["section"] for entry in entries],
            ["Commander", "Mainboard", "Companion", "Sideboard"],
        )
        self.assertEqual(entries[1]["name"], "島")
        self.assertEqual((entries[1]["set"], entries[1]["collector_number"]), ("m20", "265"))

    def test_existing_format_and_duplicate_handling(self):
        entries = parse_decklist(
            "4 Lightning Bolt\n1x Lightning Bolt\n"
            "1 Carnivorous Cultivator / Enroot (FRA) 430\n"
            "1 Chord of Calling (SLD) 1595 *F*\n"
            "Sideboard\n2 Negate"
        )
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0]["quantity"], 5)
        self.assertEqual(entries[1]["collector_number"], "430")
        self.assertEqual(entries[2]["name"], "Chord of Calling")
        self.assertEqual(entries[3]["section"], "Sideboard")

    def test_about_metadata_is_not_treated_as_cards(self):
        entries = parse_decklist(
            "About\nName Tayam, Luminous Enigma\n\n"
            "Deck\n1 Carnivorous Cultivator\n1 Sol Ring"
        )
        self.assertEqual(
            [(entry["section"], entry["name"]) for entry in entries],
            [("Mainboard", "Carnivorous Cultivator"), ("Mainboard", "Sol Ring")],
        )


class DeckApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DeckViewerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/api/deck"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, text):
        request = Request(
            self.url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_serves_browser_page(self):
        with urlopen(f"http://127.0.0.1:{self.server.server_port}/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"MTG Deck Viewer", response.read())

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_arena_identifier_and_missing_card(self, fetch):
        fetch.return_value = {
            ("printing", "eld", "115"): {
                "name": "Bonecrusher Giant // Stomp",
                "image_url": "https://example.test/card.jpg",
            }
        }
        result = self.post(
            "統率者\n1 砕骨の巨人 (ELD) 115\n"
            "デッキ\n1 Missing Card (ZZZ) 1"
        )
        self.assertEqual(
            fetch.call_args_list[0].args[0],
            [
                {"set": "eld", "collector_number": "115"},
                {"set": "zzz", "collector_number": "1"},
            ],
        )
        self.assertEqual(result["cards"][0]["section"], "Commander")
        self.assertEqual(result["cards"][0]["card"]["name"], "Bonecrusher Giant // Stomp")
        self.assertIsNone(result["cards"][1]["card"])
        self.assertIsNotNone(result["cards"][1]["error"])

    def test_empty_list_is_rejected(self):
        with self.assertRaises(HTTPError) as context:
            self.post("Deck\n")
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_arena_year_fallback_matches_digital_name_and_number(self, fetch):
        candidate = {
            "name": "Mythweaver Poq",
            "set_code": "ylci",
            "collector_number": "19",
            "digital": True,
            "image_url": "https://example.test/poq.jpg",
        }
        fetch.side_effect = [{}, {("name", "mythweaver poq"): candidate}]
        result = self.post("1 Mythweaver Poq (Y24) 19")["cards"][0]
        self.assertEqual(fetch.call_args_list[0].args[0], [{"set": "y24", "collector_number": "19"}])
        self.assertEqual(fetch.call_args_list[1].args[0], [{"name": "Mythweaver Poq"}])
        self.assertEqual(result["card"], candidate)
        self.assertIsNone(result["error"])
        self.assertIsNone(result["notice"])

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_arena_year_fallback_accepts_alternative_printing(self, fetch):
        for candidate in (
            {"set_code": "ylci", "collector_number": "20", "digital": True},
            {"set_code": "ylci", "collector_number": "19", "digital": False},
        ):
            with self.subTest(candidate=candidate):
                fetch.reset_mock()
                fetch.side_effect = [{}, {("name", "mythweaver poq"): candidate}]
                result = self.post("1 Mythweaver Poq (Y24) 19")["cards"][0]
                self.assertEqual(result["card"], candidate)
                self.assertIsNone(result["error"])
                self.assertIsNone(result["notice"])

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_exact_printing_remains_preferred_without_fallback(self, fetch):
        expected = {"name": "Mythweaver Poq"}
        fetch.return_value = {("printing", "y24", "19"): expected}
        result = self.post("1 Mythweaver Poq (Y24) 19")["cards"][0]
        self.assertEqual(result["card"], expected)
        self.assertIsNone(result["notice"])
        self.assertEqual(fetch.call_count, 1)

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_non_arena_set_falls_back_to_name(self, fetch):
        candidate = {"name": "Lightning Bolt", "set_code": "m11"}
        fetch.side_effect = [{}, {("name", "lightning bolt"): candidate}]
        result = self.post("1 Lightning Bolt (M10) 999")["cards"][0]
        self.assertEqual(result["card"], candidate)
        self.assertIsNone(result["error"])
        self.assertEqual(fetch.call_args_list[1].args[0], [{"name": "Lightning Bolt"}])

    @patch("mtg.mtg_deck_viewer.fetch_cards_by_identifiers")
    def test_fallback_is_batched_and_missing_remains_error(self, fetch):
        fetch.side_effect = [{}, {("name", "sylvan library"): {"name": "Sylvan Library"}}]
        result = self.post(
            "2 Sylvan Library (SPG) 0\nSideboard\n1 Sylvan Library (ABC) 1\n"
            "1 Unknown Card (ZZZ) 1"
        )["cards"]
        self.assertEqual(
            fetch.call_args_list[1].args[0],
            [{"name": "Sylvan Library"}, {"name": "Unknown Card"}],
        )
        self.assertEqual([entry["card"] is not None for entry in result], [True, True, False])
        self.assertIsNotNone(result[2]["error"])


class CollectionTests(unittest.TestCase):
    @patch("mtg.mtg_card_search.urlopen")
    def test_collection_preserves_printing_page_url(self, open_url):
        card = {
            "name": "Lightning Bolt",
            "set": "m10",
            "collector_number": "146",
            "scryfall_uri": "https://scryfall.com/card/m10/146/lightning-bolt",
        }
        open_url.return_value = BytesIO(json.dumps({"data": [card]}).encode())
        with patch("mtg.mtg_card_search._last_collection_request", 0.0):
            found = fetch_cards_by_identifiers([{"set": "m10", "collector_number": "146"}])
        self.assertEqual(
            found[("printing", "m10", "146")]["scryfall_url"],
            card["scryfall_uri"],
        )
        self.assertNotIn("scryfall_url", summarize_card(card))

    @patch("mtg.mtg_card_search.time.sleep")
    @patch("mtg.mtg_card_search.urlopen")
    def test_collection_batches_and_spaces_requests(self, open_url, sleep):
        open_url.side_effect = lambda *args, **kwargs: BytesIO(
            b'{"data": [], "not_found": []}'
        )
        identifiers = [{"name": f"Card {number}"} for number in range(76)]
        with patch("mtg.mtg_card_search._last_collection_request", 0.0):
            with patch("mtg.mtg_card_search.time.monotonic", side_effect=[10.0, 10.0, 10.1, 10.5]):
                fetch_cards_by_identifiers(identifiers)

        self.assertEqual(open_url.call_count, 2)
        batches = [json.loads(call.args[0].data) for call in open_url.call_args_list]
        self.assertEqual([len(batch["identifiers"]) for batch in batches], [75, 1])
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.4)


if __name__ == "__main__":
    unittest.main()
