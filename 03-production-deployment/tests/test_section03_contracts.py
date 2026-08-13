import ast
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SECTION_DIR))

from dataset_contract import (
    DatasetContractError,
    PREDEFINED_SCHEMA,
    SIMULATED_SCHEMA,
    assert_managed_dataset_ready,
    build_local_dataset_artifacts,
    dataset_client_preflight,
    managed_dataset_source,
    validate_no_sensitive_values as validate_dataset_safety,
    write_local_dataset_artifacts,
)
from deployment_contract import (
    DeploymentContractError,
    assert_dataset_manifest_ready,
    batch_dataset_from_ground_truth,
    build_batch_evaluation_manifest,
    build_release_metadata_env,
    build_data_protection_policy,
    build_deployment_manifest,
    ecr_image_evidence,
    endpoint_otel_service_name,
    evaluator_ids_for_scenario,
    gate_policy_for_evaluator,
    gateway_qualified_tool_names,
    load_postdeploy_gate_config,
    make_deployment_id,
    POSTDEPLOY_GATE_CONFIG_PATH,
    reference_inputs_kwargs,
    scenario_runtime_payload,
    summarize_postdeploy_scores,
    validate_batch_evaluation_manifest,
    validate_safe_trace_attributes,
)


class Section03DatasetContractTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = build_local_dataset_artifacts(
            region="us-east-1",
            account_id="123456789012",
        )

    def test_section02_evidence_becomes_predefined_and_simulated_artifacts(self):
        manifest = self.artifacts["dataset_manifest"]
        ground_truth = self.artifacts["postdeploy_ground_truth"]
        simulation = self.artifacts["postdeploy_simulation_scenarios"]

        self.assertEqual(ground_truth["schema_type"], PREDEFINED_SCHEMA)
        self.assertEqual(simulation["schema_type"], SIMULATED_SCHEMA)
        self.assertEqual(manifest["example_counts"]["predefined"], 4)
        self.assertEqual(manifest["example_counts"]["simulated"], 5)
        self.assertEqual(manifest["example_counts"]["excluded_from_predefined"], 10)
        self.assertEqual(manifest["example_counts"]["deferred_from_predefined"], 1)
        self.assertEqual(
            manifest["source_section02"]["dataset_version"],
            "2.1",
        )

    def test_multiturn_case_is_simulation_until_runtime_memory_exists(self):
        ground_truth = self.artifacts["postdeploy_ground_truth"]["scenarios"]
        simulation = self.artifacts["postdeploy_simulation_scenarios"]["scenarios"]
        manifest = self.artifacts["dataset_manifest"]

        self.assertNotIn(
            "TC-MULTI-001",
            {s["source_test_case_id"] for s in ground_truth},
        )

        multi_turn = next(
            s for s in simulation if s["metadata"]["source_test_case_id"] == "TC-MULTI-001"
        )
        self.assertEqual(multi_turn["metadata"]["category"], "multi_turn")
        self.assertEqual(multi_turn["max_turns"], 5)

        deferred = manifest["deferred_predefined_release_gate_records"]
        self.assertEqual(deferred[0]["source_test_case_id"], "TC-MULTI-001")
        self.assertIn("multi-turn runtime memory", deferred[0]["deferred_reason"])

    def test_reference_inputs_kwargs_are_ground_truth_only(self):
        scenario = self.artifacts["postdeploy_ground_truth"]["scenarios"][0]
        kwargs = reference_inputs_kwargs(scenario)

        self.assertIn("assertions", kwargs)
        self.assertNotIn("prompt", kwargs)
        self.assertNotIn("setup_turns", kwargs)
        validate_dataset_safety(kwargs)

    def test_managed_dataset_source_matches_dataset_client_shape(self):
        source = managed_dataset_source(self.artifacts["predefined_examples"])

        examples = source["inlineExamples"]["examples"]
        self.assertEqual(len(examples), 4)
        self.assertIn("scenario_id", examples[0])
        self.assertIn("turns", examples[0])
        self.assertIn("assertions", examples[0])

    def test_local_dataset_artifacts_write_and_validate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = write_local_dataset_artifacts(
                manifest=self.artifacts["dataset_manifest"],
                ground_truth=self.artifacts["postdeploy_ground_truth"],
                simulation_scenarios=self.artifacts["postdeploy_simulation_scenarios"],
                manifest_path=tmp / "dataset_manifest.json",
                ground_truth_path=tmp / "postdeploy_ground_truth.json",
                simulation_path=tmp / "postdeploy_simulation_scenarios.json",
            )

            for path in paths.values():
                self.assertTrue(path.is_file())
                json.loads(path.read_text(encoding="utf-8"))

    def test_dataset_safety_rejects_secrets_and_email(self):
        with self.assertRaises(DatasetContractError):
            validate_dataset_safety({"metadata": {"user_email": "alice@example.com"}})
        with self.assertRaises(DatasetContractError):
            validate_dataset_safety({"metadata": {"access_token": "abc"}})

    def test_dataset_client_preflight_is_explicit(self):
        ok, client_class, error = dataset_client_preflight()
        if ok:
            self.assertIsNotNone(client_class)
        else:
            self.assertIn("DatasetClient", error)

    def test_managed_dataset_readiness_blocks_local_only_manifest(self):
        with self.assertRaises(DatasetContractError):
            assert_managed_dataset_ready(self.artifacts["dataset_manifest"])

    def test_managed_dataset_readiness_accepts_published_manifest(self):
        manifest = json.loads(json.dumps(self.artifacts["dataset_manifest"]))
        manifest["dataset_client_status"] = {"status": "CREATED_AND_PUBLISHED"}
        for name in ["predefined", "simulated"]:
            manifest["managed_datasets"][name]["dataset_id"] = f"{name}-dataset"
            manifest["managed_datasets"][name]["baseline_dataset_version"] = "1"

        assert_managed_dataset_ready(manifest)


