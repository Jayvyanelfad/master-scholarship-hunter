"""Regression tests for extracting unlabeled official-page evidence."""

from __future__ import annotations

import unittest

from my_actor.source_adapters.base import blank_fields, fill_prose_evidence, is_generic_info_page


class ProseEvidenceTests(unittest.TestCase):
    def test_fills_empty_degree_and_field_from_programme_title(self):
        fields = fill_prose_evidence(blank_fields(), "Applications are open.", "MSc Computer Science and Artificial Intelligence")
        self.assertIn("MSc", fields["degree"])
        self.assertIn("Computer Science", fields["field"])

    def test_extracts_benefit_nationality_application_and_deadline_sentences(self):
        page = (
            "The Master's degree in Computer Science is designed for international graduates. "
            "The scholarship covers full tuition fees and provides a monthly living allowance. "
            "Applicants from Benin and other Sub-Saharan African countries may apply. "
            "International applicants may apply from abroad through the online portal. "
            "The application deadline is 15 December 2026."
        )
        fields = fill_prose_evidence(blank_fields(), page, "Master of Computer Science Scholarship")
        self.assertIn("Master", fields["degree"])
        self.assertIn("Computer Science", fields["field"])
        self.assertIn("tuition", fields["funding"].lower())
        self.assertIn("living allowance", fields["funding"].lower())
        self.assertIn("Benin", fields["nationality"])
        self.assertIn("apply from abroad", fields["application_location"])
        self.assertIn("deadline", fields["deadline"].lower())

    def test_fallback_does_not_invent_destination(self):
        fields = fill_prose_evidence(blank_fields(), "Master's students receive a stipend.", "MSc Computing Scholarship")
        self.assertEqual(fields["destination"], "")

    def test_opening_date_is_not_misread_as_deadline(self):
        page = "The next application round will open on 1 February 2027."
        fields = fill_prose_evidence(blank_fields(), page, "Master's Computing Award")
        self.assertEqual(fields["deadline"], "")

    def test_generic_info_titles_stay_skipped_after_fallback(self):
        fields = fill_prose_evidence(
            blank_fields(),
            "Scholarships may cover tuition fees and living expenses for international students.",
            "Funding your studies",
        )
        self.assertTrue(is_generic_info_page("Funding your studies", fields))


if __name__ == "__main__":
    unittest.main()
