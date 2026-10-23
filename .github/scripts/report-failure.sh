#!/usr/bin/env bash
# Open (or comment on) one tracking issue per workflow when a scheduled run fails,
# so a silent upstream API change can't go unnoticed for days.
set -euo pipefail
title="Scheduled ${GITHUB_WORKFLOW} run failing"
run_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
existing=$(gh issue list --state open --label pipeline-failure --search "in:title \"${title}\"" \
  --json number -q '.[0].number')
if [ -n "${existing}" ]; then
  gh issue comment "${existing}" --body "Failed again: ${run_url}"
else
  gh label create pipeline-failure --color B60205 --description "Scheduled pipeline run failed" 2>/dev/null || true
  gh issue create --title "${title}" --label pipeline-failure \
    --body "The scheduled \`${GITHUB_WORKFLOW}\` workflow failed: ${run_url}. Close this issue once it is fixed."
fi
