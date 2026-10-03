from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import unittest

from my_actor.profile_rules import evaluate_scholarship
from my_actor.verification import LinkCandidate, extract_structured_fields, merge_fields, select_official_url


FIXTURES = Path(__file__).with_name("fixtures")
WMS_URL = "https://www.wemakescholars.com/scholarships/example-computing"
OFFICIAL_URL = "https://example.edu/apply"


class FixtureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.links: list[LinkCandidate] = []
        self._href = ""
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._link_text = []

    def handle_data(self, data):
        self.parts.append(data)
        if self._href:
            self._link_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append(LinkCandidate(self._href, " ".join(self._link_text)))
            self._href = ""


def fixture(name: str) -> tuple[dict[str, str], list[LinkCandidate]]:
    parser = FixtureParser()
    parser.feed((FIXTURES / name).read_text(encoding="utf-8"))
    return extract_structured_fields(" ".join(parser.parts)), parser.links


def evaluate_official(fields: dict[str, str]):
    return evaluate_scholarship(
        title="Example Computing Masters Scholarship", url=OFFICIAL_URL,
        source_type="official_university", degree=fields["degree"], field=fields["field"],
        funding=fields["funding"], nationality=fields["nationality"],
        destination=fields["destination"], application_location=fields["application_location"],
        deadline=fields["deadline"], cgpa_requirements=fields["cgpa"],
        verification_status="verified", today=date(2030, 1, 1),
    )


class OfficialVerificationPipelineTests(unittest.TestCase):
    def test_wms_to_official_to_verified_strong_match(self):
        discovery, links = fixture("wms_detail.html")
        official_url = select_official_url(WMS_URL, discovery["provider"], links)
        official, _ = fixture("official_valid.html")
        merged = merge_fields(discovery, official)
        result = evaluate_official(official)

        self.assertEqual(official_url, OFFICIAL_URL)
        self.assertEqual(merged["funding"], "Tuition fees and monthly living stipend")
        self.assertEqual(result["verification_status"], "verified")
        self.assertEqual(result["funding_status"], "verified_full")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["destination_match"], "eligible")
        self.assertEqual(result["match_status"], "strong_match")
        self.assertEqual(result["recommendation"], "include")

    def test_official_tuition_only_overrides_wms_full_funding(self):
        official, _ = fixture("official_tuition_only.html")
        result = evaluate_official(official)
        self.assertEqual(result["funding_status"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_official_indian_nationality_rejects(self):
        official, _ = fixture("official_india_only.html")
        self.assertEqual(evaluate_official(official)["match_status"], "rejected")

    def test_official_phd_only_rejects(self):
        official, _ = fixture("official_phd.html")
        self.assertEqual(evaluate_official(official)["match_status"], "rejected")

    def test_official_unclear_funding_is_not_strong(self):
        official, _ = fixture("official_valid.html")
        official["funding"] = "Fully funded scholarship"
        self.assertNotEqual(evaluate_official(official)["match_status"], "strong_match")

    def test_official_usa_is_not_changed_by_unrelated_ireland_text(self):
        official, _ = fixture("official_valid.html")
        official["destination"] = "USA"
        result = evaluate_official(official)
        self.assertEqual(result["destination_match"], "excluded")

    def test_no_qualified_official_link_stays_unverified(self):
        self.assertIsNone(select_official_url(WMS_URL, "Example University", [LinkCandidate("https://www.facebook.com/example", "Official website")]))

    def test_unlabelled_provider_domain_is_not_assumed_official(self):
        self.assertIsNone(select_official_url(WMS_URL, "Example University", [LinkCandidate("https://example.edu/news", "Read more")]))

    def test_social_link_is_never_selected_when_official_link_exists(self):
        discovery, links = fixture("wms_detail.html")
        self.assertEqual(select_official_url(WMS_URL, discovery["provider"], links), OFFICIAL_URL)


if __name__ == "__main__":
    unittest.main()
