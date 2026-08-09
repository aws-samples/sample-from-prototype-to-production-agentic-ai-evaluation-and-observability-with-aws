import sys
import hashlib
import tempfile
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
if str(SECTION_DIR) not in sys.path:
    sys.path.insert(0, str(SECTION_DIR))

from optimization_contract import (  # noqa: E402
    OptimizationContractError,
    blocked_experiment,
    build_bundle_configuration,
    build_optimization_manifest,
    build_promotion_manifest,
    build_release_decision_report,
    build_treatment_behavior,
    build_tool_recommendation_inputs,
    combined_system_prompt,
    derive_insight_trace_window,
    detect_config_bundle_readiness,
    dry_run_target_canary_plan,
    extract_system_prompt_recommendation,
    extract_tool_description_recommendations,
    gateway_qualified_tool_name,
    has_completed_experiment_evidence,
    load_gateway_tool_descriptions,
    log_group_arns,
    observed_tool_names,
    plain_tool_name,
    require_config_bundle_ready,
    recommendation_safe_system_prompt,
    summarize_configuration_bundle_response,
    validate_evidence_alignment,
    validate_insights_gate,
    validate_no_sensitive_values,
    validate_recommendation_gate,
)
from ab_experiment import (  # noqa: E402
    ABExperimentError,
    build_ab_metric_review,
    create_ab_online_evaluation_config,
    create_config_bundle_ab_test,
    derive_config_bundle_ab_status,
    ensure_online_evaluation_alignment,
    finalize_ab_test_for_decision,
    flatten_ab_metric_rows,
    online_evaluation_alignment,
    require_ab_running,
    require_ab_trace_evidence,
    require_gateway_trace_delivery_ready,
    require_gateway_traffic_success,
    require_online_evaluation_ready,
    summarize_ab_test,
    summarize_gateway_response,
    summarize_online_evaluation_config,
    wait_for_ab_trace_evidence,
)


