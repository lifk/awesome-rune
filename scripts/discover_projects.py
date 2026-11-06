#!/usr/bin/env -S uv run --script
"""Report GitHub repositories that depend on Rune but are neither listed nor ignored."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv

from generate_readme import PROJECTS_PATH, ROOT, escape_cell, github_get, github_target

IGNORED_PATH = ROOT / "ignored.json"
QUERY = '"anomalyco/rune" filename:Cargo.toml'
UPSTREAM = "anomalyco/rune"
PAGE_SIZE = 100
# The search API returns at most 1,000 results.
MAX_PAGES = 10
# Code search allows 10 requests a minute.
PAGE_DELAY_SECONDS = 7


def search(token: str | None) -> dict[str, list[dict[str, str]]]:
    """Map each matching repository to the manifests that matched."""
    hits: dict[str, list[dict[str, str]]] = {}
    for page in range(1, MAX_PAGES + 1):
        if page > 1:
            time.sleep(PAGE_DELAY_SECONDS)
        data = github_get(
            "/search/code",
            token,
            {"q": QUERY, "per_page": str(PAGE_SIZE), "page": str(page)},
        )
        items = data.get("items", [])
        for item in items:
            hits.setdefault(item["repository"]["full_name"], []).append(
                {"path": item["path"], "url": item["html_url"]}
            )
        if len(items) < PAGE_SIZE:
            break
    return hits


def known_repositories() -> set[str]:
    projects = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["projects"]
    ignored = json.loads(IGNORED_PATH.read_text(encoding="utf-8"))["repositories"]
    known = {UPSTREAM.casefold()}
    known.update(entry["repository"].casefold() for entry in ignored)
    for project in projects:
        target = github_target(project["url"])
        if target is not None:
            known.add(target[0].casefold())
    return known


def candidates(token: str | None) -> list[dict[str, Any]]:
    known = known_repositories()
    found = []
    for repository, manifests in sorted(search(token).items()):
        if repository.casefold() in known:
            continue
        try:
            metadata = github_get(f"/repos/{repository}", token)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            print(f"warning: skipping {repository}: {error}", file=sys.stderr)
            continue
        # Renamed repositories resolve to their canonical name, which may be listed.
        if metadata["full_name"].casefold() in known or metadata.get("fork") or metadata.get("archived"):
            continue
        found.append({"metadata": metadata, "manifests": manifests})
    found.sort(key=lambda entry: (-entry["metadata"]["stargazers_count"], entry["metadata"]["full_name"].casefold()))
    return found


def render(found: list[dict[str, Any]]) -> str:
    lines = [
        "Repositories whose `Cargo.toml` mentions `anomalyco/rune` but that are in neither "
        "`projects.json` nor `ignored.json`. Updated weekly by `.github/workflows/discover.yml`.",
        "",
        "For each one, add it to `projects.json` or record why it is left out in `ignored.json`; "
        "either way it stops appearing here.",
        "",
        "| Repository | Stars | Last push | Description | Matched |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for entry in found:
        metadata = entry["metadata"]
        manifests = ", ".join(f"[`{escape_cell(m['path'])}`]({m['url']})" for m in entry["manifests"])
        description = escape_cell(metadata.get("description") or "")
        lines.append(
            f"| [{metadata['full_name']}]({metadata['html_url']}) | {metadata['stargazers_count']} | "
            f"{(metadata.get('pushed_at') or '')[:10]} | {description} | {manifests} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the Markdown report here instead of stdout")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required: the code search API rejects anonymous requests.", file=sys.stderr)
        return 1

    found = candidates(token)
    report = render(found)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"count={len(found)}\n")
    print(f"Found {len(found)} new candidate(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
