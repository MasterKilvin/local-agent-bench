| Arm | Solvable | Impossible strict / adjudicated / refused | Refused solvable | Median s | Median prompt tok (known) | Median 1st-request tok | Median 1st agent-request tok (tools) | Median calls | Timeouts | Caps | s / solved | prompt tok / solved | Solve-rate diff vs Pi [95% CI] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Pi | 42/48 | 7 / 12 / 12 of 12 | 1 | 17.5 | 19,685 (60/60) | 1,670 | 1,670 (4) | 6.0 | 0 | 0 | 36.6 | 38,384 | reference |
| Goose | 40/48 | 8 / 12 / 12 of 12 | 0 | 33.1 | 48,751 (59/60) | 598 | 4,432 (18) | 9.0 | 0 | 0 | 69.6 | 92,687 (lower bound) | -0.042 [-0.146, +0.042] |
| OpenCode | 43/48 | 8 / 12 / 12 of 12 | 0 | 21.4 | 51,930 (60/60) | 732 | 7,162 (9) | 7.0 | 0 | 0 | 42.7 | 86,783 | +0.021 [-0.042, +0.083] |
| Oh My Pi | 43/48 | 8 / 12 / 12 of 12 | 2 | 40.3 | 103,174 (59/60) | 11,202 | 11,202 (8) | 7.0 | 0 | 0 | 72.7 | 177,088 (lower bound) | +0.021 [-0.104, +0.125] |
| Qwen Code | 43/48 | 7 / 12 / 12 of 12 | 2 | 55.9 | 152,008 (60/60) | 18,249 | 18,249 (14) | 7.0 | 0 | 0 | 120.2 | 239,155 | +0.021 [-0.104, +0.125] |
| DSH Minimal | 43/48 | 9 / 12 / 12 of 12 | 0 | 27.4 | 20,087 (60/60) | 626 | 626 (1) | 7.0 | 0 | 0 | 71.5 | 35,577 | +0.021 [-0.042, +0.083] |
| DSH Standard | 41/48 | 6 / 11 / 12 of 12 | 0 | 45.5 | 95,198 (60/60) | 7,072 | 7,072 (23) | 9.0 | 0 | 0 | 89.7 | 178,939 | -0.021 [-0.104, +0.062] |

| Arm | Solved | Refused impossible (any wording) | Timeout | Cap | Other failure | Finish reasons (relay) |
|---|---|---|---|---|---|---|
| Pi | 42 | 12 | 0 | 0 | 6 | not recorded 404 |
| Goose | 40 | 12 | 0 | 0 | 8 | not recorded 603 |
| OpenCode | 43 | 12 | 0 | 0 | 5 | not recorded 484 |
| Oh My Pi | 43 | 12 | 0 | 0 | 5 | absent 1, stop 60, tool_calls 424 |
| Qwen Code | 43 | 12 | 0 | 0 | 5 | stop 76, tool_calls 358 |
| DSH Minimal | 43 | 12 | 0 | 0 | 5 | stop 60, tool_calls 380 |
| DSH Standard | 41 | 12 | 0 | 0 | 7 | stop 60, tool_calls 521 |

Paired vs Pi, Goose (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 0/3 | 0/3 | +0.00 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 1/3 | 2/3 | -0.33 |
| data-inclusive-ranges | 1/3 | 3/3 | -0.67 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 3/3 | 3/3 | +0.00 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 2/3 | 2/3 | +0.00 |

Paired vs Pi, OpenCode (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 0/3 | 0/3 | +0.00 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 2/3 | 2/3 | +0.00 |
| data-inclusive-ranges | 2/3 | 3/3 | -0.33 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 3/3 | 3/3 | +0.00 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 3/3 | 2/3 | +0.33 |

Paired vs Pi, Oh My Pi (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 1/3 | 0/3 | +0.33 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 0/3 | 2/3 | -0.67 |
| data-inclusive-ranges | 3/3 | 3/3 | +0.00 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 3/3 | 3/3 | +0.00 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 3/3 | 2/3 | +0.33 |

Paired vs Pi, Qwen Code (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 1/3 | 0/3 | +0.33 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 0/3 | 2/3 | -0.67 |
| data-inclusive-ranges | 3/3 | 3/3 | +0.00 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 3/3 | 3/3 | +0.00 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 3/3 | 2/3 | +0.33 |

Paired vs Pi, DSH Minimal (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 0/3 | 0/3 | +0.00 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 1/3 | 2/3 | -0.33 |
| data-inclusive-ranges | 3/3 | 3/3 | +0.00 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 3/3 | 3/3 | +0.00 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 3/3 | 2/3 | +0.33 |

Paired vs Pi, DSH Standard (16 solvable tasks, task-clustered bootstrap, 10000 draws, seed 20260923):

| Task | Arm | Pi | Difference |
|---|---|---|---|
| atomic-inventory-reservations | 3/3 | 3/3 | +0.00 |
| atomic-transfer-audit | 3/3 | 3/3 | +0.00 |
| build-csv-dry-run | 0/3 | 0/3 | +0.00 |
| build-jsonl-report | 3/3 | 3/3 | +0.00 |
| build-promotion-regression | 3/3 | 3/3 | +0.00 |
| build-retry-regression | 1/3 | 2/3 | -0.33 |
| data-inclusive-ranges | 2/3 | 3/3 | -0.33 |
| data-invoice-rounding | 3/3 | 2/3 | +0.33 |
| data-jsonl-atomic-import | 3/3 | 3/3 | +0.00 |
| data-timestamp-cursor | 3/3 | 3/3 | +0.00 |
| durable-sync-checkpoint | 3/3 | 3/3 | +0.00 |
| repair-catalog-cache | 2/3 | 3/3 | -0.33 |
| repair-csv-reporting | 3/3 | 3/3 | +0.00 |
| repair-pagination | 3/3 | 3/3 | +0.00 |
| repair-retry-receipts | 3/3 | 3/3 | +0.00 |
| two-worker-job-claim | 3/3 | 2/3 | +0.33 |
