"""Pipeline tests: dedup, failure isolation, diagnostics, zero-match email."""

import unittest

from my_actor.emailer import build_email_html
from my_actor.pipeline import HealthTracker, RecordStore, assemble_record, rejection_breakdown
from my_actor.profile_rules import STUDENT_PROFILE
from my_actor.source_adapters.base import dedup_key


def make_record(**overrides) -> dict:
    evaluated = {
        "match_status": "possible_match", "recommendation": "exclude",
        "degree_match": "unknown", "funding_status": "unknown",
        "field_match": "unknown", "nationality_match": "unknown",
        "destination_match": "unknown", "application_from_abroad": "unknown",
        "residence_match": "unknown", "deadline_state": "unknown",
    }
    evaluated.update(overrides.pop("evaluated", {}))
    base = {
        "evaluated": evaluated, "source_id": "daad", "source_name": "DAAD",
        "source_domain": "daad.de", "source_type": "official_government",
        "title": "Example", "discovery_url": "https://www.daad.de/record",
        "official_url": "https://www.daad.de/record", "canonical_url": "https://www.daad.de/record",
        "official_source_domain": "daad.de", "official_source_type": "official_government",
        "verification_status": "verified", "discovery_fields": {}, "official_fields": {},
        "display_fields": {}, "student_profile": STUDENT_PROFILE,
        "provenance": [{"source_id": "daad", "source_name": "DAAD", "discovery_url": "https://www.daad.de/record", "role": "verification"}],
        "discovery_timestamp": "2026-01-01T00:00:00+00:00", "verification_timestamp": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return assemble_record(**base)


class PipelineTests(unittest.TestCase):
    def test_same_official_url_dedups_across_sources(self):
        store = RecordStore()
        key = dedup_key("Shared Scholarship", "Example University", "Germany", "https://example.edu/apply")
        first = make_record(
            source_id="wemakescholars",
            provenance=[{"source_id": "wemakescholars", "source_name": "WeMakeScholars", "discovery_url": "https://www.wemakescholars.com/s/1", "role": "discovery"}],
            official_url="https://example.edu/apply",
        )
        second = make_record(
            source_id="daad",
            provenance=[{"source_id": "daad", "source_name": "DAAD", "discovery_url": "https://www.daad.de/record", "role": "verification"}],
            official_url="https://example.edu/apply",
        )
        self.assertEqual(store.store(key, first), "inserted")
        self.assertEqual(store.store(key, second), "duplicate")
        self.assertEqual(len(store), 1)
        provenance = store.records()[0]["source_provenance"]
        self.assertEqual(len(provenance), 2)

    def test_verified_evidence_upgrades_unverified_record(self):
        store = RecordStore()
        key = dedup_key("Shared Scholarship", "Example University", "Germany", "https://example.edu/apply")
        unverified = make_record(verification_status="unverified", official_url="")
        verified = make_record(verification_status="verified")
        self.assertEqual(store.store(key, unverified), "inserted")
        self.assertEqual(store.store(key, verified), "upgraded")
        self.assertEqual(store.records()[0]["verification_status"], "verified")

    def test_source_failure_isolation(self):
        tracker = HealthTracker()
        tracker.record("daad", "DAAD").discovered += 3
        tracker.fail("vlir_uos", "VLIR-UOS", "Listing parse failed: boom")
        health = tracker.as_dicts()
        self.assertEqual(health["daad"]["discovered"], 3)
        self.assertEqual(health["vlir_uos"]["errors"], 1)
        self.assertIn("boom", health["vlir_uos"]["note"])

    def test_rejection_breakdown_explains_zero_matches(self):
        items = [
            {"match_status": "rejected", "degree_match": "excluded"},
            {"match_status": "rejected", "degree_match": "eligible", "funding_status": "excluded"},
            {"match_status": "possible_match"},
        ]
        reasons = rejection_breakdown(items)
        self.assertEqual(reasons["non_masters"], 1)
        self.assertEqual(reasons["not_fully_funded"], 1)
        self.assertEqual(reasons["possible_matches"], 1)

    def test_zero_match_email_shows_sources_and_reasons(self):
        html = build_email_html(
            [{"recommendation": "exclude", "match_status": "rejected", "degree_match": "excluded"}],
            {"possible_matches": 0, "rejected": 1, "reason_non_masters": 1, "reason_expired": 0},
            {"daad": {"display_name": "DAAD", "discovered": 4, "official_fetched": 2, "verified": 0, "errors": 0}},
        )
        self.assertIn("No verified strong matches this run", html)
        self.assertIn("Sources checked", html)
        self.assertIn("DAAD", html)
        self.assertIn("Rejected summary", html)
        self.assertIn("Non-Master", html)

    def test_strong_match_email_still_restricted(self):
        html = build_email_html([
            {"recommendation": "include", "match_status": "strong_match", "title": "Good",
             "url": "https://example.edu/x", "destination": "Germany", "degree_requirements": "Master's",
             "field_requirements": "Computer Science", "nationality_requirements": "Benin",
             "funding": "Tuition fees and monthly living stipend", "deadlines": ["2031-01-01"], "reasons": ["ok"]},
            {"recommendation": "exclude", "match_status": "possible_match", "title": "Maybe"},
        ])
        self.assertIn("Good", html)
        self.assertNotIn("Maybe", html)


if __name__ == "__main__":
    unittest.main()
