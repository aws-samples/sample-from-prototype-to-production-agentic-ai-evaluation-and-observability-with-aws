import sys
import tempfile
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SECTION_DIR))

from workshop_state import (
    create_workshop_state,
    load_workshop_state,
    record_verification_results,
)


class WorkshopStateTests(unittest.TestCase):
    def test_verification_update_preserves_unknown_nested_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "workshop_state.json"
            create_workshop_state(
                {
                    "verification": {
                        "custom_note": "keep",
                        "required_checks": {
                            "aws_identity": {"ok": False, "old": True},
                            "ssm_parameters": {"ok": False, "stale": True},
                            "custom_required": {"keep": True},
                        },
                        "advanced_checks": {
                            "s3": {"ok": False, "old": True},
                            "agentcore_runtime": {"ok": False, "stale": True},
                            "custom_advanced": {"keep": True},
                        },
                    },
                    "advanced_capability_checks": {
                        "custom_note": "keep",
                        "summary": {"custom_summary": "keep", "warnings": 99},
                        "results": {
                            "s3": {"ok": False, "old": True},
                            "agentcore_runtime": {"ok": False, "stale": True},
                            "custom_result": {"keep": True},
                        },
                    },
                },
                state_path,
            )

            record_verification_results(
                account_id="123456789012",
                region="us-west-2",
                prefix="ecommerce-workshop",
                required_checks={"aws_identity": {"ok": True}},
                advanced_checks={"s3": {"ok": False, "status": "warning"}},
                advanced_required=False,
                path=state_path,
            )

            state = load_workshop_state(state_path)
            verification = state["verification"]
            advanced = state["advanced_capability_checks"]

            self.assertEqual(verification["custom_note"], "keep")
            self.assertEqual(verification["required_checks"]["aws_identity"]["ok"], True)
            self.assertNotIn("ssm_parameters", verification["required_checks"])
            self.assertEqual(
                verification["required_checks"]["custom_required"]["keep"],
                True,
            )
            self.assertEqual(verification["advanced_checks"]["s3"]["status"], "warning")
            self.assertNotIn("agentcore_runtime", verification["advanced_checks"])
            self.assertEqual(
                verification["advanced_checks"]["custom_advanced"]["keep"],
                True,
            )

            self.assertEqual(advanced["custom_note"], "keep")
            self.assertEqual(advanced["summary"]["custom_summary"], "keep")
            self.assertEqual(advanced["summary"]["warnings"], 1)
            self.assertEqual(advanced["results"]["s3"]["status"], "warning")
            self.assertNotIn("agentcore_runtime", advanced["results"])
            self.assertEqual(advanced["results"]["custom_result"]["keep"], True)

    def test_advanced_summary_distinguishes_warning_and_required_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "workshop_state.json"
            create_workshop_state(path=state_path)

            record_verification_results(
                account_id="123456789012",
                region="us-west-2",
                prefix="ecommerce-workshop",
                required_checks={"dynamodb_tables": {"ok": True}},
                advanced_checks={"iam": {"ok": False, "status": "warning"}},
                advanced_required=False,
                path=state_path,
            )
            state = load_workshop_state(state_path)
            summary = state["advanced_capability_checks"]["summary"]
            self.assertEqual(summary["required"], False)
            self.assertEqual(summary["warnings"], 1)
            self.assertEqual(summary["failed"], 0)

            record_verification_results(
                account_id="123456789012",
                region="us-west-2",
                prefix="ecommerce-workshop",
                required_checks={"dynamodb_tables": {"ok": True}},
                advanced_checks={"iam": {"ok": False, "status": "failed"}},
                advanced_required=True,
                path=state_path,
            )
            state = load_workshop_state(state_path)
            summary = state["advanced_capability_checks"]["summary"]
            self.assertEqual(summary["required"], True)
            self.assertEqual(summary["warnings"], 0)
            self.assertEqual(summary["failed"], 1)


if __name__ == "__main__":
    unittest.main()
