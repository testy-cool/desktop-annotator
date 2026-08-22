import json
import unittest
from datetime import datetime

from desktop_annotator.annotation import Annotation
from desktop_annotator.capture import TextCandidate
from desktop_annotator.webview import (
    annotations_from_payload,
    build_state,
    entries_payload,
    page_with_state,
)


def annotation(quote="quoted", comment="commented", source="Firefox", minute=1):
    return Annotation(
        quote=quote,
        comment=comment,
        source=source,
        captured_at=datetime(2026, 8, 22, 15, minute),
    )


class EntriesPayloadTests(unittest.TestCase):
    def test_shows_the_newest_entry_first(self):
        payload = entries_payload([annotation(quote="older", minute=1), annotation(quote="newer", minute=2)])

        self.assertEqual([entry["quote"] for entry in payload], ["newer", "older"])

    def test_carries_the_timestamp_the_interface_displays(self):
        payload = entries_payload([annotation()])

        self.assertEqual(payload[0]["stamp"], "2026-08-22 15:01")
        self.assertEqual(payload[0]["source"], "Firefox")


class AnnotationsFromPayloadTests(unittest.TestCase):
    def test_round_trips_the_list_back_into_file_order(self):
        original = [annotation(quote="older", minute=1), annotation(quote="newer", minute=2)]

        restored = annotations_from_payload(entries_payload(original))

        self.assertEqual(restored, original)

    def test_keeps_an_edited_quote_and_comment(self):
        payload = entries_payload([annotation()])
        payload[0]["quote"] = "  edited quote  "
        payload[0]["comment"] = "edited comment"

        restored = annotations_from_payload(payload)

        self.assertEqual(restored[0].quote, "edited quote")
        self.assertEqual(restored[0].comment, "edited comment")

    def test_refuses_an_entry_that_lost_its_comment(self):
        payload = entries_payload([annotation()])
        payload[0]["comment"] = "   "

        with self.assertRaises(ValueError):
            annotations_from_payload(payload)

    def test_a_removed_entry_stays_removed(self):
        payload = entries_payload([annotation(quote="keep", minute=1), annotation(quote="drop", minute=2)])

        restored = annotations_from_payload([entry for entry in payload if entry["quote"] != "drop"])

        self.assertEqual([item.quote for item in restored], ["keep"])


class BuildStateTests(unittest.TestCase):
    def test_offers_every_captured_candidate(self):
        state = build_state(
            candidates=[TextCandidate("Selected text", "one"), TextCandidate("Clipboard", "two")],
            source="Firefox",
            annotations=[],
            now=datetime(2026, 8, 22, 15, 20),
        )

        self.assertEqual(
            state["candidates"],
            [
                {"label": "Selected text", "text": "one"},
                {"label": "Clipboard", "text": "two"},
            ],
        )
        self.assertEqual(state["stamp"], "2026-08-22 15:20")
        self.assertEqual(state["source"], "Firefox")


class PageWithStateTests(unittest.TestCase):
    def test_hands_the_page_its_state_before_the_first_script_runs(self):
        page = page_with_state("<head></head><script>real()</script>", {"source": "Firefox"})

        self.assertLess(page.index("__STATE__"), page.index("real()"))
        self.assertIn('"source": "Firefox"', page)

    def test_a_quote_cannot_close_the_script_tag_early(self):
        page = page_with_state("<script>x</script>", {"source": "</script><script>evil()</script>"})

        self.assertNotIn("evil()</script>", page)
        self.assertIn("<\\/script>", page)

    def test_the_state_survives_as_valid_json(self):
        page = page_with_state("<script>x</script>", {"source": "Bad </script> window"})
        payload = page.split("window.__STATE__=", 1)[1].split(";</script>", 1)[0]

        self.assertEqual(json.loads(payload)["source"], "Bad </script> window")


if __name__ == "__main__":
    unittest.main()
