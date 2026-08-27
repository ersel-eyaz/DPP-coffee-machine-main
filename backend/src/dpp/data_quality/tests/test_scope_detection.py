"""Tests for diagnostic behavior during automatic scope detection."""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from dpp.routers.data_quality import _detect_scope


class ScopeDetectionTests(unittest.TestCase):
    def test_unknown_entity_type_is_included_in_detection_error(self) -> None:
        document = {
            "@graph": [
                {
                    "@id": "instance-001",
                    "@type": "dpp:DPPInstnce",
                }
            ]
        }

        with self.assertRaises(HTTPException) as context:
            _detect_scope(document)

        self.assertEqual(400, context.exception.status_code)
        self.assertIn("Encountered entity types: 'DPPInstnce'", context.exception.detail)
        self.assertIn("Correct unsupported model type names", context.exception.detail)

    def test_shared_entity_types_are_included_in_detection_error(self) -> None:
        document = {
            "@graph": [
                {
                    "@id": "part-001",
                    "@type": "dpp:PartInstance",
                }
            ]
        }

        with self.assertRaises(HTTPException) as context:
            _detect_scope(document)

        self.assertEqual(400, context.exception.status_code)
        self.assertIn("shared entity types only", context.exception.detail)
        self.assertIn("Encountered entity types: 'PartInstance'", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
