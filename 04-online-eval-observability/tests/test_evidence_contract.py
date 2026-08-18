import sys
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
if str(SECTION_DIR) not in sys.path:
    sys.path.insert(0, str(SECTION_DIR))

from evidence_contract import (  # noqa: E402
    EvidenceContractError,
    build_dataset_update_manifest,
    build_feedback_candidates,
    build_online_evidence_manifest,
    promote_feedback_candidates,
    runtime_log_groups,
    service_names,
    validate_no_sensitive_values,
)


class EvidenceContractTests(unittest.TestCase):
    def sample_deployment(self):
        return {
            "deployment_id": "section03-20260808T115332Z-4b1793c3",
            "runtime": {
                "runtime_id": "runtime-abc",
                "runtime_name": "product_agent",
                "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/runtime-abc",
            },
            "model_id": "model",
            "otel_service_name": "service-name",
            "agent_behavior": {"prompt_version": "p1"},
            "dataset_lineage": {"dataset_lineage_id": "lineage-1"},
            "observability": {
                "log_delivery": {
                    "log_group": "/aws/vendedlogs/bedrock-agentcore/runtime-abc"
                }
            },
        }

    def sample_dataset(self):
        return {
            "dataset_lineage_id": "lineage-1",
            "managed_datasets": {
                "predefined": {
                    "dataset_id": "dataset-1",
                    "baseline_dataset_version": "1",
                }
            },
        }

    def sample_batch(self):
        return {
            "batch_evaluation": {
                "batch_evaluation_id": "batch-1",
                "batch_evaluation_arn": "arn:batch",
                "evaluator_summaries": [
                    {"evaluator_id": "Builtin.Helpfulness", "average_score": 0.8}
                ],
            }
        }

    def test_runtime_log_groups_and_service_names(self):
        deployment = self.sample_deployment()
        self.assertEqual(
            runtime_log_groups(deployment),
            [
                "aws/spans",
                "/aws/bedrock-agentcore/runtimes/runtime-abc-DEFAULT",
                "/aws/vendedlogs/bedrock-agentcore/runtime-abc",
            ],
        )
        self.assertEqual(service_names(deployment), ["product_agent.DEFAULT"])

    def test_online_evidence_manifest_shape(self):
        manifest = build_online_evidence_manifest(
            deployment=self.sample_deployment(),
            dataset=self.sample_dataset(),
            batch_evaluation=self.sample_batch(),
            online_config={"online_evaluation_config_id": "cfg-1"},
            dashboard={"dashboard_name": "dash"},
            monitored_sessions=[],
            trace_summary={"span_count": 3},
            metric_summary={"status": "PENDING"},
            query_templates={"recent_spans": "SOURCE 'aws/spans'"},
        )
        self.assertEqual(manifest["artifact_type"], "section_04_online_evidence_manifest")
        self.assertTrue(manifest["status"]["online_config_ready"])
        self.assertTrue(manifest["status"]["trace_records_found"])
        self.assertEqual(
            manifest["release_candidate_batch_evaluation"]["batch_evaluation_id"],
            "batch-1",
        )

    def test_feedback_candidates_and_promotion(self):
        candidates = build_feedback_candidates(
            deployment=self.sample_deployment(),
            dataset=self.sample_dataset(),
            monitored_sessions=[
                {
                    "status": "success",
                    "session_id": "session-123456789012",
                    "actor_role": "customer",
                    "scenario_role": "recommendation_gap",
                    "prompt": "Recommend headphones",
                    "response": "Here is a recommendation",
                    "tools_used": ["get_product_recommendations"],
                }
            ],
            session_tools={"session-123456789012": ["get_product_recommendations"]},
        )
        self.assertEqual(candidates["candidate_count"], 1)
        promoted = promote_feedback_candidates(candidates)
        self.assertEqual(promoted["promoted_count"], 1)
        example = promoted["managed_dataset_examples"][0]
        self.assertEqual(example["expected_trajectory"]["toolNames"], ["get_product_recommendations"])
        self.assertEqual(example["metadata"]["source"], "section_04_production_feedback")

    def test_runtime_invocation_errors_are_not_promoted_to_dataset(self):
        candidates = build_feedback_candidates(
            deployment=self.sample_deployment(),
            dataset=self.sample_dataset(),
            monitored_sessions=[
                {
                    "status": "error",
                    "session_id": "session-123456789012",
                    "actor_role": "customer",
                    "scenario_role": "comparison_gap",
                    "prompt": "Compare two products",
                    "response": "ParamValidationError: invalid runtimeSessionId",
                    "tools_used": [],
                }
            ],
            session_tools={},
        )
        self.assertEqual(candidates["candidate_count"], 1)
        candidate = candidates["candidates"][0]
        self.assertFalse(candidate["recommended_for_promotion"])
        self.assertTrue(candidate["recommended_for_canary_investigation"])
        promoted = promote_feedback_candidates(candidates)
        self.assertEqual(promoted["promoted_count"], 0)

    def test_dataset_update_manifest_requires_version(self):
        promoted = {
            "promoted_count": 1,
            "managed_dataset_examples": [{"scenario_id": "s1"}],
            "review_decisions": [{"source_session_id": "session-1"}],
        }
        with self.assertRaises(EvidenceContractError):
            build_dataset_update_manifest(
                deployment=self.sample_deployment(),
                dataset=self.sample_dataset(),
                promoted_examples=promoted,
                prior_versions=[{"datasetVersion": "1"}],
                new_versions=[],
            )

    def test_sensitive_value_blocking(self):
        with self.assertRaises(EvidenceContractError):
            validate_no_sensitive_values({"authorization": "Bearer abc"})
        validate_no_sensitive_values({"model_id": "global.anthropic.claude-sonnet-5"})


if __name__ == "__main__":
    unittest.main()
