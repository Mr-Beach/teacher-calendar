#!/bin/sh
# Session start: catch main up with GitHub. Week-file PRs merge there and
# phone sessions push to main directly, so a laptop session can start behind.
# Fast-forward only: never merges, never touches local commits.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ "$(git symbolic-ref --short HEAD 2>/dev/null)" = main ] || exit 0
before=$(git rev-parse HEAD)
if git pull --ff-only --quiet origin main >/dev/null 2>&1; then
  n=$(git rev-list --count "$before"..HEAD)
  [ "$n" -gt 0 ] && printf '{"systemMessage": "Pulled %s new commit(s) from GitHub into main."}\n' "$n"
  exit 0
fi
msg="Could not fast-forward main from GitHub (offline, local commits not on GitHub, or uncommitted changes in the way). Check git status before editing a course file."
printf '{"systemMessage": "%s", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "%s"}}\n' "$msg" "$msg"
