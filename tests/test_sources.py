import unittest

from my_actor.sources import configured_sources, source_by_url


class SourceRegistryTests(unittest.TestCase):
    def test_only_supported_wms_discovery_source_is_enabled(self):
        self.assertEqual([source.identifier for source in configured_sources()], ["wemakescholars"])

    def test_source_matching_requires_a_real_domain_boundary(self):
        self.assertEqual(source_by_url("https://www.daad.de/en/").identifier, "daad")
        self.assertIsNone(source_by_url("https://notdaad.de/scholarships"))


if __name__ == "__main__":
    unittest.main()
