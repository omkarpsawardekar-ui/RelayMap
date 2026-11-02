import json
import re

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"

GITHUB_API_VERSION = "2026-03-10"


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_github_name(value: str, field: str) -> str:
    value = value.strip()

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value):
        raise GitHubAPIError(
            f"Invalid GitHub {field}.",
            400,
        )

    return value


def github_get(endpoint: str):
    url = f"{GITHUB_API}{endpoint}"

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "RelayMap-Hackathon",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        if exc.code == 404:
            message = "GitHub repository or resource was not found."
        elif exc.code == 403:
            message = (
                "GitHub API access was limited or blocked. "
                "Check the API rate limit and repository visibility."
            )
        elif exc.code == 401:
            message = "GitHub authentication is required for this resource."
        else:
            message = f"GitHub API returned HTTP {exc.code}."

        raise GitHubAPIError(message, exc.code) from exc

    except URLError as exc:
        raise GitHubAPIError(
            f"Could not connect to GitHub: {exc.reason}",
            502,
        ) from exc

    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GitHubAPIError(
            "GitHub returned an invalid JSON response.",
            502,
        ) from exc


def normalize_person(person):
    if not person:
        return None

    return {
        "login": person.get("login"),
        "profile_url": person.get("html_url"),
    }


def normalize_issue(issue: dict) -> dict:
    return {
        "github_id": issue.get("id"),
        "number": issue.get("number"),
        "title": issue.get("title"),
        "body": issue.get("body"),
        "state": issue.get("state"),
        "state_reason": issue.get("state_reason"),
        "url": issue.get("html_url"),
        "author": normalize_person(issue.get("user")),
        "assignees": [
            normalize_person(person)
            for person in issue.get("assignees", [])
        ],
        "labels": [
            label.get("name")
            for label in issue.get("labels", [])
        ],
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
    }


def normalize_pull_request(pull: dict) -> dict:
    return {
        "github_id": pull.get("id"),
        "number": pull.get("number"),
        "title": pull.get("title"),
        "body": pull.get("body"),
        "state": pull.get("state"),
        "draft": pull.get("draft", False),
        "merged": pull.get("merged", False),
        "url": pull.get("html_url"),
        "author": normalize_person(pull.get("user")),
        "assignees": [
            normalize_person(person)
            for person in pull.get("assignees", [])
        ],
        "base_branch": (pull.get("base") or {}).get("ref"),
        "head_branch": (pull.get("head") or {}).get("ref"),
        "created_at": pull.get("created_at"),
        "updated_at": pull.get("updated_at"),
        "closed_at": pull.get("closed_at"),
        "merged_at": pull.get("merged_at"),
    }


def fetch_github_repository(owner: str, repo: str) -> dict:
    owner = validate_github_name(owner, "owner")
    repo = validate_github_name(repo, "repository name")

    repository = github_get(f"/repos/{owner}/{repo}")

    if repository.get("private"):
        raise GitHubAPIError(
            "This initial connector supports public repositories only.",
            400,
        )

    raw_items = github_get(
        f"/repos/{owner}/{repo}/issues"
        "?state=all&per_page=100&sort=updated&direction=desc"
    )

    raw_pulls = github_get(
        f"/repos/{owner}/{repo}/pulls"
        "?state=all&per_page=100&sort=updated&direction=desc"
    )

    if not isinstance(raw_items, list):
        raise GitHubAPIError(
            "Unexpected response from the GitHub Issues API.",
            502,
        )

    if not isinstance(raw_pulls, list):
        raise GitHubAPIError(
            "Unexpected response from the GitHub Pull Requests API.",
            502,
        )

    # GitHub's Issues endpoint also returns pull requests.
    # Exclude those here so they are not counted twice.
    issues = [
        normalize_issue(item)
        for item in raw_items
        if "pull_request" not in item
    ]

    pull_requests = [
        normalize_pull_request(item)
        for item in raw_pulls
    ]

    return {
        "repository": {
            "id": repository.get("id"),
            "full_name": repository.get("full_name"),
            "description": repository.get("description"),
            "html_url": repository.get("html_url"),
            "default_branch": repository.get("default_branch"),
            "visibility": repository.get("visibility"),
        },
        "issues": issues,
        "pull_requests": pull_requests,
        "counts": {
            "issues": len(issues),
            "pull_requests": len(pull_requests),
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "pagination_note": (
            "This initial version fetches up to 100 issues and "
            "100 pull requests per repository. Larger repositories "
            "will need paginated sync."
        ),
    }