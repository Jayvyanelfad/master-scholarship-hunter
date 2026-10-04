"""Live-run regression tests: precision, evidence, limits, VLIR golden case.

Covers the concrete production findings without touching the strict
matcher rules: candidate explosion, unknown-evidence explosion, the wrong
``request_limit_reached=False``, the VLIR 2026-2027 expiry, and WMS index
misclassification.
"""

from datetime import date
from pathlib import Path
import unittest

from my_actor.pipeline import build_limit_diagnostic
from my_actor.profile_rules import analyze_funding, evaluate_scholarship
from my_actor.source_adapters import adapter_by_id
from my_actor.source_adapters.base import extract_text, matches_nav_anchor
from my_actor.source_adapters.wemakescholars import is_scholarship_url
from my_actor.verification import extract_structured_fields, normalize_funding_prose

FIXTURES = Path(__file__).with_name("fixtures")
OCT_2026 = date(2026, 10, 4)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def evaluate(fields: dict, **overrides) -> dict:
    payload = {
        "title": "Fixture", "url": "https://example.edu/x",
        "source_type": "official_program", "degree": fields.get("degree", ""),
        "field": fields.get("field", ""), "funding": fields.get("funding", ""),
        "nationality": fields.get("nationality", ""),
        "destination": fields.get("destination", ""),
        "application_location": fields.get("application_location", ""),
        "deadline": fields.get("deadline", ""),
        "cgpa_requirements": fields.get("cgpa", ""),
        "verification_status": "verified", "today": OCT_2026,
    }
    payload.update(overrides)
    return evaluate_scholarship(**payload)


class RequestLimitTests(unittest.TestCase):
    def test_live_numbers_report_limit_reached(self):
        # Production: limit 300, ~428 router-enqueued, 298 processed.
        diagnostic = build_limit_diagnostic(
            scheduled=302, enqueued=428, completed=298, limit=300, stats_total=302,
        )
        self.assertTrue(diagnostic["request_limit_reached"])

    def test_completed_run_reports_not_reached(self):
        diagnostic = build_limit_diagnostic(
            scheduled=205, enqueued=205, completed=205, limit=300, stats_total=205,
        )
        self.assertFalse(diagnostic["request_limit_reached"])

    def test_exact_limit_fully_processed_is_not_truncation(self):
        diagnostic = build_limit_diagnostic(
            scheduled=300, enqueued=300, completed=300, limit=300, stats_total=300,
        )
        self.assertFalse(diagnostic["request_limit_reached"])

    def test_crawler_total_alone_can_prove_truncation(self):
        diagnostic = build_limit_diagnostic(
            scheduled=302, enqueued=302, completed=250, limit=300, stats_total=305,
        )
        self.assertTrue(diagnostic["request_limit_reached"])


