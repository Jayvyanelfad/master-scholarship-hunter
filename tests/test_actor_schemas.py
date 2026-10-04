"""Regression tests for Apify schema files.

Production build 0.0.36 failed dataset-schema validation with:
  instancePath "/fields/title", keyword "type", message "must be string".
Root cause: Apify requires ``fields`` to be a JSON-Schema object
(``{"type": "object", "properties": {...}}``). A flat map of field
definitions puts field names such as ``title`` where JSON Schema only
allows its own annotation keywords (``title`` must be a string), so any
field named like a JSON-Schema keyword breaks the build. These tests pin
the conforming shape for every field, not just ``title``.
"""

import json
from pathlib import Path
import unittest

ACTOR_DIR = Path(__file__).resolve().parent.parent / ".actor"

ALLOWED_TYPES = {"string", "integer", "number", "boolean", "array", "object", "null"}


def load(name: str) -> dict:
    return json.loads((ACTOR_DIR / name).read_text(encoding="utf-8"))


class DatasetSchemaTests(unittest.TestCase):
    def test_fields_is_a_json_schema_object(self):
        doc = load("dataset_schema.json")
        self.assertEqual(doc["actorSpecification"], 1)
        self.assertEqual(doc["fields"]["type"], "object")
        self.assertIsInstance(doc["fields"]["properties"], dict)

    def test_every_field_type_is_a_single_string(self):
        # This is the exact rule Apify enforced: a union such as
        # ["string", "null"], an array, or an object fails validation.
        properties = load("dataset_schema.json")["fields"]["properties"]
        self.assertGreater(len(properties), 0)
        for name, definition in properties.items():
            self.assertIsInstance(definition, dict, name)
            self.assertIn("type", definition, name)
            self.assertIsInstance(definition["type"], str, name)
            self.assertIn(definition["type"], ALLOWED_TYPES, name)

    def test_expected_evidence_fields_present(self):
        properties = load("dataset_schema.json")["fields"]["properties"]
        for name in (
            "title", "url", "discovery_url", "official_url", "source_id",
            "source_name", "source_provenance", "verification_status",
            "funding", "funding_status", "nationality_match", "destination",
            "match_status", "recommendation", "residence_match",
            "profile_requirements_missing", "discovery_timestamp",
            "verification_timestamp",
        ):
            self.assertIn(name, properties)

    def test_title_field_is_a_plain_string_field(self):
        title = load("dataset_schema.json")["fields"]["properties"]["title"]
        self.assertEqual(title["type"], "string")

    def test_views_reference_only_defined_fields(self):
        doc = load("dataset_schema.json")
        properties = doc["fields"]["properties"]
        for view_name, view in doc["views"].items():
            for field_name in view["transformation"]["fields"]:
                self.assertIn(field_name, properties, f"{view_name}:{field_name}")
            for field_name in view["display"]["properties"]:
                self.assertIn(field_name, view["transformation"]["fields"])

    def test_actor_json_references_resolve(self):
        actor = load("actor.json")
        for key in ("inputSchema", "outputSchema"):
            self.assertTrue((ACTOR_DIR / actor[key].lstrip("./")).exists(), key)
        dataset_ref = actor["storages"]["dataset"].lstrip("./")
        self.assertTrue((ACTOR_DIR / dataset_ref).exists())

    def test_input_schema_fields_have_titles_types_descriptions(self):
        schema = load("input_schema.json")
        for name, definition in schema["properties"].items():
            self.assertIn("title", definition, name)
            self.assertIn("type", definition, name)
            self.assertIn("description", definition, name)


if __name__ == "__main__":
    unittest.main()
