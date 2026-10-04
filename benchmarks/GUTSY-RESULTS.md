# Gutsy versus local Kev 4B — 2026-10-04

On the identical 200-case test split, CPU Gutsy Q8_0 v0.4 matched 125 labels
(62.5%) and local CUDA Kev 4B matched 132 (66.0%). Always selecting circuit
breaker, fixed from development, matches 117 (58.5%). Seven cases separate the
model totals; this small exploratory sample does not establish general superiority.
Neither result is a trading-performance estimate or independently verified truth.

| Backend | Dev agreement | Test agreement | Test median latency | Test p95 latency |
| --- | ---: | ---: | ---: | ---: |
| Kev 4B CUDA | 63.5% | 66.0% | 49 ms | 52 ms |
| Gutsy 0.8B Q8_0 CPU | 55.0% | 62.5% | 839 ms | 868 ms |
| Always circuit breaker | 63.0% | 58.5% | Not measured | Not measured |

All 400 paired cases completed for both models, with zero errors. Gutsy's
rejection mass never exceeded every supplied option's unconditional mass on
these cases: zero native rejections under the predefined largest-mass rule.
Consequently conditional agreement and accepted-case agreement are identical
here. The test confusion counts were:

| Recorded label | Kev entry | Kev abort | Gutsy entry | Gutsy abort |
| --- | ---: | ---: | ---: | ---: |
| Entry (83) | 38 | 45 | 29 | 54 |
| Abort (117) | 23 | 94 | 21 | 96 |

Mean test Brier sums over the two conditional options were 0.372 for Kev and
0.471 for Gutsy. These conditional scores do not measure correct rejection.
Probabilities remain uncalibrated on the user's advisory/trading workflow.

## Abstention smoke checks

Both models selected insufficient_information on three synthetic advisory
fixtures missing spread, account exposure or transaction-cost estimates.
Those fixtures included an explicit user-defined rule requiring that evidence.
Gutsy's native reject mass was about 0.00009; it selected the explicit
insufficient-information option instead. Missing/stale structural input checks
also passed through the actual Gutsy HTTP MCP endpoint, without inference.

A separate synthetic choice question permitted neither offered action. Gutsy
returned reject=0.836964 while its conditional choice was replace at 0.674922.
The adapter preserves the reject mass and derives unconditional option masses;
ignoring reject would have produced a misleading apparent commitment. The
adapter's largest-mass rejection behaviour is also covered by unit tests.
These few fixtures do not establish abstention accuracy on real requests.

## Resources, reproducibility and limits

Gutsy uses runtime 0.4.0 and the Q8_0 model/calibration from Hugging Face revision
bb1dde4c571b2588801c27d155da005a87d05285, four CPU threads and no GPU layers.
The runtime cache self-check passed. Observed Docker resident memory ranged
from roughly 460 to 610 MiB in two samples; these are not peak or full system
memory estimates and exclude broader host file-cache accounting. It uses no
CUDA allocation. Kev reports the pinned 4B checkpoint
139fdd94f1b6a6ad80cc15e08fcb99cac885a101 on CUDA in bfloat16.

scripts/compare-gutsy.py uses the exact existing 400 cases and questions with
dataset SHA-256 e56aec4c56df8b2ede21391f8b5d346db52a8e580c99ebc634fafb265f587d06.
It alternates backend order and excludes one warmup request per model. Raw
results include IDs, probabilities/reject, model metadata, timings and adapter
hash under benchmarks/private/project23/gutsy-comparison.json (Git-ignored).
Additional smoke requests were made during the run, so latency is an observed
local-workload measurement, not an isolated load test. CPU/GPU hardware differs.
No options, prompts or rejection thresholds were tuned using this test split.

Project23 source labels remain unverified and have no timestamps/outcomes.
Grouping and duplicate filtering are documented in PROJECT23-RESULTS.md.
The earlier 68.5% remote Kev 0.8B result is separate from this paired local 4B run.
This two-option evaluation does not validate the three-way advisory prompt,
trade arguments, arithmetic, position sizing, authorisation or live returns.

The adapter suite passed 95 tests; deployment and response differences are in
docs/GUTSY-COMPARISON.md. Both backends remain running on separate endpoints.
Keep Kev as the current advisory backend. Gutsy is available for further paper
comparisons where low resource use matters; this run does not justify promoting it.
