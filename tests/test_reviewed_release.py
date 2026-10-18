"""Contract tests for the reviewed TinyHosts release route."""

import importlib.util
import json
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


class ReviewedReleaseContractTests(unittest.TestCase):
    def test_routes_a_valid_reviewed_release(self):
        route = release.release_route(
            tag="v0.4.2",
            version="0.4.2",
            reviewed_pr="42",
            ref="refs/heads/main",
        )
        self.assertEqual(
            route,
            {"tag": "v0.4.2", "version": "0.4.2", "reviewed-pr": 42},
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
            pull_request(), reviews, repository="tinyhumansai/tinyhosts", number=42
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
            (pull_request(state="open", merged=False, merged_at=None), approved),
            (pull_request(merged=False, merged_at=None), approved),
            (pull_request(base={"ref": "release", "repo": {"full_name": "tinyhumansai/tinyhosts"}}), approved),
            (pull_request(base={"ref": "main", "repo": {"full_name": "attacker/tinyhosts"}}), approved),
            (pull_request(), []),
            (
                pull_request(),
                [{"user": {"login": "author"}, "state": "APPROVED", "commit_id": "abc123"}],
            ),
            (
                pull_request(),
                [{"user": {"login": "reviewer"}, "state": "APPROVED", "commit_id": "old"}],
            ),
        ]
        for pull, reviews in cases:
            with self.subTest(pull=pull, reviews=reviews), self.assertRaises(ValueError):
                release.validate_reviewed_pr(
                    pull, reviews, repository="tinyhumansai/tinyhosts", number=42
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
            json.dumps({"legacy_workflow_sha256": __import__("hashlib").sha256(legacy).hexdigest()}),
            '{"legacy_workflow_sha256": "fc76c1d8dd5487bda978502932107d8cfa1ed671"}',
        )


if __name__ == "__main__":
    unittest.main()
