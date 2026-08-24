"""Small GitHub REST client that respects normal platform rate limits."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import IssueSnapshot, RepositorySnapshot


class GitHubError(RuntimeError):
    """An upstream request failed or returned an unusable response."""


class GitHubRateLimitError(GitHubError):
    """GitHub requested that the client stop making requests."""


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repository: str
    number: int

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repository}"


def parse_issue_url(value: str) -> IssueRef:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValueError("Use an HTTPS issue URL on github.com")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 4 or parts[2] != "issues":
        raise ValueError("Expected https://github.com/OWNER/REPO/issues/NUMBER")
    try:
        number = int(parts[3])
    except ValueError as exc:
        raise ValueError("Issue number must be a positive integer") from exc
    if number < 1:
        raise ValueError("Issue number must be a positive integer")
    return IssueRef(parts[0], parts[1], number)


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: float = 12.0):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout

    def _get(self, path: str) -> dict:
        request = Request(
            f"https://api.github.com{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "BountyProof/0.1",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in {403, 429}:
                retry_after = exc.headers.get("Retry-After", "the documented reset")
                raise GitHubRateLimitError(
                    f"GitHub rejected the request; retry after {retry_after}."
                ) from exc
            if exc.code == 404:
                raise GitHubError("The issue or repository was not found.") from exc
            raise GitHubError(f"GitHub returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise GitHubError(f"GitHub request failed: {exc.reason}") from exc

    def issue(self, ref: IssueRef) -> IssueSnapshot:
        value = self._get(f"/repos/{ref.full_name}/issues/{ref.number}")
        return IssueSnapshot(
            url=value["html_url"],
            state=value["state"],
            title=value.get("title", ""),
            body=value.get("body") or "",
            comments=value.get("comments", 0),
            updated_at=value.get("updated_at"),
            author_association=value.get("author_association", "NONE"),
            locked=value.get("locked", False),
        )

    def repository(self, ref: IssueRef) -> RepositorySnapshot:
        value = self._get(f"/repos/{ref.full_name}")
        return RepositorySnapshot(
            full_name=value["full_name"],
            archived=value.get("archived", False),
            disabled=value.get("disabled", False),
            pushed_at=value.get("pushed_at"),
            stargazers_count=value.get("stargazers_count", 0),
        )
