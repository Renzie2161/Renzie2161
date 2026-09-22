#!/usr/bin/env python3
"""Update dynamic sections in the profile README using GitHub's public API."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USERNAME = os.getenv("PROFILE_USERNAME", "Renzie2161")
PROFILE_REPO = f"{USERNAME}/{USERNAME}".lower()
README = Path(os.getenv("PROFILE_README", "README.md"))
TOKEN = os.getenv("GITHUB_TOKEN", "")
API_VERSION = "2026-03-10"


def github_get(path: str):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": f"{USERNAME}-profile-readme",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {exc.code} for {path}: {body}") from exc


def md_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def repo_url(full_name: str) -> str:
    return f"https://github.com/{full_name}"


def render_activity(events: list[dict], limit: int = 5) -> str:
    rows: list[str] = []

    for event in events:
        repo = event.get("repo", {}).get("name", "")
        if not repo or repo.lower() == PROFILE_REPO:
            continue

        event_type = event.get("type", "")
        payload = event.get("payload", {})
        url = repo_url(repo)
        repo_md = f"[`{repo}`]({url})"

        if event_type == "PushEvent":
            count = payload.get("size") or len(payload.get("commits", [])) or 1
            verb = "commit" if count == 1 else "commits"
            text = f"pushed **{count} {verb}** to {repo_md}"
        elif event_type == "CreateEvent":
            ref_type = payload.get("ref_type", "thing")
            ref = payload.get("ref")
            suffix = f" `{md_escape(str(ref))}`" if ref else ""
            text = f"created {ref_type}{suffix} in {repo_md}"
        elif event_type == "PullRequestEvent":
            action = payload.get("action", "updated")
            number = payload.get("number")
            text = f"{action} PR #{number} in {repo_md}" if number else f"{action} a pull request in {repo_md}"
        elif event_type == "IssuesEvent":
            action = payload.get("action", "updated")
            issue = payload.get("issue", {})
            number = issue.get("number")
            text = f"{action} issue #{number} in {repo_md}" if number else f"{action} an issue in {repo_md}"
        elif event_type == "IssueCommentEvent":
            issue = payload.get("issue", {})
            number = issue.get("number")
            text = f"commented on issue/PR #{number} in {repo_md}" if number else f"commented in {repo_md}"
        elif event_type == "ReleaseEvent":
            action = payload.get("action", "published")
            tag = payload.get("release", {}).get("tag_name")
            suffix = f" `{md_escape(str(tag))}`" if tag else ""
            text = f"{action} release{suffix} in {repo_md}"
        elif event_type == "ForkEvent":
            text = f"forked {repo_md}"
        elif event_type == "WatchEvent":
            text = f"starred {repo_md}"
        else:
            continue

        created = event.get("created_at", "")
        date = created[:10] if created else "recently"
        rows.append(f"- `{date}` — {text}")
        if len(rows) >= limit:
            break

    return "\n".join(rows) if rows else "- No recent public activity to show yet."


def render_projects(repos: list[dict], limit: int = 4) -> str:
    visible = [
        r for r in repos
        if not r.get("fork")
        and not r.get("archived")
        and r.get("full_name", "").lower() != PROFILE_REPO
    ]
    visible.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)

    rows: list[str] = []
    for repo in visible[:limit]:
        name = md_escape(repo.get("name", "repository"))
        full_name = repo.get("full_name", f"{USERNAME}/{name}")
        description = md_escape(repo.get("description") or "no description yet")
        language = md_escape(repo.get("language") or "mixed")
        stars = repo.get("stargazers_count", 0)
        rows.append(
            f"- **[{name}]({repo_url(full_name)})** — {description}  \n"
            f"  `{language}` · ★ {stars}"
        )

    return "\n".join(rows) if rows else "- No public projects to show yet."


def replace_section(text: str, marker: str, body: str) -> str:
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{body.rstrip()}\n{end}"
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not find README markers for {marker}")
    return new_text


def main() -> None:
    events = github_get(f"/users/{USERNAME}/events/public?per_page=30")
    repos = github_get(f"/users/{USERNAME}/repos?per_page=100&sort=pushed&direction=desc")

    text = README.read_text(encoding="utf-8")
    text = replace_section(text, "DYNAMIC_ACTIVITY", render_activity(events))
    text = replace_section(text, "DYNAMIC_PROJECTS", render_projects(repos))

    timestamp = datetime.now(timezone.utc).strftime("last refreshed %Y-%m-%d %H:%M UTC")
    text = replace_section(text, "DYNAMIC_UPDATED", timestamp)

    README.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
