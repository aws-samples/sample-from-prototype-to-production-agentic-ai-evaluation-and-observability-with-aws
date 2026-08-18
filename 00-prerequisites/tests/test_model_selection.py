import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SONNET_5_GLOBAL_MODEL_ID = "global.anthropic.claude-sonnet-5"
SONNET_5_BASE_MODEL_ID = "anthropic.claude-sonnet-5"
LEGACY_SONNET_46_TOKEN = "claude-sonnet-4-6"


class WorkshopModelSelectionTests(unittest.TestCase):
    def test_source_defaults_use_sonnet_5(self):
        agent_config = json.loads(
            (REPO_ROOT / "01-single-agent-prototype/config/agent_config.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            agent_config["model"]["model_id"],
            SONNET_5_GLOBAL_MODEL_ID,
        )

        source_expectations = {
            "00-prerequisites/verify_infrastructure.py": SONNET_5_BASE_MODEL_ID,
            "02-evaluation-baseline/custom_evaluators.py": SONNET_5_GLOBAL_MODEL_ID,
            "03-production-deployment/agents/product_catalog_agent.py": SONNET_5_GLOBAL_MODEL_ID,
            "03-production-deployment/03-production-deployment.ipynb": SONNET_5_GLOBAL_MODEL_ID,
            "scripts/run_evaluation.py": SONNET_5_GLOBAL_MODEL_ID,
            "README.md": SONNET_5_GLOBAL_MODEL_ID,
        }
        for relative_path, expected_model_id in source_expectations.items():
            with self.subTest(relative_path=relative_path):
                text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(expected_model_id, text)
                self.assertNotIn(LEGACY_SONNET_46_TOKEN, text)


if __name__ == "__main__":
    unittest.main()
