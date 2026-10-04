# Experimental trade review contract

`kev_review_trade` is available through this repository's MCP server. It uses
the configured KEV_API_BASE_URL and KEV_API_KEY. No exchange connection, order
dispatch, price fetching, argument generation or automatic local logging is added.
Restart an MCP server process to discover the added tool. ChatGPT connection
setup is a separate step; this change does not establish that connection.

## Input

The caller supplies three objects:

* market_context: symbol, source, timezone-aware observed_at, and nonempty
  features. Include provenance/observation times for individual features when
  they differ; the adapter only checks the snapshot timestamp.
* proposed_trade: the same symbol, side (long/short), rationale, and positive
  horizon_seconds. Include the agent's proposal before consulting Kev, exposure,
  proposed size and costs where relevant. No sizing defaults are invented.
* risk_constraints: positive max_market_age_seconds and a nonempty list of
  explicit user-defined rules. Include required facts, exposure/limits and
  assumptions needed to assess those rules. This is not a risk calculator.

All inputs must be finite JSON values. Invalid symbols, side or timestamp
formats raise errors. Missing required facts, stale snapshots and future
timestamps return insufficient_information without model inference. The caller
chooses its data-age limit; none is presented as a validated trading threshold.
Source identity and supplied facts are assertions, not independently verified.

## Output

Suggestions: supports_proposal, concerns, insufficient_information. Every result
reports paper_advisory mode, executed=false, execution_authorized=false,
probabilities_calibrated=false and inputs_independently_verified=false.
Input checks have origin=input_check, a reason and null probabilities/model.
Model responses have origin=model, model name, choice probabilities and API
latency/usage. All outputs include UTC evaluation time and an input SHA-256;
the hash links a paper record to its input but does not prove its correctness.

The adapter validates response labels, distribution and maximum-probability
choice. A malformed response or upstream outage is an error, never approval.
No generated explanation or fabricated evidence is returned. The model may
still select support despite missing information beyond the structural checks.
Its probabilities are not estimates of profit, safety or strategy success.

## Paper-trial procedure

Record the agent's proposal and intended action before the advisory call.
Then record the exact inputs, advisory output and final paper decision separately.
Use a caller-assigned decision ID. Subsequent outcomes need observation times,
an evaluation horizon fixed before outcomes, fill assumptions and explicit
fees/slippage. Keep outcome fields out of later decision inputs. Comparisons
must include declined proposals, failures and insufficient-information results.
The tool does not fetch or calculate outcomes or run this trial automatically.

Project23's prior 68.5% two-choice label agreement does not validate this
three-choice prompt, proposals, constraints, timestamps, long/short accuracy or
paper returns. Its untimestamped market states cannot supply a historical
performance trial. No profitable-trading claim is supported.

## Label-review queue

Run scripts/prepare-project23-review.py after the existing benchmark builder.
It prepares 20 development-only records varied by action, regime and macro
pulse under benchmarks/private/project23/label-review.jsonl. All are pending.
The held-out test split is excluded. Do not relabel against Kev predictions.
Review each target against documented generator/project rules; use unknown
when evidence is insufficient. Original generator rules were not found in the
inspected training scripts, so labels have not been independently approved.
Original training answers remain excluded from advisory inputs. Source data,
review annotations and raw benchmark results stay private and Git-ignored.

Implementation verification: mocked API and input/error tests, plus MCP tool
discovery. These do not establish the model's correctness or live ChatGPT access.
