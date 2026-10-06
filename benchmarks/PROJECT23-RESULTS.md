# Project23 exploratory routing benchmark — 2026-10-03

Kev 0.8B on the remote LAN server matched 137/200 test labels (68.5%), versus
117/200 (58.5%) for the development-selected majority baseline: always choose
trigger_circuit_breaker. Development agreement was also 137/200 (68.5%),
versus its 126/200 (63%) majority baseline. All 400 requests completed.

| Test recorded label | Kev entry | Kev circuit breaker |
| --- | ---: | ---: |
| execute_entry | 31 | 52 |
| trigger_circuit_breaker | 11 | 106 |

Entry recall against these labels was 31/83 (37.3%); abort recall was 106/117
(90.6%). This is a conservative choice pattern relative to the recorded labels.
It does not establish whether any of those trades would have succeeded.
Median measured end-to-end request latency was 244 ms on development and
248 ms on test, excluding one warmup request. Mean multiclass Brier sums were
0.442 and 0.416 respectively; these are descriptive scores, not a calibrated
dispatch policy. No routing threshold was selected.

## Construction and label review

Source: Project23's synthetic-state-action-alpha-balanced.jsonl, SHA-256
93c0adb5590a37f6ad02e522011fa9817830ac8634fe6e19cd79892b1daa5533.
Of 1,745 rows, five had non-finite market measures and two were exact-state
duplicates. The 1,738 remaining eligible states contained only two tool labels.
Entry symbol/side and allowed abort reasons were checked. No conflicting tool
labels were found for exact duplicate states. These checks do not validate
the trading judgement or prove label-generation provenance.

All eligible compression states were labelled abort (480); all severe-dump
states were labelled abort (33). Trending states included 578 entry and 191
abort labels, while Sideways included nine entry and 829 abort labels. These
slices support reviewing label rules rather than treating every regime as
a sufficient decision rule. No label was changed based on Kev's predictions.

Coarse setup groups exclude symbol, round ADX/RSI to five-point bins, and use
funding-rate sign alongside the remaining state fields. A deterministic group
hash assigns dev/test; matching groups cannot cross splits. Within each split,
200 states are selected deterministically without balancing labels. Related
setups may still cross bin boundaries; grouping does not prove independence.
No explicit decision timestamps or realised outcomes are available.

The model receives only parsed market state and a fixed two-choice question.
Assistant answers, reasoning and expected labels are never included in requests.
Choice order is deterministically varied. This directly evaluates kev_evaluate;
it does not test kev_select_tool, argument generation, long/short accuracy,
position sizing, authorisation or live trading. No tools were dispatched.

## Reproduce

Run scripts/project23-benchmark.py with the source file and optional --url.
KEV_API_KEY in the environment authenticates if the server requires it.
The endpoint must report Kev 0.8B. Private cases, split manifest and raw results
are under benchmarks/private/project23/ and excluded from Git. Results include
server model metadata, source/dataset hashes and adapter source hash. The
remote server's resolved checkpoint revision is not independently verified.

Three added benchmark tests cover duplicate/invalid-state handling, input-target
separation, cross-symbol group assignment and conflicting labels. The full
adapter suite passed: 75 tests. Next useful work is to verify label-generation
rules and compare a fixed, development-only rule baseline before expanding
the sample or considering another model.
