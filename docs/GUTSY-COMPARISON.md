# Gutsy comparison deployment

Gutsy is a separate CPU backend, not a replacement for the running Kev 4B
service. Its model API is localhost:8009, and its MCP comparison endpoint is
http://192.168.5.157:8766/mcp. The original Kev MCP remains on port 8765.
Both MCP adapters follow the user's existing blank-token LAN configuration.
No cryptocurrency exchange connection or order execution is added.

## Pinned installation

Runtime 0.4.0, Q8_0 GGUF and calibration file come from kouhxp/gutsy on Hugging
Face at revision bb1dde4c571b2588801c27d155da005a87d05285. GitHub main at
dde8b927165295bdbd65ce3519d5d7fea8dfce1a reports runtime 0.3.0, so that older
runtime was not installed. scripts/download-gutsy.ps1 downloads the fixed
release and saves SHA-256 hashes under .cache/gutsy/provenance.json.
The source and large model files are excluded from Git. Runtime/model licensing
is upstream Apache 2.0. The downloaded runtime README accompanies its source.

## Standalone deployment on another host

On Linux (Python 3.11+), run `python3 scripts/download-gutsy.py`. On Windows,
the existing PowerShell downloader also works. In a private .env, set
KEV_MCP_BIND_HOST=0.0.0.0, KEV_MCP_AUTH_TOKEN=, and
GUTSY_MCP_ALLOWED_HOSTS=192.168.5.232:8766,localhost:8766,127.0.0.1:8766,localhost:8765,127.0.0.1:8765
for the .232 deployment. GUTSY_MCP_PORT defaults to 8766.
Use `docker compose -p gutsy-advisory -f compose.gutsy.yaml up -d --build`.
This standalone file requires neither a Kev image nor CUDA/cache volumes.
It starts only Gutsy and its adapter under a separate project name.
Validate the service before changing any client configuration; retain the
previous service/configuration for rollback. Never disable Host validation
with a wildcard merely to accommodate another LAN address.

The CPU container uses llama-cpp-python 0.3.36, numpy 2.4.2, four CPU threads,
no GPU layers and a 4 GiB memory limit. A cache self-check passed. Observed
Docker resident memory during evaluation was approximately 460 MiB; this is
a point-in-time sample, not peak memory or the complete model file size.

```powershell
./scripts/download-gutsy.ps1
docker compose -f compose.yaml -f compose.gutsy.yaml up -d --build gutsy gutsy-mcp
```

To stop just the comparison services:

```powershell
docker compose -f compose.yaml -f compose.gutsy.yaml stop gutsy-mcp gutsy
```

Do not use --remove-orphans: the existing Kev model service must remain.
Both files share the kev-advisory project/network with the original deployment.
Starting only gutsy/gutsy-mcp avoids recreating the original adapter.

## Response semantics

KEV_BACKEND=gutsy and KEV_API_MODEL=gutsy-0.8b-v04 configure the comparison
adapter. Gutsy score.expected is also exposed as score; usage.latency_ms is
also exposed at the top level. Raw model-list metadata retains Gutsy's data/id
format. Kev-specific separate and permute diagnostics are explicitly unsupported.

The model's option probabilities are conditioned on not rejecting. The adapter
retains them and separately returns rejection_probability, probability_semantics,
unconditional_option_probabilities, conditional_model_choice and rejection_dominates.
Each unconditional option mass is (1-reject) times its conditional probability.
When reject exceeds every unconditional option, trade review returns
insufficient_information, and tool selection returns no suggested tool. This
is a largest-mass comparison, not a trading confidence threshold. The returned
top_probability still describes the conditional model choice, which can differ
from the final advisory suggestion; inspect the rejection fields alongside it.
No calibration on the user's trading task has been established.

## Verification and evaluation

The adapter test suite passed 95 tests. Actual HTTP MCP discovery and
missing/stale context checks passed against the Gutsy container. A fresh
synthetic advisory fixture returned insufficient_information, with conditional
probability 0.494729, rejection 0.000102 and model latency about 1.82 seconds.
This installation fixture is not a trading benchmark.

Both backends selected insufficient_information for three additional synthetic
fixtures explicitly missing spread, account exposure or transaction costs.
Gutsy's reject probabilities were approximately 0.00009: these abstentions used
the explicit insufficient-information option, not its separate reject slot.
In another synthetic two-option case where neither action was permitted,
Gutsy's reject was 0.836964 despite a conditional option probability of 0.674922.
That demonstrates why reading the conditional choice alone would be misleading.
These are smoke checks, not broad abstention accuracy estimates.

scripts/compare-gutsy.py evaluates the same fixed Project23 dataset and prompts
against local Kev 4B and CPU Gutsy, alternating call order. It verifies the
dataset hash, excludes labels from input, warms each model once and separately
reports conditional agreement, rejection counts, accepted coverage/agreement,
median/p95 end-to-end latency and confusion. Private results are saved in
benchmarks/private/project23/gutsy-comparison.json. No threshold is fitted.
Rejected cases have no correct-rejection labels, so abstention quality is not
independently validated. CPU/GPU timings are not hardware-normalized.
The previous remote 0.8B Kev result is not used as the paired comparator.

Sources: https://huggingface.co/kouhxp/gutsy and https://github.com/kouhxp/gutsy.
Benchmark generation and limitations: benchmarks/PROJECT23-RESULTS.md.
