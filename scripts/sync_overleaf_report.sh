#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_PREFIX="report"
REMOTE_NAME="${OVERLEAF_REMOTE_NAME:-overleaf}"

usage() {
  cat <<EOF
Usage:
  bash scripts/sync_overleaf_report.sh push [remote-name]
  bash scripts/sync_overleaf_report.sh pull [remote-name]

Commands:
  push  Push the report subtree to Overleaf's master branch
  pull  Pull Overleaf's master branch back into report/
EOF
}

ensure_repo_root() {
  cd "$ROOT_DIR"
  git rev-parse --is-inside-work-tree >/dev/null
}

ensure_report_dir() {
  if [[ ! -d "$REPORT_PREFIX" ]]; then
    echo "Expected $REPORT_PREFIX/ to exist."
    exit 1
  fi
}

push_report() {
  local remote="${1:-$REMOTE_NAME}"
  git subtree push --prefix="$REPORT_PREFIX" "$remote" master
}

pull_report() {
  local remote="${1:-$REMOTE_NAME}"
  git fetch "$remote" master
  git subtree pull --prefix="$REPORT_PREFIX" "$remote" master --squash
}

main() {
  ensure_repo_root
  ensure_report_dir

  local command="${1:-}"
  shift || true

  case "$command" in
    push)
      push_report "$@"
      ;;
    pull)
      pull_report "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
