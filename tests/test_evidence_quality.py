"""Evidence-quality tests: junk rejection, prose evidence, request limits.

Production showed 83/85 funding_unknown and nationality_unknown because
adapters accepted navigation pages as candidates and missed prose-form
benefits. These tests pin the fixes without touching profile_rules.
"""

import json
from pathlib import Path
import unittest

from my_actor.emailer import build_email_html
from my_actor.pipeline import HealthTracker, limit_diagnostic
from my_actor.source_adapters import adapter_by_id
from my_actor.source_adapters.base import canonical_programme_url, extract_evidence_sentences
from my_actor.verification import canonical_url

FIXTURES = Path(__file__).with_name("fixtures")


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ErasmusQualityTests(unittest.TestCase):
    def test_language_and_social_links_are_ignored(self):
        adapter = adapter_by_id("erasmus_mundus")
        result = adapter.parse_listing(
            read("erasmus_localized_listing.html"),
            "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
        )
        urls = [candidate.url for candidate in result.candidates]
        self.assertFalse(any("facebook" in url for url in urls))
        # Four language variants of one programme collapse to one candidate.
        self.assertEqual(len(result.candidates), 1)

    def test_localized_duplicates_share_identity(self):
        self.assertEqual(
            canonical_url("https://erasmus-plus.ec.europa.eu/es/opportunities/masters-computing"),
            canonical_url("https://erasmus-plus.ec.europa.eu/opportunities/masters-computing?locale=es"),
        )
        self.assertEqual(
            canonical_programme_url("https://example.eu/fr/programme-x"),
            canonical_programme_url("https://example.eu/programme-x"),
        )

    def test_catalogue_page_resolves_without_stub_record(self):
        adapter = adapter_by_id("erasmus_mundus")
        detail = adapter.parse_detail(
            read("erasmus_catalogue.html"),
            "https://erasmus-plus.ec.europa.eu/catalogue/emjm-catalogue",
        )
        self.assertTrue(detail.is_hop)
        self.assertFalse(detail.skip)
        self.assertTrue(detail.follow_links)

    def test_individual_programme_is_discovered_with_evidence(self):
        adapter = adapter_by_id("erasmus_mundus")
        detail = adapter.parse_detail(
            read("erasmus_programme.html"), "https://computerscience-mundus.example.eu/master"
        )
        self.assertFalse(detail.skip)
        self.assertFalse(detail.is_hop)
        self.assertIn("Computer Science", detail.fields["field"])
        self.assertTrue(detail.fields["funding"])
        self.assertTrue(detail.fields["nationality"])


class DaadQualityTests(unittest.TestCase):
    def test_cookie_page_is_skipped(self):
        adapter = adapter_by_id("daad")
        detail = adapter.parse_detail(read("daad_cookie.html"), "https://www.daad.de/en/cookie-consent/")
        self.assertTrue(detail.skip)

    def test_faq_and_navigation_urls_are_not_records(self):
        adapter = adapter_by_id("daad")
        for url in (
            "https://www.daad.de/en/faq-questions-and-answers/",
            "https://www.daad.de/en/accessibility-statement/",
            "https://www.daad.de/en/studying-in-germany/scholarships/daad-scholarships/",
        ):
            self.assertFalse(adapter.is_detail_url(url), url)

    def test_research_section_urls_still_route_to_daad(self):
        adapter = adapter_by_id("daad")
        url = "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/"
        self.assertTrue(adapter.is_detail_url(url))

    def test_actual_record_is_discovered_with_evidence(self):
        adapter = adapter_by_id("daad")
        result = adapter.parse_listing(
            read("daad_listing.html"),
            "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/",
        )
        self.assertEqual(len(result.candidates), 2)
        detail = adapter.parse_detail(
            read("daad_detail.html"),
            "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/",
        )
        self.assertFalse(detail.skip)
        self.assertIn("Benin", detail.fields["nationality"])
        self.assertIn("living allowance", detail.fields["funding"])


