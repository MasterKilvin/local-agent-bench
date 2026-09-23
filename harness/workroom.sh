#!/usr/bin/env bash
# Safe workroom: run a command against a throwaway copy of one git repository
# inside a rootless Podman container with no network. Copy and container are
# removed afterwards, even on failure.
# Usage: workroom.sh <git-repo> <timeout-seconds> -- <command...>
set -euo pipefail
repo=$(realpath "$1"); limit=$2; shift 2; [ "${1:-}" = "--" ] && shift
IMAGE=${WORKROOM_IMAGE:-docker.io/library/python:3.12-slim}
job="wr-$(date +%Y%m%d-%H%M%S)-$$"
base=${XDG_RUNTIME_DIR:?}/workroom; mkdir -p "$base"; chmod 700 "$base"
copy="$base/$job"
cleanup() { podman rm -f "$job" >/dev/null 2>&1 || true; rm -rf "$copy"; }
trap cleanup EXIT

# Committed files only: untracked files (.env, local keys) never enter the copy.
git clone -q --no-hardlinks --no-local "$repo" "$copy"
rm -rf "$copy/.git/hooks"; git -C "$copy" remote remove origin 2>/dev/null || true

# Refuse copies that contain secret-looking files or key material.
bad=$(find "$copy" -path "$copy/.git" -prune -o -type f \( -name '.env*' -o -name '*.pem' -o -name '*.key' \
  -o -name 'id_rsa*' -o -name 'id_ed25519*' -o -name '*.p12' -o -name 'credentials*' \) -print)
bad+=$(grep -rIl --exclude-dir=.git -E 'BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{32,}|ghp_[A-Za-z0-9]{36}' "$copy" || true)
if [ -n "$bad" ]; then echo "workroom: refused, secret-looking content:" >&2; echo "$bad" | sed "s|$copy/||" >&2; exit 3; fi

echo "workroom: job $job, repo $(basename "$repo"), limit ${limit}s" >&2
timeout --kill-after=10 "$limit" podman run --rm --name "$job" \
  --network none --read-only --tmpfs /tmp:rw,size=512m --tmpfs /home/worker:rw,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 8g --cpus 8 \
  --userns keep-id --user "$(id -u):$(id -g)" -e HOME=/home/worker \
  -v "$copy":/work:rw -w /work "$IMAGE" "$@"
