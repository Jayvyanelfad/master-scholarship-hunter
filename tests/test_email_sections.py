"""Email-section tests: strict stays strict, possibles get review cards."""

import unittest

from my_actor.emailer import (
    REVIEW_LIMIT,
    build_email_html,
    missing_evidence,
    review_items,
)


def strict_record(**overrides):
    record = {
        "recommendation": "include", "match_status": "strong_match",
        "title": "Strict CS Masters Germany", "url": "https://example.edu/x",
        "official_url": "https://example.edu/x", "canonical_url": "https://example.edu/x",
        "source_name": "DAAD", "destination": "Germany",
        "degree_requirements": "Master's", "field_requirements": "Computer Science",
        "nationality_requirements": "Benin", "funding": "Tuition fees and monthly stipend",
        "deadlines": ["2031-01-01"], "reasons": ["ok"],
        "degree_match": "eligible", "field_match": "eligible",
        "funding_status": "verified_full", "nationality_match": "eligible",
        "nationality_confidence": "high", "destination_match": "eligible",
        "application_from_abroad": "eligible", "deadline_state": "upcoming",
        "verification_status": "verified", "profile_requirements_missing": [],
    }
    record.update(overrides)
    return record


def possible_record(**overrides):
    record = strict_record(
        recommendation="exclude", match_status="possible_match",
        title="Chevening Scholarships", url="https://www.chevening.org/scholarships/",
        official_url="https://www.chevening.org/scholarships/",
        canonical_url="https://www.chevening.org/scholarships",
        source_name="Chevening", destination="United Kingdom",
        funding="Tuition fees and a monthly stipend",
        profile_requirements_missing=["work_experience"],
    )
    record.update(overrides)
    return record


class EmailSectionTests(unittest.TestCase):
    def test_strict_match_in_strict_section(self):
        html = build_email_html([strict_record()])
        self.assertIn("Verified strict matches (1)", html)
        self.assertIn("Strict CS Masters Germany", html)

    def test_possible_match_only_in_review_section(self):
        item = possible_record()
        html = build_email_html([item])
        self.assertIn("No verified strong matches this run.", html)
        self.assertIn("Promising, needs verification (1)", html)
        self.assertIn("Chevening Scholarships", html)
        self.assertIn("NOT verified matches", html)
        self.assertIn("Unverified applicant requirement: work_experience", html)
        # The strict-match framing must not leak onto the review card.
        self.assertNotIn("Why it matched", html)

    def test_partial_funding_never_strict(self):
        html = build_email_html([strict_record(
            recommendation="exclude", match_status="rejected",
            funding_status="excluded", funding="EUR 5,000 scholarship",
            title="Partial Award",
        )])
        self.assertIn("No verified strong matches this run.", html)
        self.assertNotIn("Verified strict matches", html)
        self.assertNotIn("Partial Award", html.split("Promising")[0])

    def test_empty_results_useful_diagnostic_email(self):
        html = build_email_html(
            [],
            {"scholarships_discovered": 0, "possible_matches": 0, "strong_matches": 0},
            {"daad": {"display_name": "DAAD", "discovered": 0, "official_fetched": 0,
                       "verified": 0, "strong_matches": 0, "errors": 1}},
        )
        self.assertIn("No verified strong matches this run.", html)
        self.assertIn("None this run", html)
        self.assertIn("Candidates Discovered", html)
        self.assertIn("DAAD", html)

    def test_deduplication(self):
        first = possible_record()
        duplicate = possible_record(canonical_url="https://www.chevening.org/scholarships/")
        other = possible_record(
            title="GOI-IES", url="https://hea.ie/x", official_url="https://hea.ie/x",
            canonical_url="https://hea.ie/x", source_name="Government of Ireland",
            destination="Ireland", profile_requirements_missing=[],
            deadline_state="unknown",
        )
        self.assertEqual(len(review_items([first, duplicate, other])), 2)

    def test_missing_evidence_accurate(self):
        item = possible_record(
            degree_match="unknown", field_match="unknown", funding_status="unknown",
            nationality_match="unknown", destination_match="unknown",
            application_from_abroad="unknown", deadline_state="unknown",
            verification_status="unverified", profile_requirements_missing=[],
        )
        missing = missing_evidence(item)
        self.assertIn("Official verification page not fetched", missing)
        self.assertIn("Master's eligibility not stated on the official page", missing)
        self.assertIn("Computing field not confirmed", missing)
        self.assertIn(
            "Full funding not verified — tuition AND living evidence missing", missing)
        self.assertIn("Eligibility for Benin not stated", missing)
        self.assertIn("Study country not verified", missing)
        self.assertIn("Applying from abroad not confirmed", missing)
        self.assertIn("Application deadline not found", missing)

    def test_rejected_never_reviewed(self):
        html = build_email_html([strict_record(
            recommendation="exclude", match_status="rejected",
            degree_match="excluded", title="PhD Only",
        )])
        self.assertNotIn("PhD Only", html)

    def test_review_limit_respected(self):
        items = [
            possible_record(
                title=f"Item {index}", url=f"https://example.edu/{index}",
                official_url=f"https://example.edu/{index}",
                canonical_url=f"https://example.edu/{index}",
            )
            for index in range(REVIEW_LIMIT + 5)
        ]
        self.assertEqual(len(review_items(items)), REVIEW_LIMIT)


if __name__ == "__main__":
    unittest.main()
