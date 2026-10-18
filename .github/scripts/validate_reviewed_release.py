"""Validate a reviewed TinyHosts release request before routing it upstream."""

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z")
POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*\Z")


def release_route(tag, version, reviewed_pr, ref):
    """Validate dispatch inputs and return the fixed TinyHosts release route."""
    if ref != "refs/heads/main":
        raise ValueError("reviewed releases can only run from main")
    if not VERSION.fullmatch(version) or tag != f"v{version}":
        raise ValueError("tag must be v-prefixed and match the requested version")
    if not POSITIVE_INTEGER.fullmatch(reviewed_pr):
        raise ValueError("reviewed-pr must be a positive integer")
    return {
        "tag": tag,
        "version": version,
        "reviewed-pr": int(reviewed_pr),
        "module-crate": "tinyhosts",
    }


def validate_reviewed_pr(pull, reviews, repository, number):
    """Require a merged main PR with a current approval from someone else."""
    if pull.get("number") != number:
        raise ValueError("reviewed-pr did not resolve to the requested pull request")
    if pull.get("state") != "closed" or pull.get("merged") is not True or not pull.get("merged_at"):
        raise ValueError("reviewed-pr must be merged and closed")
    base = pull.get("base") or {}
    base_repo = base.get("repo") or {}
    if base.get("ref") != "main" or base_repo.get("full_name", "").lower() != repository.lower():
        raise ValueError("reviewed-pr must target this repository's main branch")

    author = (pull.get("user") or {}).get("login", "").lower()
    head_sha = (pull.get("head") or {}).get("sha")
    if not author or not head_sha:
        raise ValueError("reviewed-pr is missing its author or merged head")

    latest_reviews = {}
    for review in reviews:
        reviewer = (review.get("user") or {}).get("login", "").lower()
        if reviewer and review.get("commit_id") == head_sha:
            latest_reviews[reviewer] = review
    if not any(
        reviewer != author and review.get("state", "").upper() == "APPROVED"
        for reviewer, review in latest_reviews.items()
    ):
        raise ValueError("reviewed-pr has no current approval from another user")


def github_json(repository, path, token):
    """Fetch one JSON response from the GitHub REST API."""
    request = Request(
        f"https://api.github.com/repos/{repository}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError("could not verify reviewed-pr with GitHub") from error


def main():
    try:
        route = release_route(
            os.environ["TAG"],
            os.environ["VERSION"],
            os.environ["REVIEWED_PR"],
            os.environ["GITHUB_REF"],
        )
        repository = os.environ["GITHUB_REPOSITORY"]
        token = os.environ["GITHUB_TOKEN"]
        number = route["reviewed-pr"]
        pull = github_json(repository, f"pulls/{number}", token)
        reviews = github_json(repository, f"pulls/{number}/reviews?per_page=100", token)
        if not isinstance(reviews, list):
            raise ValueError("GitHub returned an invalid reviewed-pr response")
        validate_reviewed_pr(pull, reviews, repository, number)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for name in ("tag", "version"):
                output.write(f"{name}={route[name]}\n")
    except (KeyError, ValueError) as error:
        print(f"reviewed release validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
