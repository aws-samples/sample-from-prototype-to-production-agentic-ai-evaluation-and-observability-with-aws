import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SECTION_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SECTION_DIR.parent
sys.path.insert(0, str(SECTION_DIR))

from workshop_paths import (
    find_section_dir,
    read_sample_json,
    sample_data_path,
    section_file_path,
)


class WorkshopPathsTests(unittest.TestCase):
    def test_finds_section_dir_from_repo_root_and_section_dir(self):
        self.assertEqual(find_section_dir(REPO_ROOT), SECTION_DIR)
        self.assertEqual(find_section_dir(SECTION_DIR), SECTION_DIR)

    def test_finds_section_dir_from_nested_path(self):
        nested_path = SECTION_DIR / "sample_data"
        self.assertEqual(find_section_dir(nested_path), SECTION_DIR)

    def test_uses_environment_override_for_external_working_directory(self):
        original = os.environ.get("WORKSHOP_SECTION_DIR")
        os.environ["WORKSHOP_SECTION_DIR"] = str(SECTION_DIR)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                self.assertEqual(find_section_dir(tmpdir), SECTION_DIR)
        finally:
            if original is None:
                os.environ.pop("WORKSHOP_SECTION_DIR", None)
            else:
                os.environ["WORKSHOP_SECTION_DIR"] = original

    def test_resolves_sample_data_and_scripts(self):
        self.assertEqual(
            sample_data_path("orders.json", section_dir=REPO_ROOT),
            SECTION_DIR / "sample_data" / "orders.json",
        )
        self.assertEqual(
            section_file_path("setup_infrastructure.py", section_dir=REPO_ROOT),
            SECTION_DIR / "setup_infrastructure.py",
        )

    def test_loads_all_sample_json_files_from_repo_root_and_section_dir(self):
        original_cwd = Path.cwd()
        try:
            for cwd, filename, expected_key in [
                (REPO_ROOT, "orders.json", "orders"),
                (REPO_ROOT, "accounts.json", "accounts"),
                (REPO_ROOT, "products.json", "products"),
                (SECTION_DIR, "orders.json", "orders"),
                (SECTION_DIR, "accounts.json", "accounts"),
                (SECTION_DIR, "products.json", "products"),
            ]:
                with self.subTest(cwd=str(cwd), filename=filename):
                    os.chdir(cwd)
                    sample_data = read_sample_json(filename)
                    self.assertIn(expected_key, sample_data)
        finally:
            os.chdir(original_cwd)

    def test_notebook_uses_resolved_paths_instead_of_brittle_relative_paths(self):
        notebook_path = SECTION_DIR / "0-environment-setup.ipynb"
        with notebook_path.open("r", encoding="utf-8") as f:
            notebook = json.load(f)

        notebook_source = "\n".join(
            "".join(cell.get("source", ""))
            if isinstance(cell.get("source", ""), list)
            else cell.get("source", "")
            for cell in notebook["cells"]
        )

        self.assertIn("SECTION_DIR = _find_section_dir()", notebook_source)
        self.assertIn("read_sample_json(\"orders.json\"", notebook_source)
        self.assertIn("section_file_path(\"setup_infrastructure.py\"", notebook_source)
        self.assertIn("section_file_path(\"verify_infrastructure.py\"", notebook_source)
        self.assertNotIn("open(\"sample_data/orders.json\")", notebook_source)
        self.assertNotIn("!{sys.executable} setup_infrastructure.py", notebook_source)
        self.assertNotIn("!{sys.executable} verify_infrastructure.py", notebook_source)


if __name__ == "__main__":
    unittest.main()
