#!/usr/bin/env bash
# Overnight queue for bench v2 (owner "go", Sept 22 night): arms in sequence, one process, native systemd unit,
# GPU lock per arm (the shared GPU lock), model unloaded between arms, status in RUN-STATUS.md for any session to read.
set -u
cd "${BENCH_DIR:-$(dirname "$0")}" || exit 1
mkdir -p logs results
S=RUN-STATUS.md; ARMS=${ARMS:-"1 2 3 4 8 9"}
note() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$S"; }
if [ "${APPEND:-0}" = 1 ]; then note "continuation: arms $ARMS (frozen set $(sha256sum ../tasks/tasks-v2-frozen.jsonl | cut -c1-16))"
else { echo "# Bench v2 overnight run"; echo; echo "Started $(date '+%F %T'); arms: $ARMS; frozen set sha256: $(sha256sum ../tasks/tasks-v2-frozen.jsonl | cut -c1-16)"; echo; } > "$S"; fi
for arm in $ARMS; do
  note "arm $arm: starting"
  ./arms-v2.sh "$arm" > "logs/overnight-arm-$arm.log" 2>&1
  rc=$?
  last=$(ls -dt results/v2-*-"$arm"-* 2>/dev/null | head -1)
  if [ -n "$last" ] && [ -f "$last/summary.json" ]; then
    note "arm $arm: done (exit $rc) -> $last :: $(python3 -c "import json;s=json.load(open('$last/summary.json'));print(s['passed'],'/',s['n'],'pass',round(s['pass_rate'],3),'| by_kind',s['by_kind'],'| timeouts',s['timeouts'])")"
  else
    note "arm $arm: FAILED (exit $rc), no summary; see logs/overnight-arm-$arm.log"
  fi
  OLLAMA_HOST=127.0.0.1:11435 ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}' | xargs -r -n1 env OLLAMA_HOST=127.0.0.1:11435 ollama stop >/dev/null 2>&1
done
note "queue finished; GPU memory now: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
