# Bench v2 FREEZE — 2026-09-22 23:20:54

Owner: "go" (Sept 22 night). Set validated 20/20 after both fix rounds. Any change to these files after this line is a new version, not this one.

7c8fddf11146cdeeb8aabe874ce898f4d3aa3cdc668cea0455ddabea95be073e  tasks-v2.jsonl
5563a27b38110e24afe54493d142deff0d0f006de1a965a74f28586cf634c152  run.py
274a367f3d198f290cc96ba162df9c2046efac4aa58e8eda47008eb6c68b291d  refusal.py
b10c15f629b31f065be262998c60c01383850dc4ded8d839603c764f9c679369  bridge.py
7c8fddf11146cdeeb8aabe874ce898f4d3aa3cdc668cea0455ddabea95be073e  tasks-v2.jsonl
5563a27b38110e24afe54493d142deff0d0f006de1a965a74f28586cf634c152  run.py
274a367f3d198f290cc96ba162df9c2046efac4aa58e8eda47008eb6c68b291d  refusal.py
b10c15f629b31f065be262998c60c01383850dc4ded8d839603c764f9c679369  bridge.py
ea01f440cb10de95dea38b3bac099a866dcd84fd04b751be68832ec8b1ca9567  ../../workroom/workroom.sh
1a246cabd5ea07c719c2627dfaaf6accc7f50bed44e1182c3a4ded3cc10f9bd2  pi-maxturns.ts
4d200d1368e923e96ffbd887ccf17b66d3374b4de625241cbcda017da20f9c43  Containerfile.deps
bd365e9b4d51b7a88fee5eb79432b37be52167846a0fe97addbcf99664246953  arms-v2.sh
ced35f33d8106f10cb6b2badfc1a7ad7fa5983f716e3b2ef4a8629ac36323d84  overnight-v2.sh

images: 1203913142c72c18fc3
ollama: ollama version is 0.33.3
agents: pi 0.87.0, opencode 1.18.32, goose  1.51.0
models: qwen3.8:27b-q8-24k=3fa93254c899 qwen3.8:27b-q4-24k=795961fa4710 qwen3.8:27b-q8_0=8f5fb6b71ea0 qwen3.8:27b-64k=67a1c5bfe600 qwen3.8:27b=22130167c4c2 qwen3-coder:30b=06c1097efce0 

## Published copy (added for the public repository)
`run.py` here differs from the frozen `5563a27b…` in four lines: the sandbox-script and task-file paths, and two comments,
so it runs from this folder. `refusal.py` and `bridge.py` are byte-identical. The published task file drops the `source`
bookkeeping field; its sha256 is `cb4645681f754b38…`, with task content, hidden tests and reference fixes unchanged.