class VlirQualityTests(unittest.TestCase):
    def test_bachelor_page_is_not_a_candidate(self):
        adapter = adapter_by_id("vlir_uos")
        self.assertFalse(
            adapter.is_detail_url("https://www.vliruos.be/get-funded/bachelor-applied-computer-science")
        )

    def test_job_page_is_not_a_candidate(self):
        adapter = adapter_by_id("vlir_uos")
        self.assertFalse(
            adapter.is_detail_url("https://www.vliruos.be/about-vliruos/vliruos-zoekt-programme-manager")
        )

    def test_icp_master_is_discovered_with_evidence(self):
        adapter = adapter_by_id("vlir_uos")
        detail = adapter.parse_detail(
            read("vlir_programme.html"),
            "https://www.vliruos.be/get-funded/master-statistics-data-science",
        )
        self.assertFalse(detail.skip)
        self.assertIn("tuition fees", detail.fields["funding"])
        self.assertIn("Benin", detail.residence_countries)


class EvidenceExtractionTests(unittest.TestCase):
    def test_prose_funding_becomes_field_evidence(self):
        text = "The scholarship covers full tuition fees and a monthly living allowance for two years."
        self.assertIn("tuition", extract_evidence_sentences(text, ("tuition", "stipend")))

    def test_empty_page_stays_unknown(self):
        adapter = adapter_by_id("goi_ies")
        detail = adapter.parse_detail("<html><body><h1>Empty</h1></body></html>", "https://hea.ie/x")
        self.assertFalse(detail.skip)
        self.assertEqual(detail.fields["funding"], "")

    def test_destination_defaults_do_not_guess(self):
        adapter = adapter_by_id("erasmus_mundus")
        detail = adapter.parse_detail(
            read("erasmus_programme.html"), "https://computerscience-mundus.example.eu/master"
        )
        # Germany comes from the page's structured destination, not a guess.
        self.assertEqual(detail.fields["destination"], "Germany")

    def test_full_funding_requires_tuition_plus_living(self):
        from my_actor.profile_rules import analyze_funding

        status, _ = analyze_funding("Tuition fees and monthly living stipend", "u", "official_program")
        self.assertEqual(status, "verified_full")
        for partial in ("Fully funded scholarship", "Tuition fee waiver", "EUR 5,000 scholarship"):
            status, _ = analyze_funding(partial, "u", "official_program")
            self.assertNotEqual(status, "verified_full", partial)


class RequestLimitTests(unittest.TestCase):
    def test_limit_is_configurable_with_production_default(self):
        schema = json.loads((FIXTURES.parent.parent / ".actor" / "input_schema.json").read_text(encoding="utf-8"))
        prop = schema["properties"]["max_requests_per_crawl"]
        self.assertEqual(prop["default"], 300)
        self.assertGreaterEqual(prop["maximum"], 300)

    def test_limit_diagnostic_flags_truncation(self):
        ok = limit_diagnostic(scheduled=205, completed=205, limit=300)
        self.assertFalse(ok["request_limit_reached"])
        cut = limit_diagnostic(scheduled=205, completed=100, limit=100)
        self.assertTrue(cut["request_limit_reached"])
        self.assertEqual(cut["requests_completed"], 100)


class HealthMetricTests(unittest.TestCase):
    def test_evidence_verified_and_strong_are_distinct(self):
        tracker = HealthTracker()
        entry = tracker.record("daad", "DAAD")
        entry.verified += 73
        entry.strong_matches += 0
        health = tracker.as_dicts()["daad"]
        self.assertEqual(health["verified"], 73)
        self.assertEqual(health["strong_matches"], 0)

    def test_zero_match_email_contains_full_diagnostics(self):
        html = build_email_html(
            [{"recommendation": "exclude", "match_status": "possible_match"}],
            {
                "scholarships_discovered": 85, "official_pages_checked": 73,
                "possible_matches": 81, "strong_matches": 0,
                "funding_unknown": 83, "nationality_unknown": 83,
                "reason_non_masters": 2,
            },
            {"daad": {"display_name": "DAAD", "discovered": 19, "official_fetched": 12,
                       "verified": 12, "strong_matches": 0, "errors": 0}},
        )
        for expected in (
            "Candidates Discovered", "85", "Official Pages Checked", "73",
            "Possible Matches", "81", "Sources checked", "DAAD",
            "Rejection reasons", "Funding Unknown", "83",
        ):
            self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()
