from datetime import date
import unittest

from my_actor.profile_rules import evaluate_scholarship


class ProfileRuleTests(unittest.TestCase):
    def evaluate(self, **changes):
        payload = {
            "title": "Computing Scholarship", "url": "https://example.edu/scholarship",
            "source_type": "official_program", "degree": "Master's", "field": "Computer Science",
            "funding": "Tuition fees and monthly living stipend", "nationality": "Open to all countries",
            "destination": "Germany", "application_location": "International applicants may apply from abroad",
            "deadline": "31 December 2030", "verification_status": "verified", "today": date(2030, 1, 1),
        }
        payload.update(changes)
        return evaluate_scholarship(**payload)

    def test_1_official_full_german_cs_is_strong(self):
        self.assertEqual(self.evaluate()["match_status"], "strong_match")

    def test_2_usa_is_rejected(self):
        self.assertEqual(self.evaluate(destination="USA")["match_status"], "rejected")

    def test_3_phd_only_is_rejected(self):
        self.assertEqual(self.evaluate(degree="PhD")["match_status"], "rejected")

    def test_4_education_is_rejected(self):
        self.assertEqual(self.evaluate(field="Education", destination="Canada")["match_status"], "rejected")

    def test_5_tuition_only_is_rejected(self):
        self.assertEqual(self.evaluate(funding="Tuition only")["match_status"], "rejected")

    def test_6_all_international_students_can_be_strong(self):
        result = self.evaluate(nationality="All international students")
        self.assertEqual(result["match_status"], "strong_match")
        self.assertEqual(result["nationality_match"], "eligible")

    def test_7_official_african_rule_can_be_strong(self):
        result = self.evaluate(nationality="Open to all African nationals")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["match_status"], "strong_match")

    def test_8_indian_nationals_only_is_rejected(self):
        self.assertEqual(self.evaluate(nationality="Indian nationals only")["match_status"], "rejected")

    def test_9_residency_requirement_is_rejected(self):
        self.assertEqual(self.evaluate(application_location="Applicants must already reside in Germany")["match_status"], "rejected")

    def test_10_full_label_without_benefits_is_not_strong(self):
        result = self.evaluate(funding="Fully funded scholarship")
        self.assertNotEqual(result["match_status"], "strong_match")
        self.assertEqual(result["funding_status"], "unknown")

    def test_11_destination_is_not_inferred_from_unrelated_country_text(self):
        result = self.evaluate(destination="USA", nationality="Open to all countries; unrelated news mentions Ireland")
        self.assertEqual(result["destination_match"], "excluded")
        self.assertEqual(result["destination"], "USA")

    def test_12_official_country_list_without_benin_is_rejected(self):
        result = self.evaluate(nationality="Australia Awards eligible countries: Ghana, Kenya, Nigeria")
        self.assertEqual(result["nationality_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")

    def test_13_explicit_benin_is_eligible(self):
        result = self.evaluate(nationality="Eligible countries: Benin, Ghana, Kenya")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["nationality_confidence"], "high")

    def test_14_international_without_abroad_rule_is_not_strong(self):
        result = self.evaluate(application_location="International students are welcome")
        self.assertEqual(result["application_from_abroad"], "unknown")
        self.assertNotEqual(result["match_status"], "strong_match")

    def test_institution_without_country_is_destination_unknown(self):
        result = self.evaluate(destination="Vanderbilt University")
        self.assertEqual(result["destination_match"], "unknown")
        self.assertEqual(result["match_status"], "possible_match")

    def test_medium_confidence_development_rule_is_not_strong(self):
        result = self.evaluate(nationality="Open to nationals of developing countries")
        self.assertEqual(result["nationality_match"], "eligible")
        self.assertEqual(result["nationality_confidence"], "medium")
        self.assertNotEqual(result["match_status"], "strong_match")

    def test_explicit_nationality_restriction_overrides_broad_wording(self):
        result = self.evaluate(nationality="Open to international students; Indian nationals only")
        self.assertEqual(result["nationality_match"], "excluded")

    def test_eu_nationals_only_is_rejected(self):
        result = self.evaluate(nationality="EU nationals only")
        self.assertEqual(result["nationality_match"], "excluded")

    def test_destination_residents_only_are_rejected(self):
        result = self.evaluate(application_location="Applicants must be resident in Germany")
        self.assertEqual(result["application_from_abroad"], "excluded")

    def test_structured_cgpa_below_profile_is_rejected(self):
        result = self.evaluate(cgpa_requirements="Minimum CGPA: 8/10")
        self.assertEqual(result["cgpa_match"], "excluded")
        self.assertEqual(result["match_status"], "rejected")


if __name__ == "__main__":
    unittest.main()
