# Gutsy comparison deployment

Gutsy is an optional CPU backend that can run separately from a Kev service.
Its model API listens on port 8009 inside the Compose network, and its MCP
endpoint is exposed on port 8766 by default. The original Kev MCP uses port
8765. No cryptocurrency exchange connection or order execution is added.

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
run `scripts/download-gutsy.ps1`. For remote MCP clients, configure a private
`.env` with `KEV_MCP_BIND_HOST=0.0.0.0`, a bearer token, and an exact
`GUTSY_MCP_ALLOWED_HOSTS` entry for the host and port clients use.
`GUTSY_MCP_PORT` defaults to 8766.
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
No calibration on the target trading task has been established.

## Verification and evaluation

The automated test suite covers adapter behavior. Validate HTTP MCP discovery,
missing/stale context handling, and a synthetic advisory fixture against the
running container before changing client configuration. Synthetic fixtures
are smoke checks, not trading benchmarks.

The adapter preserves Gutsy's explicit insufficient-information option and
separate rejection output. Read both conditional and unconditional probability
fields; the most likely conditional choice may differ from the final advisory
suggestion. Smoke tests do not establish broad abstention accuracy.

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
