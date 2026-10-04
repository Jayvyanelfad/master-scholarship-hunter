"""End-to-end golden tests: official page -> evidence -> strong_match/include.

Positive case: a DAAD-flavored official record whose every evidence
sentence uses vocabulary verified on real official pages (database labels,
EMJM benefit formula, non-EEA/domicile eligibility wording). The test
proves the PIPELINE can produce strong_match/include; it then removes
each required evidence item once and proves the match collapses, so the
test fails if any required evidence disappears.

Negative cases: superficially attractive but non-compliant awards stay
rejected/excluded through the same chain.
"""

from datetime import date
from pathlib import Path
import unittest

from my_actor.profile_rules import evaluate_scholarship
from my_actor.source_adapters import adapter_by_id
from my_actor.verification import LinkCandidate, select_official_url

FIXTURES = Path(__file__).with_name("fixtures")
TODAY = date(2030, 1, 1)
DAAD_URL = "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/"


def evaluate_detail(source_id: str, fixture: str, url: str, **overrides):
    adapter = adapter_by_id(source_id)
    detail = adapter.parse_detail((FIXTURES / fixture).read_text(encoding="utf-8"), url)
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


class PositiveGoldenTests(unittest.TestCase):
    def test_official_record_reaches_strong_match_include(self):
        detail, result = evaluate_detail("daad", "daad_detail.html", DAAD_URL)
        self.assertFalse(detail.skip)
        self.assertEqual(result["verification_status"], "verified")
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["match_status"], "strong_match")
        self.assertEqual(result["recommendation"], "include")

    def test_each_required_evidence_is_load_bearing(self):
        # Blank exactly one evidence field at a time: strong must collapse.
        # Destination has an adapter-level default, so its absence is proven
        # through an excluded destination instead of an empty string.
        load_bearing = (
            "degree", "field", "funding", "nationality",
            "application_location", "deadline",
        )
        for field_name in load_bearing:
            _, result = evaluate_detail("daad", "daad_detail.html", DAAD_URL, **{field_name: ""})
            self.assertNotEqual(
                result["match_status"], "strong_match",
                f"strong_match survived losing {field_name}",
            )
        _, result = evaluate_detail("daad", "daad_detail.html", DAAD_URL, destination="USA")
        self.assertNotEqual(result["match_status"], "strong_match")


class NegativeGoldenTests(unittest.TestCase):
    def test_partial_euro_award_stays_rejected(self):
        _, result = evaluate_detail(
            "nl_scholarship", "nl_detail.html", "https://www.studyinnl.org/finances/nl-scholarship"
        )
        self.assertEqual(result["funding_status"], "excluded")
        self.assertEqual(result["match_status"], "rejected")
        self.assertEqual(result["recommendation"], "exclude")

    def test_indian_only_tuition_only_usa_record_rejected_thrice(self):
        from my_actor.source_adapters.base import extract_text
        from my_actor.verification import extract_structured_fields

        fields = extract_structured_fields(extract_text((FIXTURES / "wms_live_card.html").read_text(encoding="utf-8")))
        result = evaluate_scholarship(
            title="Vanderbilt University Scholarship 2026",
            url="https://www.wemakescholars.com/scholarship/vanderbilt-university-scholarship",
            source_type="official_university", degree=fields["degree"], field=fields["field"],
            funding=fields["funding"], nationality=fields["nationality"],
            destination="USA", application_location=fields["application_location"],
            deadline=fields["deadline"], cgpa_requirements=fields["cgpa"],
            verification_status="verified", today=TODAY,
        )
        self.assertEqual(result["nationality_match"], "excluded")
        self.assertEqual(result["destination_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")
        self.assertEqual(result["recommendation"], "exclude")

    def test_provider_name_anchor_selects_official_page(self):
        url = select_official_url(
            "https://www.wemakescholars.com/scholarship/vanderbilt-university-scholarship",
            "Vanderbilt University",
            [
                LinkCandidate("https://www.facebook.com/wemakescholars", ""),
                LinkCandidate(
                    "https://engineering.vanderbilt.edu/academics/graduate/fellowships/",
                    "Vanderbilt University",
                ),
            ],
        )
        self.assertEqual(
            url, "https://engineering.vanderbilt.edu/academics/graduate/fellowships"
        )

    def test_generic_anchor_still_never_selects_official_page(self):
        self.assertIsNone(select_official_url(
            "https://www.wemakescholars.com/scholarships/example",
            "Example University",
            [LinkCandidate("https://example.edu/news", "Read more")],
        ))


if __name__ == "__main__":
    unittest.main()
