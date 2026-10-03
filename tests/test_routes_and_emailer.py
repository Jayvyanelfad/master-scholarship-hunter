import unittest

from my_actor.emailer import build_email_html


class EmailTests(unittest.TestCase):
    def test_email_excludes_possible_and_rejected_records(self):
        html = build_email_html([
            {"recommendation": "exclude", "match_status": "possible_match"},
            {"recommendation": "exclude", "match_status": "rejected"},
        ], {"possible_matches": 1, "rejected": 1})
        self.assertIn("No verified strong matches this run", html)
        self.assertIn("Possible Matches: 1", html)


if __name__ == "__main__":
    unittest.main()
