import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SECTION_DIR))

from evaluation_contract import (
    EvaluationContractError,
    attach_safe_span_attributes,
    build_release_gate_evidence,
    build_run_manifest,
    duplicate_test_case_ids,
    get_cases_for_slice,
    load_dataset,
    load_registry,
    load_slices,
    safe_span_attributes,
    validate_contract_artifacts,
    validate_safe_span_attributes,
)


class FakeCase:
    def __init__(self, name, input_text, expected_output, metadata):
        self.name = name
        self.input = input_text
        self.expected_output = expected_output
        self.metadata = metadata


class EvaluationContractTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_dataset()
        self.registry = load_registry()
        self.slices = load_slices()

    def test_registry_covers_required_evaluators_and_builtins(self):
        evaluator_ids = {entry["id"] for entry in self.registry["evaluators"]}
        for evaluator_id in [
            "goal_success",
            "helpfulness",
            "rbac_compliance",
            "tool_parameter_accuracy",
            "policy_compliance",
            "response_quality",
            "customer_satisfaction",
            "agentcore_goal_success_rate",
            "agentcore_correctness",
            "agentcore_helpfulness",
        ]:
            self.assertIn(evaluator_id, evaluator_ids)

        hard_gates = [
            entry
            for entry in self.registry["evaluators"]
            if entry["gate_role"] == "hard_gate"
        ]
        self.assertTrue(any(entry["type"] == "deterministic_assertion" for entry in hard_gates))

    def test_slices_resolve_and_preserve_smoke_path(self):
        smoke_cases = get_cases_for_slice(self.dataset, self.slices, "smoke")
        smoke_ids = [case["id"] for case in smoke_cases]

        self.assertEqual(
            smoke_ids,
            [
                "TC-SEARCH-001",
                "TC-DETAILS-001",
                "TC-INV-001",
                "TC-REC-001",
                "TC-COMP-001",
                "TC-ADMIN-001",
                "TC-RBAC-001",
                "TC-ADV-001",
                "TC-OOS-001",
                "TC-POLICY-001",
                "TC-MULTI-001",
            ],
        )

        ondemand_ids = [
            case["id"]
            for case in get_cases_for_slice(self.dataset, self.slices, "agentcore_ondemand")
        ]
        self.assertEqual(ondemand_ids, ["TC-SEARCH-001", "TC-INV-001", "TC-REC-001"])

    def test_duplicate_dataset_ids_are_reported_but_unreferenced_duplicates_do_not_fail(self):
        duplicates = duplicate_test_case_ids(self.dataset)
        self.assertIn("TC-PROD-001", duplicates)

        summary = validate_contract_artifacts()
        self.assertIn("production_feedback", summary["resolved_slice_counts"])

    def test_explicit_duplicate_slice_reference_fails(self):
        bad_slices = json.loads(json.dumps(self.slices))
        bad_slices["slices"]["bad_duplicate"] = {
            "description": "bad",
            "test_case_ids": ["TC-PROD-001"],
        }

        with self.assertRaisesRegex(EvaluationContractError, "duplicate case ID"):
            get_cases_for_slice(self.dataset, bad_slices, "bad_duplicate")

    def test_missing_slice_reference_fails(self):
        bad_slices = json.loads(json.dumps(self.slices))
        bad_slices["slices"]["bad_missing"] = {
            "description": "bad",
            "test_case_ids": ["TC-NOT-REAL"],
        }

        with self.assertRaisesRegex(EvaluationContractError, "missing case ID"):
            get_cases_for_slice(self.dataset, bad_slices, "bad_missing")

    def test_run_manifest_is_json_serializable_and_includes_section01_versions(self):
        selected_cases = get_cases_for_slice(self.dataset, self.slices, "smoke")
        manifest = build_run_manifest(
            region="us-west-2",
            selected_slice="smoke",
            selected_test_case_ids=[case["id"] for case in selected_cases],
            dataset=self.dataset,
            registry=self.registry,
            judge_model_id="global.anthropic.claude-sonnet-4-6",
            agent_manifest={
                "agent": {"name": "ProductCatalogAgent", "version": "local-rbac-v1"},
                "model": {"model_id": "global.anthropic.claude-sonnet-4-6"},
                "config": {
                    "prompt_version": "product-catalog-prompts-v1",
                    "tool_policy_version": "product-catalog-tool-policy-v1",
                    "tool_catalog_version": "product-catalog-tool-catalog-v1",
                },
            },
        )

        self.assertEqual(manifest["dataset_version"], "2.1")
        self.assertEqual(manifest["selected_slice"], "smoke")
        self.assertEqual(manifest["agent"]["prompt_version"], "product-catalog-prompts-v1")
        json.dumps(manifest)

    def test_safe_span_attributes_allowlist_and_denylist(self):
        selected_case = get_cases_for_slice(self.dataset, self.slices, "agentcore_ondemand")[0]
        manifest = build_run_manifest(
            region="us-west-2",
            selected_slice="agentcore_ondemand",
            selected_test_case_ids=[selected_case["id"]],
            dataset=self.dataset,
            registry=self.registry,
            judge_model_id="global.anthropic.claude-sonnet-4-6",
        )
        attrs = safe_span_attributes(case=selected_case, run_manifest=manifest)
        validate_safe_span_attributes(attrs)

        with self.assertRaisesRegex(EvaluationContractError, "Unsafe span attribute key"):
            validate_safe_span_attributes({"ground_truth": "answer key"})

        bad_attrs = dict(attrs)
        bad_attrs["agent.name"] = "alice@example.com"
        with self.assertRaisesRegex(EvaluationContractError, "Unsafe span attribute value"):
            validate_safe_span_attributes(bad_attrs)

    def test_attach_safe_span_attributes_updates_adot_attribute_maps(self):
        span = {"traceId": "abc", "attributes": {"existing": "value"}}
        attrs = {
            "eval.run_id": "run-1",
            "eval.dataset_version": "2.1",
            "eval.slice_name": "agentcore_ondemand",
            "eval.test_case_id": "TC-SEARCH-001",
            "eval.case_category": "product_search",
            "eval.case_subcategory": "basic_keyword",
            "eval.case_difficulty": "easy",
            "eval.registry_version": "1.0",
            "eval.thresholds_version": "release-gate-thresholds-v1",
            "eval.synthetic": True,
            "agent.name": "ProductCatalogAgent",
            "agent.role": "customer",
            "agent.model_id": "global.anthropic.claude-sonnet-4-6",
        }

        enriched = attach_safe_span_attributes([span], attrs)
        self.assertEqual(enriched[0]["attributes"]["existing"], "value")
        self.assertEqual(enriched[0]["attributes"]["eval.test_case_id"], "TC-SEARCH-001")
        self.assertNotIn("eval.test_case_id", span["attributes"])

    def test_release_gate_evidence_shape(self):
        case = FakeCase(
            "TC-RBAC-001",
            "Create a product",
            "The customer should be denied.",
            {
                "role": "customer",
                "category": "rbac_boundary",
                "subcategory": "customer_create",
                "difficulty": "medium",
                "expected_behavior": "deny",
                "expected_tool": None,
                "expected_tool_parameters": None,
                "must_have_facts": ["cannot"],
            },
        )
        manifest = build_run_manifest(
            region="us-west-2",
            selected_slice="release_gate",
            selected_test_case_ids=["TC-RBAC-001"],
            dataset=self.dataset,
            registry=self.registry,
            judge_model_id="global.anthropic.claude-sonnet-4-6",
        )
        results = [
            {
                "test_case": "TC-RBAC-001",
                "goal_success": 1.0,
                "helpfulness": 0.9,
                "rbac_compliance": 1.0,
                "tool_parameter_accuracy": 1.0,
                "policy_compliance": 1.0,
                "response_quality": 0.9,
                "customer_satisfaction": 0.9,
            }
        ]
        deterministic = [
            {
                "test_case": "TC-RBAC-001",
                "overall_pass": True,
                "behavior_pass": True,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = build_release_gate_evidence(
                selected_cases=[case],
                response_cache={"TC-RBAC-001": "Sorry, I cannot create products."},
                trajectory_cache={"TC-RBAC-001": []},
                deterministic_results=deterministic,
                results=results,
                run_manifest=manifest,
                registry=self.registry,
                output_path=Path(tmpdir) / "release_gate_evidence.json",
            )

        record = artifact["records"][0]
        self.assertEqual(record["source_test_case_id"], "TC-RBAC-001")
        self.assertEqual(record["gate_decision"], "pass")
        self.assertTrue(record["eligible_for_section_03a_ground_truth"])
        self.assertIn("expected_tool_trajectory", record)

    def test_helper_does_not_import_or_reference_agentcore_dataset_client(self):
        helper_text = (SECTION_DIR / "evaluation_contract.py").read_text(encoding="utf-8")
        self.assertNotIn("DatasetClient", helper_text)
        self.assertNotIn("create_dataset", helper_text)
        self.assertNotIn("managed dataset", helper_text.lower())

    def test_main_notebook_uses_quality_contract_and_no_dataset_client(self):
        notebook_text = (SECTION_DIR / "02a-strands-evaluation.ipynb").read_text(
            encoding="utf-8"
        )

        for expected_text in [
            "SECTION02_EVALUATION_SLICE",
            "SELECTED_SLICE",
            "get_cases_for_slice",
            "build_run_manifest",
            "safe_span_attributes",
            "attach_safe_span_attributes",
            "build_release_gate_evidence",
            "RUN_MANIFEST_PATH",
            "RELEASE_GATE_EVIDENCE_PATH",
        ]:
            self.assertIn(expected_text, notebook_text)

        self.assertNotIn("DatasetClient", notebook_text)
        self.assertNotIn("create_dataset", notebook_text)
        self.assertNotIn("bedrock_agentcore.datasets", notebook_text)

    def test_main_notebook_code_cells_are_python_parseable(self):
        notebook = json.loads(
            (SECTION_DIR / "02a-strands-evaluation.ipynb").read_text(encoding="utf-8")
        )
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
                ast.parse("".join(cleaned_source), filename=f"02a cell {index}")
            except SyntaxError as exc:
                errors.append(f"cell {index}: {exc.msg} at line {exc.lineno}")

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