class Section03DeploymentContractTests(unittest.TestCase):
    def test_deployment_manifest_shape_and_safety(self):
        dataset_manifest = build_local_dataset_artifacts(
            region="us-east-1",
            account_id="123456789012",
        )["dataset_manifest"]
        deployment_id = make_deployment_id()
        manifest = build_deployment_manifest(
            deployment_id=deployment_id,
            region="us-east-1",
            account_id="123456789012",
            runtime={
                "runtime_id": "rt-123",
                "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/rt-123",
                "runtime_name": "ecommerce_workshop_product_catalog_agent",
            },
            gateway={
                "gateway_id": "gw-123",
                "gateway_url": "https://gateway.example.invalid",
            },
            cognito={
                "user_pool_id": "pool-123",
                "user_client_id": "client-123",
            },
            image={
                "repository": "ecommerce-workshop-product-catalog-agent",
                "tag": "rc-123",
                "digest": "sha256:abc",
            },
            model_id="global.anthropic.claude-sonnet-4-6",
            otel_service_name="ecommerce_workshop_product_catalog_agent.DEFAULT",
            dataset_manifest=dataset_manifest,
            section02=dataset_manifest["source_section02"],
            prompt_version="product-catalog-prompts-v1",
            tool_policy_version="product-catalog-tool-policy-v1",
            observability={"custom_spans": True},
            quality_gate={"status": "PASSED"},
        )

        self.assertEqual(manifest["deployment_id"], deployment_id)
        self.assertEqual(manifest["dataset_lineage"]["dataset_lineage_id"], dataset_manifest["dataset_lineage_id"])
        json.dumps(manifest)

    def test_deployment_blocks_without_managed_dataset_readiness(self):
        dataset_manifest = build_local_dataset_artifacts(
            region="us-east-1",
            account_id="123456789012",
        )["dataset_manifest"]

        with self.assertRaises(DeploymentContractError):
            assert_dataset_manifest_ready(None)
        with self.assertRaises(DeploymentContractError):
            assert_dataset_manifest_ready(dataset_manifest)

    def test_deployment_manifest_rejects_sensitive_values(self):
        with self.assertRaises(DeploymentContractError):
            build_deployment_manifest(
                deployment_id="section03-test",
                region="us-east-1",
                account_id="123456789012",
                runtime={
                    "runtime_id": "rt-123",
                    "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/rt-123",
                    "runtime_name": "runtime",
                },
                gateway={"gateway_id": "gw-123", "gateway_url": "https://gateway.example.invalid"},
                cognito={"user_pool_id": "pool-123", "user_client_id": "client-123"},
                image={"repository": "repo", "tag": "rc-123"},
                model_id="global.anthropic.claude-sonnet-4-6",
                otel_service_name="service",
                quality_gate={"status": "PASSED", "user_email": "alice@example.com"},
            )

    def test_postdeploy_gate_summary_distinguishes_failed_pending_and_passed(self):
        summary = summarize_postdeploy_scores(
            [
                {
                    "scenario_id": "s1",
                    "results": [
                        {
                            "evaluator_id": "Builtin.Correctness",
                            "score": 0.9,
                            "threshold": 0.7,
                            "status": "PASS",
                        }
                    ],
                }
            ],
            total_observability_events=3,
        )
        self.assertEqual(summary["status"], "PASSED")

        failed = summarize_postdeploy_scores([], total_observability_events=0)
        self.assertEqual(failed["status"], "FAILED")

        pending = summarize_postdeploy_scores(
            [
                {
                    "scenario_id": "s1",
                    "results": [
                        {
                            "evaluator_id": "Builtin.Correctness",
                            "score": None,
                            "threshold": 0.7,
                            "status": "PENDING",
                        }
                    ],
                }
            ],
            total_observability_events=3,
        )
        self.assertEqual(pending["status"], "PENDING")

    def test_postdeploy_gate_config_controls_threshold_and_review_mode(self):
        self.assertTrue(POSTDEPLOY_GATE_CONFIG_PATH.is_file())
        config = load_postdeploy_gate_config()
        scenario = {
            "scenario_id": "release-gate-TC-REC-001",
            "source_test_case_id": "TC-REC-001",
            "threshold_policy": {"Builtin.Correctness": 0.7},
        }

        default_policy = gate_policy_for_evaluator(
            "Builtin.Correctness",
            scenario,
            config,
        )
        self.assertEqual(default_policy["gate_mode"], "blocking")
        self.assertEqual(default_policy["threshold"], 0.7)

        relaxed_config = json.loads(json.dumps(config))
        relaxed_config["source_case_overrides"]["TC-REC-001"]["evaluator_overrides"][
            "Builtin.Correctness"
        ]["gate_mode"] = "review_only"
        review_policy = gate_policy_for_evaluator(
            "Builtin.Correctness",
            scenario,
            relaxed_config,
        )
        self.assertEqual(review_policy["gate_mode"], "review_only")

        threshold_config = json.loads(json.dumps(config))
        threshold_config["source_case_overrides"]["TC-REC-001"]["evaluator_overrides"][
            "Builtin.Correctness"
        ]["threshold"] = 0.5
        threshold_policy = gate_policy_for_evaluator(
            "Builtin.Correctness",
            scenario,
            threshold_config,
        )
        self.assertEqual(threshold_policy["threshold"], 0.5)

    def test_review_only_evaluator_does_not_block_postdeploy_gate(self):
        summary = summarize_postdeploy_scores(
            [
                {
                    "scenario_id": "release-gate-TC-REC-001",
                    "results": [
                        {
                            "evaluator_id": "Builtin.Correctness",
                            "score": 0.5,
                            "threshold": 0.7,
                            "gate_mode": "review_only",
                            "status": "REVIEW",
                        }
                    ],
                }
            ],
            total_observability_events=3,
        )
        self.assertEqual(summary["status"], "PASSED")
        self.assertEqual(
            summary["review_reasons"],
            ["release-gate-TC-REC-001:Builtin.Correctness:review_only"],
        )
        self.assertFalse(summary["failure_reasons"])

    def test_evaluator_ids_fallback_and_data_protection_policy(self):
        scenario = {
            "expected_response": "Expected answer",
            "expected_trajectory": ["search_products"],
            "assertions": ["Agent searched products"],
        }
        ids = evaluator_ids_for_scenario(scenario)
        self.assertIn("Builtin.Correctness", ids)
        self.assertIn("Builtin.TrajectoryAnyOrderMatch", ids)

        policy = build_data_protection_policy(
            ["arn:aws:logs:us-east-1:123456789012:log-group:/aws/example:*"]
        )
        self.assertEqual(policy["Name"], "Section03RuntimeDataProtection")
        self.assertEqual(len(policy["Statement"]), 2)

    def test_release_metadata_env_and_trace_allowlist(self):
        otel_service_name = endpoint_otel_service_name(
            "ecommerce_workshop_product_catalog_agent"
        )
        self.assertEqual(
            otel_service_name,
            "ecommerce_workshop_product_catalog_agent.DEFAULT",
        )
        env = build_release_metadata_env(
            deployment_id="section03-20260808T000000Z-abc12345",
            agent_version="section03-rc-abc12345",
            model_id="global.anthropic.claude-sonnet-4-6",
            otel_service_name=otel_service_name,
            prompt_version="product-catalog-prompts-v1",
            tool_policy_version="product-catalog-tool-policy-v1",
        )
        self.assertEqual(env["DEPLOYMENT_ID"], "section03-20260808T000000Z-abc12345")

        validate_safe_trace_attributes(
            {
                "deployment.id": env["DEPLOYMENT_ID"],
                "agent.version": env["AGENT_VERSION"],
                "agent.model_id": env["MODEL_ID"],
                "runtime.role": "customer",
                "runtime.session_id": "session-1",
                "tools.allowed_count": 6,
            }
        )

        with self.assertRaises(DeploymentContractError):
            validate_safe_trace_attributes({"prompt": "answer this"})

    def test_scenario_runtime_payload_keeps_tokens_ephemeral(self):
        scenario = {
            "role": "customer",
            "prompt": "Tell me about PROD-001",
        }
        payload = scenario_runtime_payload(
            scenario,
            session_id="session-1",
            role_tokens={
                "customer": {
                    "id_token": "header.payload.signature",
                    "access_token": "access.header.payload",
                }
            },
        )

        self.assertEqual(payload["prompt"], scenario["prompt"])
        self.assertEqual(payload["session_id"], "session-1")
        self.assertIn("bearer_token", payload)

    def test_ecr_image_evidence_records_digest_when_available(self):
        class FakeEcr:
            def describe_images(self, **kwargs):
                return {"imageDetails": [{"imageDigest": "sha256:abc"}]}

        evidence = ecr_image_evidence(
            FakeEcr(),
            repository="repo",
            tag="rc-abc",
            image_uri="123.dkr.ecr.us-east-1.amazonaws.com/repo:rc-abc",
            latest_uri="123.dkr.ecr.us-east-1.amazonaws.com/repo:latest",
        )

        self.assertEqual(evidence["digest"], "sha256:abc")
        self.assertEqual(evidence["tag"], "rc-abc")

    def test_batch_dataset_uses_gateway_qualified_tool_names(self):
        ground_truth = build_local_dataset_artifacts(
            region="us-east-1",
            account_id="123456789012",
        )["postdeploy_ground_truth"]

        dataset = batch_dataset_from_ground_truth(ground_truth)

        self.assertEqual(len(dataset.scenarios), 4)
        details = next(
            scenario
            for scenario in dataset.scenarios
            if scenario.scenario_id == "release-gate-TC-DETAILS-001"
        )
        self.assertEqual(
            details.expected_trajectory,
            ["ProductTools___get_product_details"],
        )
        self.assertEqual(details.turns[0].input["role"], "customer")
        self.assertIn("prompt", details.turns[0].input)
        self.assertEqual(gateway_qualified_tool_names(["search_products"]), ["ProductTools___search_products"])

    def test_batch_evaluation_manifest_shape_and_blocking(self):
        dataset_manifest = build_local_dataset_artifacts(
            region="us-east-1",
            account_id="123456789012",
        )["dataset_manifest"]
        dataset_manifest["dataset_client_status"] = {"status": "CREATED_AND_PUBLISHED"}
        for name in ["predefined", "simulated"]:
            dataset_manifest["managed_datasets"][name]["dataset_id"] = f"{name}-dataset"
            dataset_manifest["managed_datasets"][name]["baseline_dataset_version"] = "1"

        batch_result = SimpleNamespace(
            batch_evaluation_id="batch-123",
            batch_evaluation_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:batch-evaluation/batch-123",
            batch_evaluation_name="section03-batch",
            status="COMPLETED",
            created_at="2026-08-08T00:00:00Z",
            updated_at=None,
            error_details=[],
            agent_invocation_failures=[],
            output_data_config=SimpleNamespace(
                log_group_name="/aws/bedrock-agentcore/evaluations/batch-evaluations/results/default",
                log_stream_name="run-batch-123",
            ),
            evaluation_results=SimpleNamespace(
                number_of_sessions_completed=4,
                number_of_sessions_failed=0,
                number_of_sessions_ignored=0,
                number_of_sessions_in_progress=0,
                total_number_of_sessions=4,
                evaluator_summaries=[
                    SimpleNamespace(
                        evaluator_id="Builtin.Correctness",
                        statistics=SimpleNamespace(average_score=1.0),
                        total_evaluated=4,
                    )
                ],
            ),
        )

        manifest = build_batch_evaluation_manifest(
            deployment_id="section03-test",
            dataset_manifest=dataset_manifest,
            batch_result=batch_result,
            evaluator_ids=["Builtin.Correctness"],
            scenario_count=4,
            batch_events_count=4,
        )

        self.assertEqual(manifest["artifact_type"], "section_03_batch_evaluation_manifest")
        self.assertEqual(manifest["batch_evaluation"]["status"], "COMPLETED")
        self.assertEqual(manifest["batch_evaluation"]["sessions"]["completed"], 4)
        validate_batch_evaluation_manifest(manifest)

        batch_result.status = "FAILED"
        with self.assertRaises(DeploymentContractError):
            build_batch_evaluation_manifest(
                deployment_id="section03-test",
                dataset_manifest=dataset_manifest,
                batch_result=batch_result,
                evaluator_ids=["Builtin.Correctness"],
                scenario_count=4,
            )


