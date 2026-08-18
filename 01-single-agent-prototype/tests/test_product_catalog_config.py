import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SECTION_DIR.parent
AGENTS_DIR = SECTION_DIR / "agents"
sys.path.insert(0, str(AGENTS_DIR))

from config_loader import AgentConfigError, load_agent_behavior_config
from product_catalog_agent import (
    ADMIN_ONLY_TOOLS,
    ADMIN_TOOLS,
    CUSTOMER_TOOLS,
    ProductCatalogAgent,
    UserSession,
    build_system_prompt,
    get_tools_for_role,
)


class FakeTool:
    def __init__(self, tool_name):
        self.tool_name = tool_name


class ProductCatalogConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = load_agent_behavior_config()

    def test_config_loads_expected_versions_and_defaults(self):
        self.assertEqual(self.config.agent_name, "ProductCatalogAgent")
        self.assertEqual(self.config.default_role, "customer")
        self.assertEqual(
            self.config.model_config["model_id"],
            "global.anthropic.claude-sonnet-5",
        )
        self.assertEqual(
            self.config.prompt_version,
            "product-catalog-prompts-v1",
        )
        self.assertEqual(
            self.config.tool_policy_version,
            "product-catalog-tool-policy-v1",
        )
        self.assertEqual(
            self.config.tool_catalog_version,
            "product-catalog-tool-catalog-v1",
        )

    def test_policy_catalog_consistency(self):
        catalog_names = set(self.config.tool_catalog_by_name())
        policy_names = set()
        for role in self.config.tool_policy["roles"]:
            policy_names.update(self.config.tools_for_role(role))

        self.assertEqual(catalog_names, policy_names)
        self.assertEqual(len(catalog_names), 11)

    def test_prompt_rendering_includes_user_context_and_contract(self):
        prompt = build_system_prompt(
            UserSession(
                user_id="CUST-1001",
                role="customer",
                email="john.smith@email.com",
                name="John Smith",
            )
        )

        self.assertIn("John Smith", prompt)
        self.assertIn("john.smith@email.com", prompt)
        self.assertIn("product-catalog-prompts-v1", prompt)
        self.assertIn("search_products", prompt)
        self.assertNotIn("{user_name}", prompt)

    def test_role_based_tool_filtering_uses_policy_not_prompt_text(self):
        all_tools = [FakeTool(name) for name in ADMIN_TOOLS]

        customer_tool_names = [t.tool_name for t in get_tools_for_role(all_tools, "customer")]
        admin_tool_names = [t.tool_name for t in get_tools_for_role(all_tools, "admin")]

        self.assertEqual(customer_tool_names, CUSTOMER_TOOLS)
        self.assertEqual(admin_tool_names, ADMIN_TOOLS)
        self.assertTrue(set(ADMIN_ONLY_TOOLS).isdisjoint(customer_tool_names))

    def test_unknown_role_uses_least_privilege_customer_policy(self):
        all_tools = [FakeTool(name) for name in ADMIN_TOOLS]
        unknown_role_tools = get_tools_for_role(all_tools, "superadmin")
        unknown_role_names = [t.tool_name for t in unknown_role_tools]

        self.assertEqual(unknown_role_names, CUSTOMER_TOOLS)
        self.assertTrue(set(ADMIN_ONLY_TOOLS).isdisjoint(unknown_role_names))

    def test_gateway_prefixed_tool_names_still_filter_by_base_name(self):
        prefixed_tools = [FakeTool(f"ProductCatalog___{name}") for name in ADMIN_TOOLS]
        filtered_tools = get_tools_for_role(prefixed_tools, "customer")
        filtered_names = [tool.tool_name for tool in filtered_tools]

        self.assertEqual(
            filtered_names,
            [f"ProductCatalog___{name}" for name in CUSTOMER_TOOLS],
        )

    def test_missing_config_file_has_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_section = Path(tmpdir) / "section"
            shutil.copytree(SECTION_DIR, temp_section)
            (temp_section / "config" / "tool_policy.json").unlink()

            with self.assertRaisesRegex(AgentConfigError, "Missing configuration file"):
                load_agent_behavior_config(temp_section)

    def test_agent_manifest_is_json_serializable_and_local_only(self):
        agent = ProductCatalogAgent.__new__(ProductCatalogAgent)
        agent.region = "us-west-2"
        agent.behavior_config = self.config
        agent.user_session = UserSession(
            user_id="ADMIN-001",
            role="admin",
            email="alice.admin@company.com",
            name="Alice Admin",
        )

        manifest = ProductCatalogAgent.get_agent_manifest(agent)

        self.assertEqual(manifest["module"], "01-single-agent-prototype")
        self.assertEqual(manifest["execution_mode"], "local")
        self.assertTrue(manifest["local_only"])
        self.assertEqual(manifest["agent"]["name"], "ProductCatalogAgent")
        self.assertEqual(manifest["model"]["model_id"], self.config.model_config["model_id"])
        self.assertEqual(manifest["model"]["region"], "us-west-2")
        self.assertEqual(manifest["role"]["resolved"], "admin")
        self.assertEqual(manifest["available_tools"], ADMIN_TOOLS)
        self.assertEqual(len(manifest["tool_metadata"]), len(ADMIN_TOOLS))
        self.assertNotIn("gateway", json.dumps(manifest).lower())
        self.assertNotIn("deployment", json.dumps(manifest).lower())
        json.dumps(manifest)

    def test_notebook_uses_config_manifest_and_stays_local_only(self):
        notebook_path = SECTION_DIR / "01-single-agent-prototype.ipynb"
        with notebook_path.open("r", encoding="utf-8") as f:
            notebook = json.load(f)

        notebook_source = "\n".join(
            "".join(cell.get("source", ""))
            if isinstance(cell.get("source", ""), list)
            else cell.get("source", "")
            for cell in notebook["cells"]
        )

        self.assertIn("SECTION_DIR = _find_section_dir()", notebook_source)
        self.assertIn("BEHAVIOR_CONFIG = load_agent_behavior_config(SECTION_DIR)", notebook_source)
        self.assertIn("get_agent_manifest()", notebook_source)
        self.assertIn('print(f"\\nDiscovered {len(all_tools)} tools from MCP server:")', notebook_source)
        self.assertNotIn('print(f"\nDiscovered {len(all_tools)} tools from MCP server:")', notebook_source)
        self.assertIn("config/tool_policy.json", notebook_source)
        self.assertIn("Local Behavior Contract", notebook_source)
        self.assertNotIn("AgentCore Identity", notebook_source)
        self.assertNotIn("Gateway", notebook_source)
        self.assertNotIn("Harness", notebook_source)
        self.assertNotIn("A/B", notebook_source)
        self.assertNotIn("JWT claims", notebook_source)
        self.assertNotIn("No RBAC", notebook_source)
        self.assertNotIn("basic_agent", notebook_source)
        self.assertNotIn("Before deploying to production", notebook_source)
        self.assertNotIn("all 11 tools (no role filtering)", notebook_source)
        self.assertNotIn("Optimization", notebook_source)
        self.assertNotIn("evaluate or deploy", notebook_source)
        self.assertNotIn("does not deploy", notebook_source)


if __name__ == "__main__":
    unittest.main()
