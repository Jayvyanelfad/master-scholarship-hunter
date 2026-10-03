"""Strict-gate tests: funding, nationality/residence, deadlines, regressions.

These pin the historical bad examples and the critical profile rules so
source expansion can never silently weaken the matcher.
"""

from datetime import date
from pathlib import Path
import unittest

from my_actor.profile_rules import evaluate_scholarship
from my_actor.source_adapters.base import extract_text
from my_actor.verification import extract_structured_fields

FIXTURES = Path(__file__).with_name("fixtures")
TODAY = date(2030, 1, 1)


def from_fixture(name: str, **overrides) -> dict:
    fields = extract_structured_fields(extract_text((FIXTURES / name).read_text(encoding="utf-8")))
    payload = {
        "title": "Fixture scholarship", "url": "https://example.edu/scholarship",
        "source_type": "official_university", "degree": fields["degree"], "field": fields["field"],
        "funding": fields["funding"], "nationality": fields["nationality"],
        "destination": fields["destination"], "application_location": fields["application_location"],
        "deadline": fields["deadline"], "cgpa_requirements": fields["cgpa"],
        "verification_status": "verified", "today": TODAY,
    }
    payload.update(overrides)
    return evaluate_scholarship(**payload)


class StrictGateTests(unittest.TestCase):
    def test_mcadam_education_phd_is_rejected(self):
        result = from_fixture("bad_mcadam.html")
        self.assertEqual(result["match_status"], "rejected")

    def test_accommodation_only_is_rejected(self):
        result = from_fixture("bad_accommodation.html")
        self.assertEqual(result["funding_status"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_small_bursary_is_rejected(self):
        result = from_fixture("bad_bursary.html")
        self.assertEqual(result["match_status"], "rejected")

    def test_colorado_partial_usa_is_rejected(self):
        result = from_fixture("bad_colorado.html")
        self.assertEqual(result["destination_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_usa_fully_funded_cs_is_rejected_on_destination(self):
        result = from_fixture(
            "official_valid.html", destination="USA",
            funding="Tuition fees and monthly living stipend",
        )
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertEqual(result["destination_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_germany_fully_funded_cs_benin_can_be_strong(self):
        result = from_fixture("official_valid.html")
        self.assertEqual(result["match_status"], "strong_match")

    def test_benin_vs_india_nationality_is_not_confused(self):
        indian = from_fixture("official_valid.html", nationality="Indian nationals only")
        beninese = from_fixture("official_valid.html", nationality="Benin")
        self.assertEqual(indian["nationality_match"], "excluded")
        self.assertEqual(beninese["nationality_match"], "eligible")

    def test_studying_in_india_is_not_indian_nationality(self):
        result = from_fixture(
            "official_valid.html",
            application_location="The applicant is currently studying in India and may apply from abroad",
        )
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertNotEqual(result["nationality_match"], "excluded")

    def test_closed_residence_list_without_india_rejects(self):
        result = from_fixture("official_valid.html", residence_countries="Benin, Burkina Faso, Cameroon")
        self.assertEqual(result["residence_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_open_residence_rule_does_not_block(self):
        result = from_fixture("official_valid.html", residence_countries="")
        self.assertEqual(result["residence_match"], "unknown")
        self.assertEqual(result["match_status"], "strong_match")

    def test_expired_deadline_rejects(self):
        result = from_fixture("official_valid.html", deadline="12 March 2020")
        self.assertEqual(result["deadline_state"], "expired")
        self.assertEqual(result["match_status"], "rejected")

    def test_between_cycle_without_deadline_is_not_strong(self):
        result = from_fixture(
            "official_valid.html",
            deadline="The 2026 call is closed. The next call is expected to open in mid-November 2031",
        )
        self.assertNotEqual(result["match_status"], "strong_match")

    def test_outside_eu_eea_domicile_covers_benin(self):
        result = from_fixture(
            "official_valid.html",
            nationality="Applicants must have a domiciliary of origin outside the EU/EEA, Switzerland and the United Kingdom",
        )
        self.assertEqual(result["nationality_match"], "eligible")

    def test_title_relevance_alone_is_never_strong(self):
        result = from_fixture(
            "official_valid.html", title="Fully Funded Computer Science Masters in Germany for Benin",
            degree="", field="", funding="", nationality="", destination="",
            application_location="", deadline="",
        )
        self.assertNotEqual(result["match_status"], "strong_match")


if __name__ == "__main__":
    unittest.main()
