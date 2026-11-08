"""Run with:  python3 -m unittest discover tests"""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "waitlist_watch", Path(__file__).resolve().parent.parent / "waitlist_watch.py")
ww = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ww)

CLASS_PAGE_SNIPPET = """
<section class="collapsable current-enrollment open">
  <div class="top"><strong>Total Open Seats:</strong> <span>51</span></div>
  <div class="stats">
    <div><strong>Enrolled:</strong> 19</div>
    <div><strong>Waitlisted:</strong> 0</div>
    <div><strong>Capacity:</strong> 70</div>
    <div><strong>Waitlist Max:</strong> 10</div>
  </div>
</section>
"""

FULL = {"enrolled": 70, "cap": 70, "waitlisted": 10, "waitlist_cap": 10}


class ParseClassPage(unittest.TestCase):
    def setUp(self):
        ww.CFG = {"year": 2027, "semester": "Spring"}
        self.urls = []
        ww.curl_get = lambda url: (self.urls.append(url), CLASS_PAGE_SNIPPET)[1]

    def test_reads_counts(self):
        d = ww.fetch_class_page("PHYSICS", "137A", "001")
        self.assertEqual((d["enrolled"], d["cap"], d["waitlisted"], d["waitlist_cap"]), (19, 70, 0, 10))

    def test_builds_url(self):
        ww.fetch_class_page("PHYSICS", "137A", "001")
        self.assertTrue(self.urls[0].startswith(
            "https://classes.berkeley.edu/content/2027-spring-physics-137a-001-lec-001"))

    def test_missing_section_raises(self):
        ww.curl_get = lambda url: "<html>no enrollment here</html>"
        with self.assertRaises(RuntimeError):
            ww.fetch_class_page("PHYSICS", "105", "001")


class DetectChanges(unittest.TestCase):
    def test_first_check_is_silent(self):
        self.assertEqual(ww.changes("x", None, FULL), [])

    def test_no_change_is_silent(self):
        self.assertEqual(ww.changes("x", FULL, dict(FULL)), [])

    def test_waitlist_spot_opens(self):
        msgs = ww.changes("x", FULL, dict(FULL, waitlisted=9))
        self.assertEqual(len(msgs), 1)
        self.assertIn("WAITLIST SPOT OPEN", msgs[0])

    def test_seat_opens(self):
        msgs = ww.changes("x", FULL, dict(FULL, enrolled=69))
        self.assertTrue(any("SEAT OPEN" in m for m in msgs))

    def test_class_fills(self):
        old = dict(FULL, enrolled=69, waitlisted=0)
        msgs = ww.changes("x", old, dict(FULL, waitlisted=0))
        self.assertTrue(any("just filled" in m for m in msgs))

    def test_cap_raise(self):
        msgs = ww.changes("x", FULL, dict(FULL, cap=80, enrolled=72, waitlisted=8))
        self.assertTrue(any("Seat cap changed 70 → 80" in m for m in msgs))
        self.assertTrue(any("WAITLIST SPOT OPEN" in m for m in msgs))

    def test_enrolled_changes_only_when_enabled(self):
        old = dict(FULL, enrolled=19, waitlisted=0)
        new = dict(old, enrolled=21)
        self.assertEqual(ww.changes("x", old, new), [])
        self.assertEqual(len(ww.changes("x", old, new, notify_enrolled=True)), 1)


class LoadConfig(unittest.TestCase):
    def test_example_config_loads(self):
        cfg = ww.load_config(Path(__file__).resolve().parent.parent / "config.example.json")
        self.assertEqual(cfg["semester"], "Spring")
        self.assertEqual(cfg["classes"][0][:3], ("PHYSICS", "105", "001"))


if __name__ == "__main__":
    unittest.main()
