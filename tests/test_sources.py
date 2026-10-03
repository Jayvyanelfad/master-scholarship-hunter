import unittest

from my_actor.sources import configured_sources, enabled_source_ids, source_by_url, status_table


class SourceRegistryTests(unittest.TestCase):
    def test_production_default_uses_enabled_adapters(self):
        # Behaviour change vs the single-source era: the production default
        # is every enabled adapter, not WeMakeScholars alone.
        default = [source.identifier for source in configured_sources()]
        self.assertIn("wemakescholars", default)
        self.assertIn("erasmus_mundus", default)
        self.assertIn("daad", default)
        self.assertIn("vlir_uos", default)
        self.assertIn("chevening", default)
        self.assertIn("goi_ies", default)
        self.assertIn("mext", default)
        self.assertIn("mastercard_foundation", default)
        self.assertIn("nl_scholarship", default)
        self.assertEqual(default, enabled_source_ids())

    def test_explicit_selection_is_respected(self):
        self.assertEqual(
            [source.identifier for source in configured_sources(["daad", "goi_ies"])],
            ["daad", "goi_ies"],
        )
        self.assertEqual(configured_sources(["unknown-source"]), [])

    def test_unverifiable_sources_stay_disabled_with_reasons(self):
        table = {entry["source_id"]: entry for entry in status_table()}
        for source_id in ("eiffel", "canada", "denmark", "luxembourg", "singapore"):
            self.assertEqual(table[source_id]["status"], "disabled")
            self.assertTrue(table[source_id]["reason"])
        self.assertNotIn("eiffel", enabled_source_ids())

    def test_source_matching_requires_a_real_domain_boundary(self):
        self.assertEqual(source_by_url("https://www.daad.de/en/").identifier, "daad")
        self.assertIsNone(source_by_url("https://notdaad.de/scholarships"))


if __name__ == "__main__":
    unittest.main()
