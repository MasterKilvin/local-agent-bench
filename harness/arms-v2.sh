#!/usr/bin/env bash
# Bench v2 arms (PLAN-v2 §2). One arm per invocation: arms-v2.sh <arm>. Every arm runs under the GPU lock via
# the GPU lock wrapper, records the environment manifest, and unloads the model before the lock is
# released (the Sept 21 trap). Nothing here runs until the task set is frozen.
set -u
cd "${BENCH_DIR:-$(dirname "$0")}" || exit 1
export AGENTROOM_IMAGE=localhost/bench-agentroom-deps:1 WORKROOM_IMAGE=localhost/bench-agentroom-deps:1
export OLLAMA_HOST=127.0.0.1:11435
TASKS=../tasks/tasks-v2-frozen.jsonl; STAMP=$(date +%Y%m%d)
arm=${1:?arm name}
manifest() {  # environment manifest next to the results (CAPTURE-SPEC field 11)
  local out=$1; mkdir -p "$out"
  { echo "arm=$arm"; echo "date=$(date -Is)"; nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    ollama --version; echo "kv_cache_type=${OLLAMA_KV_CACHE_TYPE:-default(f16)}"; echo "flash_attention=${OLLAMA_FLASH_ATTENTION:-default}"
    for m in "${@:2}"; do echo "model=$m digest=$(ollama show "$m" --modelfile 2>/dev/null | grep -m1 '^FROM' )"; done
    sha256sum "$TASKS" run.py refusal.py bridge.py | sed 's/^/sha256 /'; } > "$out/MANIFEST.txt"
}
run() {  # run <agent> <model> <repeats> <outdir> [extra run.py args]
  local agent=$1 model=$2 reps=$3 out=$4; shift 4
  manifest "$out" "$model"
  python3 run.py --v2 --taskfile "$TASKS" --agent "$agent" --model "$model" --repeats "$reps" --timeout 900 --out "$out" "$@"
  local rc=$? rows=0 expected
  ollama stop "$model" 2>/dev/null
  if [ -f "$out/results.jsonl" ]; then
    rows=$(wc -l < "$out/results.jsonl")
  fi
  expected=$(wc -l < "$TASKS")
  expected=$((expected * reps))
  printf 'rc=%d rows=%d expected=%d\n' "$rc" "$rows" "$expected" > "$out/EXIT"
  if [ "$rc" -ne 0 ]; then
    return "$rc"
  fi
  [ "$rows" -eq "$expected" ]
}
case "$arm" in
  1|baseline)  ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run pi qwen3.8:27b-64k 3 results/v2-$STAMP-1-baseline-pi-27b --thinking medium ;;
  2|goose)     ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run goose qwen3.8:27b-64k 3 results/v2-$STAMP-2-goose-27b ;;
  3|opencode)  ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run opencode qwen3.8:27b-64k 3 results/v2-$STAMP-3-opencode-27b --thinking medium ;;
  4|coder)     ollama create qwen3-coder:30b-64k -f Modelfile.qwen3-coder-30b-64k >/dev/null; run pi qwen3-coder:30b-64k 3 results/v2-$STAMP-4-pi-coder30b ;;   # coder model has no thinking mode
  5|kvq4)      echo "KV Q4 arm: needs OLLAMA_KV_CACHE_TYPE=q4_0 on the Ollama SERVICE (a restart), same flash-attention setting as the control; not runnable from here" ; exit 2 ;;
  A|anchors)   ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; TASKS=../tasks/tasks-anchors.jsonl; run pi qwen3.8:27b-64k 3 results/v2-$STAMP-A-anchors-pi-27b --thinking medium ;;
  6|thinklow)  ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run pi qwen3.8:27b-64k 2 results/v2-$STAMP-6-pi-27b-thinklow --thinking low ;;
  7|thinkhigh) ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run pi qwen3.8:27b-64k 2 results/v2-$STAMP-7-pi-27b-thinkhigh --thinking high ;;
  8|q8)        ollama create qwen3.8:27b-q8-24k -f Modelfile.qwen3.8-27b-q8-24k >/dev/null; run pi qwen3.8:27b-q8-24k 3 results/v2-$STAMP-8-pi-27b-q8-24k --thinking medium --ctx 24576 ;;
  9|q4ctl)     ollama create qwen3.8:27b-q4-24k -f Modelfile.qwen3.8-27b-q4-24k >/dev/null; run pi qwen3.8:27b-q4-24k 3 results/v2-$STAMP-9-pi-27b-q4-24k --thinking medium --ctx 24576 ;;
  11|omp)     ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run omp qwen3.8:27b-64k 3 results/v2-$STAMP-11-omp-27b --thinking medium --ctx 65536 ;;   # Oh My Pi 18.2.11 (added Sept 23)
  12|qwen)    ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run qwen qwen3.8:27b-64k 3 results/v2-$STAMP-12-qwencode-27b --ctx 65536 ;;   # Qwen Code 0.24.4 (added Sept 23)
  13|dsh-min) ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run dsh-min qwen3.8:27b-64k 3 results/v2-$STAMP-13-dsh-min-27b --ctx 65536 ;;   # DeepSeek Harness 0.1.5-rc.3, sdk-minimal
  14|dsh-std) ollama create qwen3.8:27b-64k -f Modelfile.qwen3.8-27b-64k >/dev/null; run dsh-std qwen3.8:27b-64k 3 results/v2-$STAMP-14-dsh-std-27b --ctx 65536 ;;   # DeepSeek Harness 0.1.5-rc.3, sdk (standard)
  *) echo "unknown arm $arm"; exit 2 ;;
esac
