import sys
import unittest
from copy import deepcopy
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SECTION_DIR))

from dataset_contract import (
    managed_dataset_source,
    postdeploy_ground_truth_from_examples,
    predefined_example_from_record,
    simulation_example_from_record,
)
from deployment_contract import reference_inputs_kwargs


class DatasetPayloadTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "source_test_case_id": "TC-DETAILS-001",
            "input": "Describe PROD-001",
            "expected_output": "A wireless product",
            "expected_tool_trajectory": {"expected_tool": "get_product_details"},
            "role": "customer",
            "category": "product_lookup",
            "assertions": {"expected_behavior": "allow"},
        }
        self.example = predefined_example_from_record(self.record, {})

    def test_fixed_inline_payload_uses_string_ground_truth(self):
        source = managed_dataset_source([self.example])
        example = source["inlineExamples"]["examples"][0]

        self.assertTrue(example["assertions"])
        self.assertTrue(all(isinstance(item, str) for item in example["assertions"]))
        self.assertEqual(example["expected_trajectory"], ["get_product_details"])
        self.assertEqual(
            example["turns"][0]["expected_response"], self.record["expected_output"]
        )

    def test_dynamic_inline_payload_uses_string_assertions(self):
        source = managed_dataset_source([simulation_example_from_record(self.record)])
        example = source["inlineExamples"]["examples"][0]

        self.assertTrue(example["assertions"])
        self.assertTrue(all(isinstance(item, str) for item in example["assertions"]))
        self.assertNotIn("turns", example)
        self.assertEqual(example["actor_profile"]["goal"], self.record["input"])

    def test_local_ground_truth_preserves_both_payload_formats(self):
        legacy_example = deepcopy(self.example)
        legacy_example["expected_trajectory"] = {
            "toolNames": legacy_example["expected_trajectory"]
        }
        legacy_example["assertions"] = [
            {"text": text} for text in legacy_example["assertions"]
        ]
        current = postdeploy_ground_truth_from_examples([self.example], {})
        legacy = postdeploy_ground_truth_from_examples([legacy_example], {})

        self.assertEqual(current["scenarios"], legacy["scenarios"])
        kwargs = reference_inputs_kwargs(current["scenarios"][0])
        self.assertEqual(kwargs["assertions"], self.example["assertions"])
        self.assertEqual(kwargs["expected_trajectory"], ["get_product_details"])
        self.assertEqual(kwargs["expected_response"], self.record["expected_output"])

    def test_local_ground_truth_handles_mixed_assertion_formats(self):
        self.example["assertions"] = [
            "Current assertion",
            {"text": "Legacy assertion"},
            "",
            {},
        ]
        artifact = postdeploy_ground_truth_from_examples([self.example], {})

        self.assertEqual(
            artifact["scenarios"][0]["assertions"],
            ["Current assertion", "Legacy assertion"],
        )


if __name__ == "__main__":
    unittest.main()