class DiscoveryPrecisionTests(unittest.TestCase):
    def test_portal_nav_yields_one_record_plus_pagination(self):
        adapter = adapter_by_id("norway")
        result = adapter.parse_listing(
            read("portal_nav_listing.html"), "https://www.studyinnorway.no/"
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertIn("norwegian-government-scholarship", result.candidates[0].url)
        self.assertIsNotNone(result.next_page_url)
        self.assertNotIn("page=2", result.candidates[0].url)

    def test_pagination_is_never_a_record(self):
        adapter = adapter_by_id("norway")
        self.assertFalse(adapter.is_detail_url("https://www.studyinnorway.no/study-opportunities?page=2"))

    def test_nav_anchors_rejected(self):
        for anchor in ("Find a programme", "Cost and requirements", "Universities", "View all"):
            self.assertTrue(matches_nav_anchor(anchor), anchor)
        self.assertFalse(matches_nav_anchor("Norwegian Government Scholarship for international students"))

    def test_wms_index_pages_are_not_details(self):
        for url in (
            "https://www.wemakescholars.com/university/university-of-east-london/scholarships",
            "https://www.wemakescholars.com/scholarships-to-study-in-germany-for-international-students",
            "https://www.wemakescholars.com/scholarship",
        ):
            self.assertFalse(is_scholarship_url(url), url)
        self.assertTrue(is_scholarship_url("https://www.wemakescholars.com/scholarship/example-masters"))
        self.assertTrue(is_scholarship_url("https://www.wemakescholars.com/scholarships/example-computing"))

    def test_wms_search_endpoint_is_a_listing(self):
        adapter = adapter_by_id("wemakescholars")
        url = "https://www.wemakescholars.com/scholarship?study=3&interest=3"
        self.assertTrue(adapter.is_listing_url(url))
        self.assertIn(url, adapter.discovery_urls)


class FundingNormalizationTests(unittest.TestCase):
    def test_fully_funded_alone_is_unknown(self):
        status, _ = analyze_funding("Fully funded scholarship", "u", "official_program")
        self.assertEqual(status, "unknown")

    def test_tuition_plus_monthly_stipend_is_verified_full(self):
        status, _ = analyze_funding(
            "Tuition fees and a monthly stipend of 1,400 EUR per month", "u", "official_program"
        )
        self.assertEqual(status, "verified_full")

    def test_participation_plus_living_is_verified_full(self):
        status, _ = analyze_funding(
            "Covers participation costs, travel, visa and a monthly living allowance",
            "u", "official_program",
        )
        self.assertEqual(status, "verified_full")

    def test_accommodation_only_is_not_verified_full(self):
        status, _ = analyze_funding("Accommodation provided on campus", "u", "official_program")
        self.assertNotEqual(status, "verified_full")

    def test_tuition_only_is_not_verified_full(self):
        status, _ = analyze_funding("Only tuition fees, USD 25,000", "u", "official_program")
        self.assertNotEqual(status, "verified_full")

    def test_bursary_only_is_not_verified_full(self):
        status, _ = analyze_funding("Small bursary of AUD 500", "u", "official_program")
        self.assertNotEqual(status, "verified_full")

    def test_currency_words_normalize_to_codes(self):
        self.assertIn("EUR", normalize_funding_prose("monthly payments of 1,400 euros"))
        self.assertEqual(
            normalize_funding_prose("monthly payments of 1,400 euros"),
            "monthly payments of EUR 1,400",
        )
        status, _ = analyze_funding(
            normalize_funding_prose("Tuition fees covered plus monthly payments of EUR 1,400 per month"),
            "u", "official_program",
        )
        self.assertEqual(status, "verified_full")

    def test_scholarship_amount_label_is_extracted(self):
        fields = extract_structured_fields(extract_text(read("wms_live_card.html")))
        self.assertIn("tuition fees", fields["funding"])


class NationalityExtractionTests(unittest.TestCase):
    def test_open_indian_nationals_is_excluded(self):
        fields = extract_structured_fields(extract_text(read("wms_live_card.html")))
        result = evaluate(fields, destination="Germany", deadline="31 December 2030",
                          today=date(2030, 1, 1))
        self.assertEqual(result["nationality_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_regional_categories_recognized(self):
        for text, expected in (
            ("Open to African countries", "eligible"),
            ("Sub-Saharan Africa", "eligible"),
            ("non-EU applicants", "eligible"),
        ):
            result = evaluate_scholarship(
                title="T", url="https://example.edu/x", source_type="official_program",
                degree="Master's", field="Computer Science",
                funding="Tuition fees and monthly stipend", nationality=text,
                destination="Germany",
                application_location="International applicants may apply from abroad",
                deadline="31 December 2030", verification_status="verified",
                today=date(2030, 1, 1),
            )
            self.assertEqual(result["nationality_match"], expected, text)

    def test_unknown_nationality_stays_unknown(self):
        result = evaluate_scholarship(
            title="T", url="https://example.edu/x", source_type="official_program",
            degree="Master's", field="Computer Science",
            funding="Tuition fees and monthly stipend", nationality="",
            destination="Germany",
            application_location="International applicants may apply from abroad",
            deadline="31 December 2030", verification_status="verified",
            today=date(2030, 1, 1),
        )
        self.assertEqual(result["nationality_match"], "unknown")
        self.assertNotEqual(result["match_status"], "strong_match")


class VlirGoldenTests(unittest.TestCase):
    def test_benin_not_excluded_but_call_expired(self):
        adapter = adapter_by_id("vlir_uos")
        detail = adapter.parse_detail(
            read("vlir_icp_2026.html"),
            "https://www.vliruos.be/get-funded/study-scholarships",
        )
        self.assertFalse(detail.skip)
        self.assertIn("Benin", detail.fields["nationality"])
        result = evaluate(
            detail.fields, residence_countries=detail.residence_countries,
            requirement_text=detail.requirement_text,
        )
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["deadline_state"], "expired")
        self.assertEqual(result["match_status"], "rejected")

    def test_project_call_is_not_a_scholarship(self):
        adapter = adapter_by_id("vlir_uos")
        self.assertFalse(adapter.is_detail_url(
            "https://www.vliruos.be/get-funded/project-funding/short-initiative"))
        result = adapter.parse_listing(
            read("vlir_project_call.html"), "https://www.vliruos.be/get-funded/study-scholarships"
        )
        self.assertEqual(len(result.candidates), 0)


class DeadlineExtractionTests(unittest.TestCase):
    def test_explicit_date(self):
        result = evaluate_scholarship(
            title="T", url="u", source_type="official_program", degree="Master's",
            field="Computer Science", funding="Tuition fees and monthly stipend",
            nationality="Benin", destination="Germany",
            application_location="International applicants may apply from abroad",
            deadline="28 February 2026", verification_status="verified", today=OCT_2026,
        )
        self.assertEqual(result["deadline_state"], "expired")

    def test_wms_comma_date_parses(self):
        result = evaluate_scholarship(
            title="T", url="u", source_type="official_program", degree="Master's",
            field="Computer Science", funding="Tuition fees and monthly stipend",
            nationality="Benin", destination="Germany",
            application_location="International applicants may apply from abroad",
            deadline="31 Oct, 2026", verification_status="verified", today=OCT_2026,
        )
        self.assertEqual(result["deadline_state"], "upcoming")

    def test_date_range_uses_future_end(self):
        result = evaluate_scholarship(
            title="T", url="u", source_type="official_program", degree="Master's",
            field="Computer Science", funding="Tuition fees and monthly stipend",
            nationality="Benin", destination="Germany",
            application_location="International applicants may apply from abroad",
            deadline="Applications open 1 November 2025 to 28 February 2027",
            verification_status="verified", today=OCT_2026,
        )
        self.assertIn(result["deadline_state"], ("active", "upcoming"))

    def test_no_deadline_is_unknown_not_expired(self):
        result = evaluate_scholarship(
            title="T", url="u", source_type="official_program", degree="Master's",
            field="Computer Science", funding="Tuition fees and monthly stipend",
            nationality="Benin", destination="Germany",
            application_location="International applicants may apply from abroad",
            deadline="See the latest guidelines", verification_status="verified", today=OCT_2026,
        )
        self.assertEqual(result["deadline_state"], "unknown")


class RecordIdentityTests(unittest.TestCase):
    def test_generic_info_page_without_evidence_is_skipped(self):
        adapter = adapter_by_id("finland")
        detail = adapter.parse_detail(
            "<html><body><h1>Funding your studies</h1><p>Plan your budget.</p></body></html>",
            "https://www.studyinfinland.fi/funding-your-studies",
        )
        self.assertTrue(detail.skip or not detail.fields["funding"])

    def test_cookie_page_skipped_everywhere(self):
        html = read("daad_cookie.html")
        for source_id in ("daad", "norway", "finland"):
            detail = adapter_by_id(source_id).parse_detail(html, "https://example.edu/cookie/")
            self.assertTrue(detail.skip, source_id)


if __name__ == "__main__":
    unittest.main()
