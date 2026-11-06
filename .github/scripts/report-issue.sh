#!/usr/bin/env bash
# Keep one open issue per label in sync with a report: open or update it while
# the report has findings, and close it once they are gone.
#
# Usage: report-issue.sh <label> <title> <body-file> <finding-count>
set -euo pipefail

label=$1
title=$2
body=$3
findings=$4

gh label create "$label" --color ededed --description "Opened by a scheduled workflow" --force >/dev/null
number=$(gh issue list --label "$label" --state open --limit 1 --json number --jq '.[0].number // empty')

if [ "$findings" -gt 0 ]; then
  if [ -n "$number" ]; then
    gh issue edit "$number" --title "$title" --body-file "$body"
  else
    gh issue create --title "$title" --label "$label" --body-file "$body"
  fi
elif [ -n "$number" ]; then
  gh issue close "$number" --comment "Nothing left to report as of $(date -u +%F)."
else
  echo "Nothing to report."
fi
