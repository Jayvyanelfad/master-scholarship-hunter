"""Orchestration regression tests: the production WMS-only scheduling bug.

These pin the default discovery schedule without a browser or network:
no sources input must schedule ALL enabled adapters, explicit selections
must be honoured, disabled sources must never run, and every scheduled
request must route to the adapter that owns it.
"""

import unittest

from my_actor.pipeline import find_adapter_for_url, plan_run, validate_discovery_config
from my_actor.source_adapters import build_adapters
from my_actor.sources import enabled_source_ids

WMS_LISTING = "https://www.wemakescholars.com/Masters-scholarships-in-computer-sciences-and-information-technology-to-study-abroad"
EXPECTED_ENABLED = {
    "wemakescholars", "erasmus_mundus", "daad", "vlir_uos", "chevening",
    "goi_ies", "mext", "mastercard_foundation", "nl_scholarship", "si_sweden",
    "finland", "norway", "switzerland", "austria", "australia",
}


def adapters():
    return build_adapters()


class OrchestrationTests(unittest.TestCase):
    def test_no_sources_input_schedules_all_enabled_adapters(self):
        plan = plan_run(sources_input=None, user_start_urls=[], adapters=adapters())
        self.assertEqual(set(plan.active_ids), EXPECTED_ENABLED)
        self.assertEqual(len(plan.active_ids), 15)

    def test_sources_all_schedules_all_enabled_adapters(self):
        plan = plan_run(sources_input=["all"], user_start_urls=[], adapters=adapters())
        self.assertEqual(set(plan.active_ids), EXPECTED_ENABLED)

    def test_single_source_selection(self):
        plan = plan_run(sources_input=["daad"], user_start_urls=[], adapters=adapters())
        self.assertEqual(plan.active_ids, ["daad"])
        self.assertTrue(all("daad.de" in url for url in plan.start_urls))

    def test_multi_source_selection(self):
        plan = plan_run(
            sources_input=["daad", "vlir_uos"], user_start_urls=[], adapters=adapters()
        )
        self.assertEqual(set(plan.active_ids), {"daad", "vlir_uos"})

    def test_disabled_source_cannot_be_scheduled(self):
        for disabled in ("eiffel", "canada", "denmark", "luxembourg", "singapore"):
            plan = plan_run(sources_input=[disabled], user_start_urls=[], adapters=adapters())
            self.assertEqual(plan.active_ids, [])
            self.assertEqual(plan.start_urls, [])
            self.assertTrue(plan.warnings)

    def test_unknown_source_id_warns_without_crashing(self):
        plan = plan_run(
            sources_input=["daad", "atlantis"], user_start_urls=[], adapters=adapters()
        )
        self.assertEqual(plan.active_ids, ["daad"])
        self.assertTrue(any("atlantis" in warning for warning in plan.warnings))

    def test_legacy_wms_start_url_still_works(self):
        plan = plan_run(
            sources_input=None, user_start_urls=[WMS_LISTING], adapters=adapters()
        )
        self.assertIn(WMS_LISTING, plan.start_urls)

    def test_wms_does_not_suppress_other_enabled_sources(self):
        plan = plan_run(
            sources_input=None, user_start_urls=[WMS_LISTING], adapters=adapters()
        )
        self.assertEqual(set(plan.active_ids), EXPECTED_ENABLED)
        self.assertGreater(plan.scheduled_total, 1)

    def test_every_discovery_request_routes_to_its_own_adapter(self):
        all_adapters = adapters()
        for adapter in all_adapters:
            if not adapter.enabled:
                continue
            for url in adapter.discovery_urls:
                routed = find_adapter_for_url(all_adapters, url, strict_domain=True)
                self.assertIsNotNone(routed, url)
                self.assertEqual(routed.source_id, adapter.source_id, url)

    def test_daad_record_is_not_claimed_by_erasmus(self):
        all_adapters = adapters()
        url = "https://www.daad.de/en/study-and-research-in-germany/scholarships/masters-computer-science/"
        routed = find_adapter_for_url(all_adapters, url, strict_domain=True)
        self.assertIsNotNone(routed)
        self.assertEqual(routed.source_id, "daad")

    def test_broken_adapter_does_not_stop_routing(self):
        class Broken:
            source_id = "broken"
            enabled = True
            official_domains = ("daad.de",)
            discovery_urls = ()

            def is_listing_url(self, url):
                raise RuntimeError("boom")

            def is_detail_url(self, url):
                raise RuntimeError("boom")

        all_adapters = [Broken(), *adapters()]
        routed = find_adapter_for_url(
            all_adapters,
            "https://www.daad.de/en/study-and-research-in-germany/scholarships/x/",
            strict_domain=True,
        )
        self.assertIsNotNone(routed)
        self.assertEqual(routed.source_id, "daad")

    def test_startup_counts_match_scheduled_requests(self):
        plan = plan_run(sources_input=None, user_start_urls=[], adapters=adapters())
        per_source_total = sum(len(urls) for urls in plan.per_source_urls.values())
        adapter_url_total = sum(
            len(plan.per_source_urls[source_id]) for source_id in plan.active_ids
        )
        self.assertEqual(per_source_total, adapter_url_total)
        self.assertEqual(plan.scheduled_total, len(plan.start_urls))
        # Every active adapter contributes at least one request.
        for source_id in plan.active_ids:
            self.assertGreaterEqual(len(plan.per_source_urls[source_id]), 1)

    def test_enabled_adapters_all_expose_valid_discovery_urls(self):
        for adapter in adapters():
            self.assertEqual(validate_discovery_config(adapter), [], adapter.source_id)

    def test_source_health_knows_every_enabled_source(self):
        self.assertEqual(set(enabled_source_ids()), EXPECTED_ENABLED)

    def test_dataset_records_preserve_source_identity(self):
        from my_actor.pipeline import assemble_record
        from my_actor.profile_rules import STUDENT_PROFILE

        record = assemble_record(
            evaluated={"match_status": "possible_match"}, source_id="daad",
            source_name="DAAD", source_domain="daad.de", source_type="official_government",
            title="Example", discovery_url="https://www.daad.de/record",
            official_url="https://www.daad.de/record", canonical_url="https://www.daad.de/record",
            official_source_domain="daad.de", official_source_type="official_government",
            verification_status="verified", discovery_fields={}, official_fields={},
            display_fields={}, student_profile=STUDENT_PROFILE,
            provenance=[{"source_id": "daad", "source_name": "DAAD",
                         "discovery_url": "https://www.daad.de/record", "role": "verification"}],
            discovery_timestamp="2026-01-01T00:00:00+00:00",
            verification_timestamp="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(record["source_id"], "daad")
        self.assertEqual(record["source_name"], "DAAD")
        self.assertEqual(record["source_provenance"][0]["source_id"], "daad")

    def test_full_discovery_loop_closes_per_adapter(self):
        """Simulate listing -> candidate -> routing for every enabled adapter."""
        all_adapters = adapters()
        single_page = {"goi_ies", "nl_scholarship"}
        for adapter in all_adapters:
            if not adapter.enabled:
                continue
            if adapter.source_id in single_page:
                # The discovery URL itself is the official detail page.
                for url in adapter.discovery_urls:
                    self.assertTrue(adapter.is_detail_url(url), url)
                    routed = find_adapter_for_url(all_adapters, url, strict_domain=True)
                    self.assertIsNotNone(routed, url)
                    self.assertEqual(routed.source_id, adapter.source_id, url)
                continue
            host = adapter.official_domains[0]
            if adapter.source_id == "wemakescholars":
                detail_url = f"https://{host}/scholarships/example-masters"
            elif adapter.source_id == "daad":
                detail_url = f"https://{host}/en/scholarships/example-masters/"
            elif adapter.source_id == "mastercard_foundation":
                detail_url = f"https://{host}/en/partners/where-to-apply"
            elif adapter.source_id == "mext":
                detail_url = f"https://{host}/en/mext-scholarship-guideline"
            elif adapter.source_id == "chevening":
                detail_url = f"https://{host}/scholarships/find-a-course/computer-science"
            else:
                detail_url = f"https://{host}/scholarships/example-masters-scholarship"
            listing_html = (
                f'<html><body><h1>Index</h1><a href="{detail_url}">'
                f"Example Master's scholarship programme</a></body></html>"
            )
            base = adapter.discovery_urls[0]
            result = adapter.parse_listing(listing_html, base)
            self.assertTrue(result.candidates, adapter.source_id)
            candidate_url = result.candidates[0].url
            routed = find_adapter_for_url(all_adapters, candidate_url, strict_domain=True)
            if routed is None:
                # Consortium-style pages on foreign domains use the fallback.
                routed = find_adapter_for_url(all_adapters, candidate_url, strict_domain=False)
            self.assertIsNotNone(routed, candidate_url)
            self.assertEqual(routed.source_id, adapter.source_id, candidate_url)


if __name__ == "__main__":
    unittest.main()
