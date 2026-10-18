"""Contract tests for the reviewed TinyHosts release route."""

import hashlib
import re
import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReviewedReleaseContractTests(unittest.TestCase):
    def test_release_manifest_and_tinybus_sdk_are_pinned_together(self):
        manifest = tomllib.loads((ROOT / "Cargo.toml").read_text())
        bus_manifest = tomllib.loads((ROOT / "crates" / "tinyhosts-bus" / "Cargo.toml").read_text())
        self.assertEqual(manifest["package"]["version"], "0.4.2")
        self.assertEqual(bus_manifest["package"]["version"], "0.4.2")
        self.assertEqual(manifest["dependencies"]["tinyhosts-bus"]["version"], "0.4.2")
        self.assertEqual(manifest["dependencies"]["tinybus"]["version"], ">=0.3.2, <0.4")
        self.assertEqual(manifest["dependencies"]["tinybus-module"]["version"], ">=0.3.2, <0.4")
        self.assertEqual(
            subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD:vendor/tinybus"], text=True
            ).strip(),
            "cba2de0e573f99fe4c7e45ba14e2d6b5a2a7757f",
        )

    def test_reviewed_epic_release_delegates_to_the_canonical_preflight(self):
        workflow = (ROOT / ".github" / "workflows" / "release-reviewed-epic.yml").read_text()
        inputs = workflow.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(
            re.findall(r"^      ([a-z-]+):$", inputs, re.MULTILINE),
            ["tag", "version", "reviewed-pr"],
        )
        self.assertIn("      tag:\n        description:", inputs)
        self.assertIn("      version:\n        description:", inputs)
        self.assertIn("      reviewed-pr:\n        description:", inputs)
        self.assertEqual(inputs.count("        type: string"), 2)
        self.assertIn("        type: number", inputs)
        self.assertIn("canonical epic branch", workflow)
        self.assertIn(
            "permissions:\n  contents: write\n  pull-requests: read\n  checks: read\n  actions: read\n",
            workflow,
        )
        self.assertIn(
            "uses: tinyhumansai/.github/.github/workflows/module-reviewed-epic-release.yml"
            "@6ed83b04aab2d8977ec62e966cb914531e534fa4",
            workflow,
        )
        self.assertIn("tag: ${{ inputs.tag }}", workflow)
        self.assertIn("version: ${{ inputs.version }}", workflow)
        self.assertIn("reviewed-pr: ${{ inputs['reviewed-pr'] }}", workflow)
        self.assertNotIn("module-crate:", workflow)
        self.assertNotIn("actions/checkout", workflow)
        self.assertNotIn("validate_reviewed_release.py", workflow)
        self.assertNotIn("  push:", workflow)

    def test_ordinary_release_workflow_is_unchanged(self):
        legacy = (ROOT / ".github" / "workflows" / "release.yml").read_bytes()
        self.assertEqual(
            hashlib.sha256(legacy).hexdigest(),
            "9f50de454c7fa81350a62358fe18a25ef9afe3f34a593dc34ff30dd1c2c5a8b6",
        )


if __name__ == "__main__":
    unittest.main()
