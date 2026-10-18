"""Contract tests for the reviewed TinyHosts release route."""

import importlib.util
import hashlib
import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "validate_reviewed_release.py"
SPEC = importlib.util.spec_from_file_location("validate_reviewed_release", SCRIPT_PATH)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def pull_request(**overrides):
    value = {
        "number": 42,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-10-18T10:00:00Z",
        "user": {"login": "author"},
        "base": {
            "ref": "main",
            "repo": {"full_name": "tinyhumansai/tinyhosts"},
        },
        "head": {"sha": "abc123"},
    }
    value.update(overrides)
    return value


def release_files():
    return [
        {"filename": "Cargo.toml"},
        {"filename": "crates/tinyhosts-bus/Cargo.toml"},
        {"filename": "vendor/tinybus"},
    ]


class ReviewedReleaseContractTests(unittest.TestCase):
    def test_reviewed_epic_release_delegates_to_the_canonical_preflight(self):
        workflow = (ROOT / ".github" / "workflows" / "release-reviewed-epic.yml").read_text()
        inputs = workflow.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(
            __import__("re").findall(r"^      ([a-z-]+):$", inputs, __import__("re").MULTILINE),
            ["tag", "version", "reviewed-pr"],
        )
        self.assertIn("      reviewed-pr:\n        description:", inputs)
        self.assertIn("        type: number", inputs)
        self.assertIn(
            "permissions:\n  contents: write\n  pull-requests: read\n  checks: read\n  actions: read\n",
            workflow,
        )
        self.assertIn(
            "uses: tinyhumansai/.github/.github/workflows/module-reviewed-epic-release.yml"
            "@e045fc567c583a1b83dc9c1edef896179853fa69",
            workflow,
        )
        self.assertIn("reviewed-pr: ${{ inputs['reviewed-pr'] }}", workflow)
        self.assertNotIn("module-crate:", workflow)
        self.assertNotIn("actions/checkout", workflow)
        self.assertNotIn("validate_reviewed_release.py", workflow)
        self.assertNotIn("  push:", workflow)

    def test_release_manifest_and_module_sdk_are_pinned_together(self):
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
        release.validate_release_manifests("0.4.2", ROOT)
        with self.assertRaises(ValueError):
            release.validate_release_manifests("0.4.3", ROOT)

    def test_routes_a_valid_reviewed_release(self):
        route = release.release_route(
            tag="v0.4.2",
            version="0.4.2",
            reviewed_pr="42",
            ref="refs/heads/main",
        )
        self.assertEqual(
            route,
            {
                "tag": "v0.4.2",
                "version": "0.4.2",
                "reviewed-pr": 42,
                "module-crate": "tinyhosts",
            },
        )

    def test_rejects_invalid_release_inputs(self):
        for values in [
            ("v0.4.2", "0.4.1", "42", "refs/heads/main"),
            ("0.4.2", "0.4.2", "42", "refs/heads/main"),
            ("v0.4.2", "0.4.2", "0", "refs/heads/main"),
            ("v0.4.2", "0.4.2", "-42", "refs/heads/main"),
            ("v0.4.2", "0.4.2", "42;echo", "refs/heads/main"),
            ("v0.4.2", "0.4.2", "42", "refs/heads/feature"),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                release.release_route(*values)

    def test_accepts_only_a_merged_main_pr_with_a_current_external_approval(self):
        reviews = [
            {
                "user": {"login": "reviewer"},
                "state": "APPROVED",
                "commit_id": "abc123",
            }
        ]
        release.validate_reviewed_pr(
            pull_request(),
            reviews,
            release_files(),
            repository="tinyhumansai/tinyhosts",
            number=42,
        )

    def test_rejects_unmerged_misdirected_unreviewed_or_stale_prs(self):
        approved = [
            {
                "user": {"login": "reviewer"},
                "state": "APPROVED",
                "commit_id": "abc123",
            }
        ]
        cases = [
            (pull_request(state="open", merged=False, merged_at=None), approved, release_files()),
            (pull_request(merged=False, merged_at=None), approved, release_files()),
            (
                pull_request(base={"ref": "release", "repo": {"full_name": "tinyhumansai/tinyhosts"}}),
                approved,
                release_files(),
            ),
            (
                pull_request(base={"ref": "main", "repo": {"full_name": "attacker/tinyhosts"}}),
                approved,
                release_files(),
            ),
            (pull_request(), [], release_files()),
            (pull_request(), approved, [{"filename": "README.md"}]),
            (
                pull_request(),
                [{"user": {"login": "author"}, "state": "APPROVED", "commit_id": "abc123"}],
                release_files(),
            ),
            (
                pull_request(),
                [{"user": {"login": "reviewer"}, "state": "APPROVED", "commit_id": "old"}],
                release_files(),
            ),
        ]
        for pull, reviews, files in cases:
            with self.subTest(pull=pull, reviews=reviews, files=files), self.assertRaises(ValueError):
                release.validate_reviewed_pr(
                    pull,
                    reviews,
                    files,
                    repository="tinyhumansai/tinyhosts",
                    number=42,
                )

    def test_new_route_is_closed_pinned_and_leaves_the_ordinary_route_unchanged(self):
        workflow = (ROOT / ".github" / "workflows" / "release-reviewed-epic.yml").read_text()
        legacy = (ROOT / ".github" / "workflows" / "release.yml").read_bytes()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertIn("tinyhumansai/.github/.github/workflows/module-release.yml@e045fc567c583a1b83cd9c1edef896179853fa69", workflow)
        self.assertIn("module-crate: tinyhosts", workflow)
        for input_name in ["tag", "version", "reviewed-pr"]:
            self.assertIn(f"      {input_name}:", workflow)
        self.assertEqual(
            hashlib.sha256(legacy).hexdigest(),
            "9f50de454c7fa81350a62358fe18a25ef9afe3f34a593dc34ff30dd1c2c5a8b6",
        )


if __name__ == "__main__":
    unittest.main()