class Section03NotebookContractTests(unittest.TestCase):
    def test_notebooks_are_json_valid_and_code_cells_parse(self):
        for notebook_name in [
            "03a-ground-truth-dataset.ipynb",
            "03-production-deployment.ipynb",
        ]:
            notebook = json.loads((SECTION_DIR / notebook_name).read_text(encoding="utf-8"))
            errors = []
            for index, cell in enumerate(notebook["cells"]):
                if cell.get("cell_type") != "code":
                    continue
                cleaned_source = []
                for line in cell.get("source", []):
                    stripped = line.lstrip()
                    if stripped.startswith("%") or stripped.startswith("!"):
                        cleaned_source.append("\n")
                    else:
                        cleaned_source.append(line)
                try:
                    ast.parse("".join(cleaned_source), filename=f"{notebook_name} cell {index}")
                except SyntaxError as exc:
                    errors.append(f"{notebook_name} cell {index}: {exc.msg} at line {exc.lineno}")
            self.assertEqual(errors, [])

    def test_03a_notebook_teaches_datasetclient_and_reference_inputs(self):
        text = (SECTION_DIR / "03a-ground-truth-dataset.ipynb").read_text(encoding="utf-8")

        for expected_text in [
            "DatasetClient",
            "assert_managed_dataset_ready",
            "Section 03a blocked before deployment handoff",
            "AGENTCORE_EVALUATION_PREDEFINED_V1",
            "AGENTCORE_EVALUATION_SIMULATED_V1",
            "ReferenceInputs",
            "postdeploy_ground_truth.json",
            "postdeploy_simulation_scenarios.json",
            "dataset_manifest.json",
        ]:
            self.assertIn(expected_text, text)

    def test_deployment_notebook_uses_release_manifest_and_grounded_gate(self):
        text = (SECTION_DIR / "03-production-deployment.ipynb").read_text(encoding="utf-8")

        for expected_text in [
            "DEPLOYMENT_ID",
            "AGENT_VERSION",
            "deployment_manifest.json",
            "assert_dataset_manifest_ready",
            "IMAGE_EVIDENCE",
            "imageDigest",
            "run_shell",
            "docker_image_exists",
            "DOCKER_BUILD_SUCCEEDED",
            "DOCKER_BUILDKIT=1 docker build",
            "build_release_metadata_env",
            "CONFIG_BUNDLE_HOOK_VERSION",
            "config_bundle_source_sha256",
            "update_agent_runtime",
            "postdeploy_ground_truth.json",
            "EvaluationClient",
            "ReferenceInputs",
            "reference_inputs_kwargs",
            "GATEWAY_TOOL_PREFIX",
            "ProductTools___",
            "raw_results_meet_threshold",
            "run_evaluation_with_trace_retries",
            "summarize_postdeploy_scores",
            "Post-deployment quality gate did not pass",
            "BatchEvaluationRunner",
            "BatchEvaluationRunConfig",
            "CloudWatchDataSourceConfig",
            "batch_evaluation_manifest.json",
            "build_batch_evaluation_manifest",
            "APPLY_CLOUDWATCH_DATA_PROTECTION",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS",
            "httpx",
            "OTEL_PYTHON_HTTPX_EXCLUDED_URLS",
            "ecommerce-workshop-product-gateway",
        ]:
            self.assertIn(expected_text, text)

        self.assertNotIn("bedrock_agentcore_starter_toolkit import Evaluation", text)

    def test_runtime_agent_has_custom_spans_and_sanitized_errors(self):
        text = (SECTION_DIR / "agents" / "product_catalog_agent.py").read_text(
            encoding="utf-8"
        )

        for span_name in [
            "product_catalog.runtime_invocation",
            "product_catalog.jwt_role_extraction",
            "product_catalog.gateway_mcp_connection",
            "product_catalog.tool_discovery",
            "product_catalog.rbac_tool_filtering",
            "product_catalog.agent_invocation",
        ]:
            self.assertIn(span_name, text)

        self.assertIn("set_safe_span_attributes", text)
        self.assertIn("safe_error", text)
        self.assertIn("BedrockAgentCoreContext", text)
        self.assertIn("get_config_bundle", text)
        self.assertIn("resolve_system_prompt", text)
        self.assertIn("apply_tool_description_overrides", text)
        self.assertLess(text.index("config_bundle = get_config_bundle()"), text.index("agent = Agent("))
        self.assertNotIn("logger.error(f\"Agent error: {e}\")", text)

    def test_runtime_role_allows_configuration_bundle_reads(self):
        text = (SECTION_DIR / "utils.py").read_text(encoding="utf-8")
        self.assertIn("configuration-bundle-policy", text)
        self.assertIn("bedrock-agentcore:GetConfigurationBundleVersion", text)
        self.assertIn("bedrock-agentcore:ListConfigurationBundleVersions", text)

    def test_generated_streamlit_example_has_no_password_or_demo_emails(self):
        text = (SECTION_DIR / "streamlit_app" / "agent_config.json.example").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("test_password", text)
        self.assertNotIn("john.customer@example.com", text)
        self.assertNotIn("alice.admin@example.com", text)

    def test_notebook_and_streamlit_avoid_fixed_demo_credentials(self):
        notebook_text = (SECTION_DIR / "03-production-deployment.ipynb").read_text(
            encoding="utf-8"
        )
        app_text = (SECTION_DIR / "streamlit_app" / "app.py").read_text(
            encoding="utf-8"
        )

        for text in [notebook_text, app_text]:
            self.assertNotIn("john.customer@example.com", text)
            self.assertNotIn("alice.admin@example.com", text)
            self.assertNotIn("Workshop1234", text)

        self.assertIn("DEMO_USER_SUFFIX", notebook_text)
        self.assertIn("redact_email", notebook_text)
        self.assertIn("demo_credentials", app_text)
        self.assertIn("SECTION03_TEST_PASSWORD", app_text)

    def test_notebook_and_utils_sanitize_exception_output(self):
        notebook_text = (SECTION_DIR / "03-production-deployment.ipynb").read_text(
            encoding="utf-8"
        )
        utils_text = (SECTION_DIR / "utils.py").read_text(encoding="utf-8")
        product_tools_text = (
            SECTION_DIR / "lambda_tools" / "product_tools_lambda.py"
        ).read_text(encoding="utf-8")

        self.assertIn("sanitize_error", notebook_text)
        self.assertIn("sanitize_error", utils_text)
        self.assertIn("sanitize_error", product_tools_text)
        self.assertNotIn("print(f\\\"Error checking status: {e}", notebook_text)
        self.assertNotIn("print(f\"Error creating role: {e}", utils_text)
        self.assertNotIn("return {'Role': None, 'exit_code': 1, 'error': str(e)}", utils_text)
        self.assertNotIn('"error": str(e)', product_tools_text)


if __name__ == "__main__":
    unittest.main()
