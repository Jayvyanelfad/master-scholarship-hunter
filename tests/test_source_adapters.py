"""Adapter tests: discovery parsing and official detail extraction per source.

All parsing is exercised on mocked HTML fixtures (no network). Fixtures
mirror the structure of the verified official pages; adapters must extract
evidence from the page, never invent it.
"""

from datetime import date
from pathlib import Path
import unittest

from my_actor.profile_rules import evaluate_scholarship
from my_actor.source_adapters import adapter_by_id
from my_actor.source_adapters.base import extract_text
from my_actor.verification import extract_structured_fields

FIXTURES = Path(__file__).with_name("fixtures")
TODAY = date(2030, 1, 1)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def evaluate_detail(source_id: str, fixture_name: str, url: str, **overrides):
    adapter = adapter_by_id(source_id)
    assert adapter is not None, source_id
    detail = adapter.parse_detail(read(fixture_name), url)
    fields = dict(detail.fields)
    fields.update(overrides)
    result = evaluate_scholarship(
        title=detail.title, url=url, source_type=adapter.source_type,
        degree=fields["degree"], field=fields["field"], funding=fields["funding"],
        nationality=fields["nationality"], destination=fields["destination"] or adapter.destination,
        application_location=fields["application_location"], deadline=fields["deadline"],
        cgpa_requirements=fields["cgpa"], verification_status="verified",
        residence_countries=detail.residence_countries,
        requirement_text=detail.requirement_text, today=TODAY,
    )
    return detail, result


class AdapterDiscoveryTests(unittest.TestCase):
    def test_erasmus_listing_finds_programme_links_not_social(self):
        adapter = adapter_by_id("erasmus_mundus")
        result = adapter.parse_listing(
            read("erasmus_listing.html"),
            "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
        )
        urls = [candidate.url for candidate in result.candidates]
        self.assertTrue(any("catalogue" in url for url in urls))
        self.assertTrue(any("computerscience-mundus" in url for url in urls))
        self.assertFalse(any("facebook" in url for url in urls))

    def test_daad_listing_finds_record_links(self):
        adapter = adapter_by_id("daad")
        result = adapter.parse_listing(
            read("daad_listing.html"),
            "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/",
        )
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all("daad.de" in candidate.url for candidate in result.candidates))

    def test_daad_detail_normalizes_official_labels(self):
        detail, _ = evaluate_detail(
            "daad", "daad_detail.html",
            "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/",
        )
        # "Who can apply?" and "What is funded?" are DAAD headings that must
        # be normalized into the shared evidence vocabulary.
        self.assertIn("Benin", detail.fields["nationality"])
        self.assertIn("living allowance", detail.fields["funding"])

    def test_daad_full_record_can_be_strong(self):
        _, result = evaluate_detail(
            "daad", "daad_detail.html",
            "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/",
        )
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["match_status"], "strong_match")

    def test_erasmus_programme_can_be_strong(self):
        _, result = evaluate_detail(
            "erasmus_mundus", "erasmus_programme.html",
            "https://computerscience-mundus.example.eu/master",
        )
        self.assertEqual(result["match_status"], "strong_match")

    def test_vlir_listing_finds_programme_pages(self):
        adapter = adapter_by_id("vlir_uos")
        result = adapter.parse_listing(
            read("vlir_listing.html"), "https://www.vliruos.be/get-funded/study-scholarships"
        )
        self.assertEqual(len(result.candidates), 2)

    def test_vlir_india_residence_rejects_despite_benin_nationality(self):
        detail, result = evaluate_detail(
            "vlir_uos", "vlir_programme.html",
            "https://www.vliruos.be/get-funded/master-statistics-data-science",
        )
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertIn("Benin", detail.residence_countries)
        self.assertEqual(result["residence_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_chevening_work_experience_blocks_strong_match(self):
        detail, result = evaluate_detail(
            "chevening", "chevening_detail.html", "https://www.chevening.org/scholarships/"
        )
        self.assertIn("work experience", detail.requirement_text)
        self.assertIn("work_experience", result["profile_requirements_missing"])
        self.assertNotEqual(result["match_status"], "strong_match")
        self.assertEqual(result["recommendation"], "exclude")

    def test_goi_ies_funding_verdict_comes_from_evidence(self):
        _, result = evaluate_detail(
            "goi_ies", "goi_detail.html",
            "https://hea.ie/policy/internationalisation/goi-ies/",
        )
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertEqual(result["nationality_match"], "eligible")
        # No computing field on the call page, so this stays possible: the
        # verifier decides from evidence instead of assuming.
        self.assertEqual(result["match_status"], "possible_match")

    def test_mext_research_pathway_keeps_masters_but_stays_possible(self):
        _, result = evaluate_detail(
            "mext", "mext_detail.html",
            "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
        )
        self.assertEqual(result["degree_match"], "eligible")
        self.assertEqual(result["funding_status"], "verified_full")
        # No eligible-country wording on the overview page: nationality and
        # deadline stay unknown until a current guideline is verified.
        self.assertEqual(result["nationality_match"], "unknown")
        self.assertEqual(result["match_status"], "possible_match")

    def test_mastercard_follows_partner_routes(self):
        adapter = adapter_by_id("mastercard_foundation")
        detail = adapter.parse_detail(
            read("mastercard_detail.html"),
            "https://mastercardfdn.org/en/what-we-do/our-programs/mastercard-foundation-scholars-program/",
        )
        self.assertTrue(detail.follow_links)
        self.assertTrue(any("partner-university" in link for link in detail.follow_links))

    def test_nl_scholarship_is_discovered_then_rejected_as_partial(self):
        detail, result = evaluate_detail(
            "nl_scholarship", "nl_detail.html", "https://www.studyinnl.org/finances/nl-scholarship"
        )
        self.assertEqual(detail.fields["destination"], "Netherlands")
        self.assertEqual(result["funding_status"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_si_sweden_gaps_block_strong_match(self):
        _, result = evaluate_detail(
            "si_sweden", "si_detail.html", "https://si.se/en/apply/scholarships/"
        )
        self.assertTrue(result["profile_requirements_missing"])
        self.assertNotEqual(result["match_status"], "strong_match")

    def test_finland_tuition_waiver_is_not_strong(self):
        _, result = evaluate_detail(
            "finland", "finland_detail.html", "https://www.studyinfinland.fi/scholarships"
        )
        self.assertNotEqual(result["match_status"], "strong_match")

    def test_eskas_doctoral_track_is_rejected(self):
        _, result = evaluate_detail(
            "switzerland", "eskas_detail.html",
            "https://www.sbfi.admin.ch/sbfi/en/home/education/scholarships-and-grants/swiss-government-excellence-scholarships.html",
        )
        self.assertEqual(result["degree_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_australia_awards_can_be_strong_with_full_evidence(self):
        _, result = evaluate_detail(
            "australia", "australia_detail.html", "https://www.australiaawardsafrica.org/"
        )
        self.assertEqual(result["match_status"], "strong_match")

    def test_erasmus_overview_resolves_programme_without_stub_record(self):
        adapter = adapter_by_id("erasmus_mundus")
        detail = adapter.parse_detail(
            read("erasmus_listing.html"),
            "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
        )
        self.assertTrue(detail.is_hop)
        self.assertTrue(detail.follow_links)

    def test_extract_fallback(self):
        fields = extract_structured_fields(extract_text(read("erasmus_programme.html")))
        self.assertIn("Computer Science", fields["field"])


if __name__ == "__main__":
    unittest.main()