class OptimizationContractTests(unittest.TestCase):
    def sample_behavior(self):
        return {
            "prompt_version": "product-catalog-prompts-v1",
            "tool_policy_version": "product-catalog-tool-policy-v1",
            "tool_catalog_version": "product-catalog-tool-catalog-v1",
            "system_prompts": {
                "admin": "Admin prompt",
                "customer": "Customer prompt",
            },
            "tool_descriptions": {
                "search_products": "Search product catalog.",
                "update_inventory": "Adjust stock quantities.",
            },
        }

    def sample_evidence(self):
        return {
            "deployment": {
                "deployment_id": "section03-20260808T115332Z-4b1793c3",
                "runtime": {
                    "runtime_id": "runtime-1",
                    "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/runtime-1",
                },
                "image": {"tag": "rc-123"},
            },
            "dataset": {
                "dataset_lineage_id": "lineage-1",
                "managed_datasets": {
                    "predefined": {"baseline_dataset_version": "1"},
                }
            },
            "batch_evaluation": {
                "deployment_id": "section03-20260808T115332Z-4b1793c3",
                "dataset_lineage_id": "lineage-1",
                "batch_evaluation": {
                    "batch_evaluation_id": "batch-1",
                    "batch_evaluation_arn": "arn:aws:bedrock-agentcore:us-east-1:123:batch-evaluate/batch-1",
                    "status": "COMPLETED",
                    "evaluator_summaries": [
                        {"evaluator_id": "Builtin.Helpfulness", "average_score": 0.8}
                    ],
                }
            },
            "online_evidence": {
                "deployment_id": "section03-20260808T115332Z-4b1793c3",
                "dataset_lineage": {"dataset_lineage_id": "lineage-1"},
                "status": {
                    "online_config_ready": True,
                    "trace_records_found": True,
                },
            },
            "dataset_update": {
                "deployment_id": "section03-20260808T115332Z-4b1793c3",
                "dataset_lineage_id": "lineage-1",
                "updated_dataset_version": "2",
            },
            "production_feedback_candidates": {"candidate_count": 2},
            "promoted_feedback_examples": {"promoted_count": 1},
        }

    def test_combined_prompt_and_bundle_configuration(self):
        behavior = self.sample_behavior()
        combined = combined_system_prompt(behavior)
        self.assertIn("## admin", combined)
        self.assertIn("## customer", combined)
        safe_prompt = recommendation_safe_system_prompt(behavior)
        self.assertIn("product catalog assistant", safe_prompt)
        self.assertIn("Prompt version: product-catalog-prompts-v1", safe_prompt)
        config = build_bundle_configuration(behavior)
        self.assertEqual(config["prompt_version"], "product-catalog-prompts-v1")
        self.assertEqual(len(config["tool_descriptions"]), 2)

    def test_observed_tool_inputs_use_gateway_names(self):
        current = self.sample_behavior()["tool_descriptions"]
        online = {
            "monitored_sessions": [
                {
                    "tools_used_from_spans": ["ProductTools___search_products"],
                    "tools_used": ["update_inventory"],
                },
                {
                    "tools_used_from_spans": [],
                    "tools_used": ["check_inventory"],
                },
            ]
        }
        observed = observed_tool_names(online, current, limit=2)
        self.assertEqual(observed, ["search_products", "update_inventory"])
        self.assertEqual(
            gateway_qualified_tool_name("search_products"),
            "ProductTools___search_products",
        )
        self.assertEqual(plain_tool_name("ProductTools___search_products"), "search_products")
        inputs = build_tool_recommendation_inputs(current, observed)
        self.assertEqual(inputs[0]["toolName"], "ProductTools___search_products")
        self.assertEqual(inputs[0]["plain_tool_name"], "search_products")

    def test_load_gateway_tool_descriptions(self):
        descriptions = load_gateway_tool_descriptions()
        self.assertEqual(
            descriptions["check_inventory"],
            "Check inventory availability and stock quantity for a product",
        )
        inputs = build_tool_recommendation_inputs(
            descriptions,
            ["check_inventory", "compare_products", "get_product_details"],
        )
        self.assertEqual(inputs[0]["toolName"], "ProductTools___check_inventory")
        self.assertEqual(
            inputs[0]["toolDescription"]["text"],
            "Check inventory availability and stock quantity for a product",
        )

    def test_evidence_alignment_rejects_mismatched_deployment(self):
        validate_evidence_alignment(self.sample_evidence())
        bad = self.sample_evidence()
        bad["online_evidence"]["deployment_id"] = "other"
        with self.assertRaises(OptimizationContractError):
            validate_evidence_alignment(bad)

    def test_treatment_behavior_uses_recommendations_without_mutating_control(self):
        behavior = self.sample_behavior()
        treatment = build_treatment_behavior(
            behavior,
            recommended_system_prompt="Recommended combined prompt",
            recommended_tool_descriptions={"search_products": "Search by use case and budget."},
        )
        self.assertEqual(
            treatment["system_prompts"]["recommended_combined"],
            "Recommended combined prompt",
        )
        self.assertEqual(
            treatment["tool_descriptions"]["search_products"],
            "Search by use case and budget.",
        )
        self.assertEqual(
            behavior["tool_descriptions"]["search_products"],
            "Search product catalog.",
        )

    def test_detect_config_bundle_readiness_blocks_missing_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.py"
            path.write_text("from bedrock_agentcore.runtime import BedrockAgentCoreApp\n", encoding="utf-8")
            readiness = detect_config_bundle_readiness(path)
        self.assertFalse(readiness["supported"])
        with self.assertRaises(OptimizationContractError):
            require_config_bundle_ready(readiness)

    def test_detect_config_bundle_readiness_passes_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.py"
            path.write_text(
                "from bedrock_agentcore.runtime import BedrockAgentCoreContext\n"
                "BedrockAgentCoreContext.get_config_bundle()\n",
                encoding="utf-8",
            )
            readiness = detect_config_bundle_readiness(path, deployment_manifest={})
        self.assertTrue(readiness["source_supported"])
        self.assertFalse(readiness["supported"])
        with self.assertRaises(OptimizationContractError):
            require_config_bundle_ready(readiness)

    def test_detect_config_bundle_readiness_requires_deployment_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.py"
            path.write_text(
                "from bedrock_agentcore.runtime import BedrockAgentCoreContext\n"
                "BedrockAgentCoreContext.get_config_bundle()\n",
                encoding="utf-8",
            )
            readiness = detect_config_bundle_readiness(
                path,
                deployment_manifest={
                    "runtime": {
                        "config_bundle_hook_version": "1",
                        "config_bundle_source_sha256": hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest(),
                    },
                    "image": {"tag": "rc-123", "digest": "sha256:abc"},
                },
            )
        self.assertTrue(readiness["supported"])
        self.assertTrue(readiness["deployed_supported"])
        require_config_bundle_ready(readiness)

    def test_log_group_arns_and_response_summaries(self):
        self.assertEqual(
            log_group_arns(
                region="us-east-1",
                account_id="123456789012",
                log_group_names=["aws/spans", "/aws/runtime"],
            ),
            [
                "arn:aws:logs:us-east-1:123456789012:log-group:aws/spans",
                "arn:aws:logs:us-east-1:123456789012:log-group:/aws/runtime",
            ],
        )
        summary = summarize_configuration_bundle_response(
            {"bundleId": "b-1", "bundleArn": "arn:bundle", "versionId": "1"}
        )
        self.assertEqual(summary["bundle_id"], "b-1")

    def test_insight_trace_window_uses_section04_anchor(self):
        window = derive_insight_trace_window(
            {"created_at": "2026-08-08T20:55:09Z"},
            before_seconds=300,
            after_seconds=120,
        )
        self.assertEqual(window["start_time"].isoformat(), "2026-08-08T20:50:09+00:00")
        self.assertEqual(window["end_time"].isoformat(), "2026-08-08T20:57:09+00:00")

    def test_insights_gate_blocks_partial_jobs(self):
        gate = validate_insights_gate(
            {
                "status": "COMPLETED",
                "error_count": 0,
                "has_failure_analysis": False,
                "has_user_intent": True,
                "has_execution_summary": True,
                "evaluation_results": {
                    "numberOfSessionsCompleted": 5,
                    "numberOfSessionsFailed": 0,
                    "totalNumberOfSessions": 5,
                },
            }
        )
        self.assertEqual(gate["status"], "PASSED")

        with self.assertRaises(OptimizationContractError):
            validate_insights_gate(
                {
                    "status": "COMPLETED_WITH_ERRORS",
                    "error_count": 1,
                    "error_details": ["2 of 63 sessions failed during batch evaluation."],
                    "has_failure_analysis": True,
                    "has_user_intent": True,
                    "has_execution_summary": True,
                    "evaluation_results": {
                        "numberOfSessionsCompleted": 61,
                        "numberOfSessionsFailed": 2,
                        "totalNumberOfSessions": 63,
                    },
                }
            )

        with self.assertRaises(OptimizationContractError):
            validate_insights_gate(
                {
                    "status": "COMPLETED",
                    "error_count": 0,
                    "has_failure_analysis": False,
                    "has_user_intent": True,
                    "has_execution_summary": True,
                    "evaluation_results": {
                        "numberOfSessionsCompleted": 4,
                        "numberOfSessionsFailed": 1,
                        "totalNumberOfSessions": 5,
                    },
                }
            )

    def test_extract_recommendations(self):
        prompt = extract_system_prompt_recommendation(
            {
                "recommendationResult": {
                    "systemPromptRecommendationResult": {
                        "recommendedSystemPrompt": "Better prompt"
                    }
                }
            }
        )
        self.assertEqual(prompt, "Better prompt")
        tools = extract_tool_description_recommendations(
            {
                "recommendationResult": {
                    "toolDescriptionRecommendationResult": {
                        "tools": [
                            {
                                "toolName": "ProductTools___search_products",
                                "recommendedToolDescription": "Better search",
                            }
                        ]
                    }
                }
            },
            {"search_products": "Original"},
        )
        self.assertEqual(tools, {"search_products": "Better search"})

    def test_recommendation_gate_blocks_failed_jobs(self):
        gate = validate_recommendation_gate(
            {
                "system_prompt": {
                    "status": "COMPLETED",
                    "recommendation_id": "rec-1",
                    "has_candidate": True,
                },
                "tool_descriptions": {
                    "status": "COMPLETED",
                    "recommendation_id": "rec-2",
                    "has_candidate": True,
                },
            }
        )
        self.assertEqual(gate["status"], "PASSED")

        with self.assertRaises(OptimizationContractError):
            validate_recommendation_gate(
                {
                    "system_prompt": {
                        "status": "FAILED",
                        "recommendation_id": "rec-1",
                        "error_code": "ValidationException",
                        "has_candidate": False,
                    },
                    "tool_descriptions": {
                        "status": "COMPLETED",
                        "recommendation_id": "rec-2",
                        "has_candidate": True,
                    },
                }
            )

        with self.assertRaises(OptimizationContractError):
            validate_recommendation_gate(
                {
                    "system_prompt": {
                        "status": "COMPLETED",
                        "recommendation_id": "rec-1",
                        "has_candidate": False,
                    },
                    "tool_descriptions": {
                        "status": "COMPLETED",
                        "recommendation_id": "rec-2",
                        "has_candidate": True,
                    },
                }
            )

    def test_blocked_ab_and_dry_run_canary_shape(self):
        blocked = blocked_experiment(
            experiment_type="config_bundle_ab_test",
            reason="runtime hook missing",
            prerequisites=["BedrockAgentCoreContext.get_config_bundle()"],
            planned_variants=[{"name": "control", "weight": 50}],
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertFalse(blocked["promotion_allowed"])

        canary = dry_run_target_canary_plan(
            baseline_runtime={"runtime_id": "runtime-1"},
            candidate_runtime=None,
            ci_gate=None,
        )
        self.assertEqual(canary["status"], "DRY_RUN_NO_CANDIDATE_RUNTIME")
        self.assertEqual(canary["traffic_policy"], {"control": 90, "treatment": 10})

    def test_release_and_promotion_manifests_never_auto_promote(self):
        optimization = build_optimization_manifest(
            evidence=self.sample_evidence(),
            behavior=self.sample_behavior(),
            insights={"status": "COMPLETED"},
            recommendations={"system_prompt": {"status": "COMPLETED"}},
            bundle_readiness={"supported": False},
            configuration_bundles={},
            experiments={"config_bundle_ab_test": {"status": "BLOCKED"}},
        )
        report = build_release_decision_report(
            optimization_manifest=optimization,
            decision="continue",
            rationale="Need runtime hook before live config-bundle A/B.",
            residual_risks=["Treatment has not received live traffic."],
            next_steps=["Add config-bundle runtime hook and rerun Section 03 gate."],
        )
        self.assertFalse(report["promotion_allowed"])
        promotion = build_promotion_manifest(
            deployment=self.sample_evidence()["deployment"],
            release_decision=report,
        )
        self.assertFalse(promotion["promotion_executed"])
        self.assertEqual(promotion["status"], "SKIPPED_NO_PROMOTION")
        self.assertEqual(promotion["execution_mode"], "not_requested")

    def test_promote_decision_requires_completed_experiment_evidence(self):
        optimization = build_optimization_manifest(
            evidence=self.sample_evidence(),
            behavior=self.sample_behavior(),
            insights={"status": "COMPLETED"},
            recommendations={"system_prompt": {"status": "COMPLETED"}},
            bundle_readiness={"supported": False},
            configuration_bundles={},
            experiments={"config_bundle_ab_test": {"status": "BLOCKED"}},
        )
        self.assertFalse(has_completed_experiment_evidence(optimization["experiments"]))
        with self.assertRaises(OptimizationContractError):
            build_release_decision_report(
                optimization_manifest=optimization,
                decision="promote",
                rationale="Should be rejected.",
                residual_risks=[],
                next_steps=[],
            )

        optimization["experiments"] = {
            "config_bundle_ab_test": {
                "status": "COMPLETED_WITH_RESULTS",
                "promotion_allowed": True,
            }
        }
        self.assertTrue(has_completed_experiment_evidence(optimization["experiments"]))
        report = build_release_decision_report(
            optimization_manifest=optimization,
            decision="promote",
            rationale="Completed experiment passed.",
            residual_risks=[],
            next_steps=[],
        )
        self.assertTrue(report["promotion_allowed"])
        promotion = build_promotion_manifest(
            deployment=self.sample_evidence()["deployment"],
            release_decision=report,
        )
        self.assertFalse(promotion["promotion_executed"])
        self.assertEqual(promotion["execution_mode"], "manual_approval_required")

        executed = build_promotion_manifest(
            deployment=self.sample_evidence()["deployment"],
            release_decision=report,
            promotion_execution={
                "status": "PRODUCTION_TRAFFIC_SWITCHED",
                "promotion_executed": True,
                "execution_mode": "explicit_operator_approved",
                "execution_result": {
                    "bundle_id": "control",
                    "version_id": "2",
                    "production_traffic_switched": True,
                },
            },
        )
        self.assertTrue(executed["promotion_executed"])
        self.assertEqual(executed["status"], "PRODUCTION_TRAFFIC_SWITCHED")

        with self.assertRaises(OptimizationContractError):
            build_promotion_manifest(
                deployment=self.sample_evidence()["deployment"],
                release_decision=report,
                promotion_execution={
                    "status": "PROMOTED_CONFIG_BUNDLE",
                    "promotion_executed": True,
                    "execution_mode": "explicit_operator_approved",
                    "execution_result": {"bundle_id": "control", "version_id": "2"},
                },
            )

        with self.assertRaises(OptimizationContractError):
            build_promotion_manifest(
                deployment=self.sample_evidence()["deployment"],
                release_decision=report,
                promotion_execution={
                    "status": "PROMOTED_CONFIG_BUNDLE",
                    "promotion_executed": True,
                    "execution_mode": "manual_approval_required",
                },
            )

    def test_ab_test_summary_requires_analysis_metrics(self):
        summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "abTestArn": "arn:ab",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "results": {
                    "analysisTimestamp": "2026-08-08T00:00:00Z",
                    "evaluatorMetrics": [
                        {
                            "evaluatorArn": "arn:aws:bedrock-agentcore:::evaluator/Builtin.Helpfulness",
                            "controlStats": {"mean": 0.7, "sampleSize": 10},
                            "variantResults": [
                                {
                                    "variantName": "treatment",
                                    "mean": 0.84,
                                    "sampleSize": 10,
                                    "pValue": 0.03,
                                    "isSignificant": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )
        self.assertTrue(summary["has_results"])
        self.assertEqual(summary["metric_count"], 1)
        self.assertEqual(summary["derived_decision"], "COMPLETED_WITH_WINNER")
        self.assertEqual(summary["promotion_candidate"], "treatment")
        self.assertAlmostEqual(
            summary["evaluator_metrics"][0]["variant_results"][0]["percent_change"],
            20.0,
        )

        summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "results": {},
            }
        )
        self.assertFalse(summary["has_results"])
        self.assertEqual(summary["derived_decision"], "NO_RESULTS")

    def test_ab_test_summary_blocks_promotion_when_service_errors_exist(self):
        summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "errorDetails": [{"message": "variant scoring failed"}],
                "results": {
                    "analysisTimestamp": "2026-08-08T00:00:00Z",
                    "evaluatorMetrics": [
                        {
                            "evaluatorArn": "arn:aws:bedrock-agentcore:::evaluator/Builtin.Helpfulness",
                            "controlStats": {"mean": 0.7, "sampleSize": 10},
                            "variantResults": [
                                {
                                    "variantName": "treatment",
                                    "mean": 0.84,
                                    "sampleSize": 10,
                                    "pValue": 0.03,
                                    "isSignificant": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )
        self.assertTrue(summary["service_error"])
        self.assertEqual(summary["derived_decision"], "ERROR")
        self.assertIsNone(summary["promotion_candidate"])

        no_metric_summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "errorDetails": [{"message": "variant scoring failed before metrics"}],
                "results": {},
            }
        )
        self.assertFalse(no_metric_summary["has_results"])
        self.assertTrue(no_metric_summary["service_error"])
        self.assertEqual(no_metric_summary["derived_decision"], "ERROR")
        self.assertIsNone(no_metric_summary["promotion_candidate"])
        self.assertEqual(
            derive_config_bundle_ab_status(no_metric_summary, keep_ab_running=True),
            "ERROR",
        )
        self.assertEqual(
            derive_config_bundle_ab_status(no_metric_summary, keep_ab_running=False),
            "ERROR",
        )

    def test_config_bundle_ab_status_mapping_preserves_partial_no_result_states(self):
        no_results = {"derived_decision": "NO_RESULTS", "has_results": False}
        self.assertEqual(
            derive_config_bundle_ab_status(no_results, keep_ab_running=True),
            "RUNNING_NO_RESULTS_YET",
        )
        self.assertEqual(
            derive_config_bundle_ab_status(no_results, keep_ab_running=False),
            "TRAFFIC_ROUTED_NO_RESULTS_STOPPED",
        )
        winner = {"derived_decision": "COMPLETED_WITH_WINNER", "has_results": True}
        self.assertEqual(
            derive_config_bundle_ab_status(winner, keep_ab_running=True),
            "COMPLETED_WITH_WINNER",
        )

    def test_finalize_ab_test_stops_running_test_before_decision(self):
        class FakeABClient:
            def __init__(self):
                self.stopped = False
                self.calls = 0

            def get_ab_test(self, **kwargs):
                self.calls += 1
                if not self.stopped:
                    return {
                        "abTestId": kwargs["abTestId"],
                        "status": "ACTIVE",
                        "executionStatus": "RUNNING",
                        "results": {},
                    }
                return {
                    "abTestId": kwargs["abTestId"],
                    "status": "ACTIVE",
                    "executionStatus": "STOPPED",
                    "stoppedAt": "2026-08-09T03:19:17Z",
                    "results": {
                        "analysisTimestamp": "2026-08-09T03:20:00Z",
                        "evaluatorMetrics": [
                            {
                                "evaluatorId": "Builtin.Helpfulness",
                                "controlStats": {"mean": 0.7, "sampleSize": 10},
                                "variantResults": [
                                    {
                                        "variantName": "T1",
                                        "mean": 0.84,
                                        "sampleSize": 10,
                                        "isSignificant": True,
                                    }
                                ],
                            }
                        ],
                    },
                }

            def update_ab_test(self, **kwargs):
                self.stopped = kwargs["executionStatus"] == "STOPPED"
                return {
                    "abTestId": kwargs["abTestId"],
                    "status": "UPDATING",
                    "executionStatus": "STOPPED",
                }

        client = FakeABClient()
        result = finalize_ab_test_for_decision(
            client,
            "ab-1",
            stop_before_decision=True,
            post_stop_polls=1,
            poll_seconds=0,
        )
        self.assertTrue(result["finalization"]["stopped_by_notebook"])
        self.assertEqual(result["summary"]["execution_status"], "STOPPED")
        self.assertTrue(result["summary"]["has_results"])
        self.assertEqual(result["summary"]["derived_decision"], "COMPLETED_WITH_WINNER")

    def test_finalize_ab_test_stops_running_test_with_existing_metrics(self):
        class FakeABClient:
            def __init__(self):
                self.stopped = False

            def get_ab_test(self, **kwargs):
                return {
                    "abTestId": kwargs["abTestId"],
                    "status": "ACTIVE",
                    "executionStatus": "STOPPED" if self.stopped else "RUNNING",
                    "stoppedAt": "2026-08-09T07:31:21Z" if self.stopped else None,
                    "results": {
                        "analysisTimestamp": "2026-08-09T07:30:11Z",
                        "evaluatorMetrics": [
                            {
                                "evaluatorId": "Builtin.Helpfulness",
                                "controlStats": {"mean": 1.0, "sampleSize": 8},
                                "variantResults": [
                                    {
                                        "variantName": "T1",
                                        "mean": 1.0,
                                        "sampleSize": 2,
                                        "isSignificant": False,
                                    }
                                ],
                            }
                        ],
                    },
                }

            def update_ab_test(self, **kwargs):
                self.stopped = kwargs["executionStatus"] == "STOPPED"
                return {
                    "abTestId": kwargs["abTestId"],
                    "status": "UPDATING",
                    "executionStatus": "STOPPED",
                }

        result = finalize_ab_test_for_decision(
            FakeABClient(),
            "ab-1",
            stop_before_decision=True,
            post_stop_polls=1,
            poll_seconds=0,
        )
        self.assertTrue(result["finalization"]["stopped_by_notebook"])
        self.assertEqual(result["summary"]["execution_status"], "STOPPED")
        self.assertTrue(result["summary"]["has_results"])
        self.assertEqual(result["summary"]["metric_count"], 1)

    def test_finalize_ab_test_can_leave_running_for_inspection(self):
        class FakeABClient:
            def get_ab_test(self, **kwargs):
                return {
                    "abTestId": kwargs["abTestId"],
                    "status": "ACTIVE",
                    "executionStatus": "RUNNING",
                    "results": {},
                }

        result = finalize_ab_test_for_decision(
            FakeABClient(),
            "ab-1",
            stop_before_decision=False,
            post_stop_polls=1,
            poll_seconds=0,
        )
        self.assertFalse(result["finalization"]["stopped_by_notebook"])
        self.assertEqual(result["summary"]["execution_status"], "RUNNING")
        self.assertFalse(result["summary"]["has_results"])

    def test_ab_metric_review_explains_promotion_candidate(self):
        summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "results": {
                    "analysisTimestamp": "2026-08-08T00:00:00Z",
                    "evaluatorMetrics": [
                        {
                            "evaluatorArn": "arn:aws:bedrock-agentcore:::evaluator/Builtin.Helpfulness",
                            "controlStats": {"mean": 0.7, "sampleSize": 20},
                            "variantResults": [
                                {
                                    "variantName": "T1",
                                    "mean": 0.84,
                                    "sampleSize": 20,
                                    "pValue": 0.03,
                                    "isSignificant": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )
        rows = flatten_ab_metric_rows(summary, min_variant_sample_size=10)
        self.assertEqual(rows[0]["signal"], "significant_improvement")
        self.assertTrue(rows[0]["meets_min_sample_size"])

        review = build_ab_metric_review(summary, min_variant_sample_size=10)
        self.assertEqual(review["status"], "COMPLETED_WITH_WINNER")
        self.assertEqual(review["recommended_release_decision"], "promote")
        self.assertTrue(review["promotion_candidate_ready"])
        self.assertEqual(review["promotion_candidate"], "T1")

    def test_ab_metric_review_blocks_without_results_or_sample_size(self):
        no_results = build_ab_metric_review(
            {"has_results": False, "service_error": False},
            min_variant_sample_size=10,
        )
        self.assertEqual(no_results["status"], "NO_RESULTS")
        self.assertEqual(no_results["recommended_release_decision"], "continue")
        self.assertFalse(no_results["promotion_candidate_ready"])

        stopped_no_results = build_ab_metric_review(
            {
                "has_results": False,
                "service_error": False,
                "execution_status": "STOPPED",
                "stopped_at": "2026-08-09T03:19:17Z",
            },
            min_variant_sample_size=10,
        )
        self.assertEqual(stopped_no_results["status"], "NO_RESULTS_AFTER_STOP")
        self.assertIn("Do not promote", stopped_no_results["next_action"])
        self.assertFalse(stopped_no_results["promotion_candidate_ready"])

        low_sample_summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "results": {
                    "analysisTimestamp": "2026-08-08T00:00:00Z",
                    "evaluatorMetrics": [
                        {
                            "evaluatorId": "Builtin.Helpfulness",
                            "controlStats": {"mean": 0.7, "sampleSize": 3},
                            "variantResults": [
                                {
                                    "variantName": "T1",
                                    "mean": 0.84,
                                    "sampleSize": 3,
                                    "pValue": 0.03,
                                    "isSignificant": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )
        low_sample = build_ab_metric_review(low_sample_summary, min_variant_sample_size=10)
        self.assertEqual(low_sample["status"], "INSUFFICIENT_SAMPLE")
        self.assertFalse(low_sample["promotion_candidate_ready"])

    def test_ab_test_summary_flags_regression(self):
        summary = summarize_ab_test(
            {
                "abTestId": "ab-1",
                "status": "ACTIVE",
                "executionStatus": "RUNNING",
                "results": {
                    "analysisTimestamp": "2026-08-08T00:00:00Z",
                    "evaluatorMetrics": [
                        {
                            "evaluatorArn": "arn:aws:bedrock-agentcore:::evaluator/Builtin.GoalSuccessRate",
                            "controlStats": {"mean": 0.8},
                            "variantResults": [
                                {
                                    "variantName": "treatment",
                                    "mean": 0.6,
                                    "isSignificant": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )
        self.assertEqual(summary["derived_decision"], "REGRESSION")
        self.assertEqual(len(summary["regressions"]), 1)
        review = build_ab_metric_review(summary)
        self.assertEqual(review["status"], "REGRESSION")
        self.assertEqual(review["recommended_release_decision"], "investigate")
        self.assertFalse(review["promotion_candidate_ready"])

    def test_ab_runtime_and_traffic_gates(self):
        class FakeResponse:
            def __init__(self, status_code, text):
                self.status_code = status_code
                self.text = text

        require_ab_running({"status": "ACTIVE", "executionStatus": "RUNNING"})
        with self.assertRaises(ABExperimentError):
            require_ab_running({"status": "ACTIVE", "executionStatus": "PAUSED"})
        with self.assertRaises(ABExperimentError):
            require_ab_running(
                {
                    "status": "ACTIVE",
                    "executionStatus": "RUNNING",
                    "errorDetails": [{"message": "bad"}],
                }
            )

        require_gateway_traffic_success({"success": 2, "failed": 0}, expected_count=2)
        with self.assertRaises(ABExperimentError):
            require_gateway_traffic_success({"success": 1, "failed": 1}, expected_count=2)

        success = summarize_gateway_response(
            FakeResponse(
                200,
                '{"status":"success","metadata":{"role":"customer","tools_used":["get_product_details"],"tools_available":6}}',
            )
        )
        self.assertTrue(success["ok"])
        self.assertEqual(success["runtime_status"], "success")
        self.assertEqual(success["tools_used"], ["get_product_details"])

        runtime_error = summarize_gateway_response(
            FakeResponse(200, '{"status":"error","error":"RuntimeError: see logs"}')
        )
        self.assertFalse(runtime_error["ok"])
        self.assertTrue(runtime_error["transport_ok"])
        self.assertEqual(runtime_error["runtime_status"], "error")

    def test_config_bundle_ab_uses_agentcore_variant_names(self):
        class FakeDataClient:
            def __init__(self):
                self.kwargs = None

            def create_ab_test(self, **kwargs):
                self.kwargs = kwargs
                return {"abTestId": "ab-1"}

        client = FakeDataClient()
        response = create_config_bundle_ab_test(
            client,
            name="EcommerceBundleABTest",
            gateway_arn="arn:gateway",
            role_arn="arn:role",
            online_evaluation_config_arn="arn:online-eval",
            control_bundle={"bundle_arn": "arn:control", "version_id": "1"},
            treatment_bundle={"bundle_arn": "arn:treatment", "version_id": "2"},
        )
        self.assertEqual(response["abTestId"], "ab-1")
        self.assertEqual(
            [variant["name"] for variant in client.kwargs["variants"]],
            ["C", "T1"],
        )

    def test_online_evaluation_readiness_gate(self):
        config = {
            "onlineEvaluationConfigId": "cfg-1",
            "onlineEvaluationConfigArn": "arn:cfg",
            "status": "ACTIVE",
            "executionStatus": "ENABLED",
            "dataSourceConfig": {
                "cloudWatchLogs": {
                    "logGroupNames": ["aws/spans"],
                    "serviceNames": ["product-agent"],
                }
            },
            "evaluators": [{"evaluatorId": "Builtin.Helpfulness"}],
        }
        summary = summarize_online_evaluation_config(config)
        self.assertEqual(summary["evaluator_ids"], ["Builtin.Helpfulness"])
        require_online_evaluation_ready(config)
        require_online_evaluation_ready(
            config,
            required_service_names=["product-agent"],
            required_log_group_names=["aws/spans"],
        )
        with self.assertRaises(ABExperimentError):
            require_online_evaluation_ready(
                config,
                required_service_names=["product_agent.DEFAULT"],
            )
        with self.assertRaises(ABExperimentError):
            require_online_evaluation_ready({**config, "status": "CREATING"})

    def test_online_evaluation_alignment_reports_missing_endpoint_service(self):
        config = {
            "dataSourceConfig": {
                "cloudWatchLogs": {
                    "logGroupNames": ["aws/spans"],
                    "serviceNames": ["product-agent"],
                }
            }
        }
        alignment = online_evaluation_alignment(
            config,
            required_service_names=["product-agent", "product_agent.DEFAULT"],
            required_log_group_names=["aws/spans"],
        )
        self.assertFalse(alignment["aligned"])
        self.assertEqual(alignment["missing_service_names"], ["product_agent.DEFAULT"])

    def test_ensure_online_evaluation_alignment_updates_live_config(self):
        class FakeControlClient:
            def __init__(self):
                self.updated = None
                self.current = {
                    "onlineEvaluationConfigId": "cfg-1",
                    "status": "ACTIVE",
                    "executionStatus": "ENABLED",
                    "description": "config",
                    "rule": {"samplingConfig": {"samplingPercentage": 100.0}},
                    "evaluators": [{"evaluatorId": "Builtin.Helpfulness"}],
                    "evaluationExecutionRoleArn": "arn:role",
                    "dataSourceConfig": {
                        "cloudWatchLogs": {
                            "logGroupNames": ["aws/spans"],
                            "serviceNames": ["product-agent"],
                        }
                    },
                }

            def update_online_evaluation_config(self, **kwargs):
                self.updated = kwargs
                self.current["dataSourceConfig"] = kwargs["dataSourceConfig"]
                return {"onlineEvaluationConfigId": self.current["onlineEvaluationConfigId"]}

            def get_online_evaluation_config(self, **kwargs):
                return self.current

        client = FakeControlClient()
        result = ensure_online_evaluation_alignment(
            client,
            client.current,
            required_service_names=["product-agent", "product_agent.DEFAULT"],
            required_log_group_names=["aws/spans", "/aws/vendedlogs/runtime"],
        )
        self.assertTrue(result["updated"])
        cloudwatch = client.updated["dataSourceConfig"]["cloudWatchLogs"]
        self.assertEqual(
            cloudwatch["serviceNames"],
            ["product_agent.DEFAULT"],
        )
        self.assertEqual(
            cloudwatch["logGroupNames"],
            ["aws/spans", "/aws/vendedlogs/runtime"],
        )

    def test_ab_specific_online_evaluation_config_shape(self):
        class FakeControlClient:
            def __init__(self):
                self.created = None

            def create_online_evaluation_config(self, **kwargs):
                self.created = kwargs
                return {
                    "onlineEvaluationConfigId": "cfg-ab",
                    "onlineEvaluationConfigArn": "arn:cfg-ab",
                }

            def get_online_evaluation_config(self, **kwargs):
                return {
                    "onlineEvaluationConfigId": kwargs["onlineEvaluationConfigId"],
                    "onlineEvaluationConfigArn": "arn:cfg-ab",
                    "status": "ACTIVE",
                    "executionStatus": "ENABLED",
                    "dataSourceConfig": self.created["dataSourceConfig"],
                    "evaluators": self.created["evaluators"],
                }

        client = FakeControlClient()
        summary = create_ab_online_evaluation_config(
            client,
            name="Section05ABEval",
            description="A/B eval",
            log_group_names=["aws/spans", "/aws/runtime"],
            service_names=["product_agent.DEFAULT"],
            evaluation_execution_role_arn="arn:role",
        )
        self.assertEqual(summary["online_evaluation_config_id"], "cfg-ab")
        self.assertEqual(summary["source"], "section05_ab_specific")
        self.assertEqual(
            client.created["dataSourceConfig"]["cloudWatchLogs"]["serviceNames"],
            ["product_agent.DEFAULT"],
        )
        self.assertEqual(
            [item["evaluatorId"] for item in client.created["evaluators"]],
            ["Builtin.GoalSuccessRate", "Builtin.Helpfulness"],
        )
        self.assertEqual(client.created["rule"]["sessionConfig"]["sessionTimeoutMinutes"], 1)

    def test_ab_trace_evidence_requires_model_spans_and_bundle_fetch(self):
        require_ab_trace_evidence(
            {
                "model_span_sessions": 1,
                "mcp_400_sessions": 0,
                "bundle_access_denied_sessions": 0,
                "bundle_fetch_sessions": 1,
            }
        )
        with self.assertRaises(ABExperimentError):
            require_ab_trace_evidence(
                {
                    "model_span_sessions": 1,
                    "mcp_400_sessions": 0,
                    "bundle_access_denied_sessions": 0,
                    "bundle_fetch_sessions": 0,
                }
            )
        with self.assertRaises(ABExperimentError):
            require_ab_trace_evidence(
                {
                    "model_span_sessions": 0,
                    "mcp_400_sessions": 0,
                    "bundle_access_denied_sessions": 0,
                    "bundle_fetch_sessions": 1,
                }
            )

    def test_gateway_trace_delivery_ready_gate(self):
        require_gateway_trace_delivery_ready({"status": "READY", "warnings": []})
        with self.assertRaises(ABExperimentError):
            require_gateway_trace_delivery_ready(
                {"status": "PARTIAL", "warnings": ["delivery:AccessDeniedException"]}
            )

    def test_sensitive_values_blocked(self):
        with self.assertRaises(OptimizationContractError):
            validate_no_sensitive_values({"authorization": "Bearer abc"})
        fake_access_key = "".join(["A", "KIA", "ABCDEFGHIJKLMNOP"])
        with self.assertRaises(OptimizationContractError):
            validate_no_sensitive_values({"note": fake_access_key})
        validate_no_sensitive_values({"model_id": "global.anthropic.claude-sonnet-4-6"})


if __name__ == "__main__":
    unittest.main()
