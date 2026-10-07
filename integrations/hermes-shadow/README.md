# Hermes comparison trial

Install this folder as `~/.hermes/plugins/kev-shadow-trial` and copy
`src/kev_mcp_server/server.py` to `adapter.py` inside it. The Hermes Python
environment needs the adapter dependencies. Enable its registration with
`hermes plugins enable --no-allow-tool-override kev-shadow-trial`. No hooks register unless
`KEV_SHADOW_TRIAL=1`. No running agent needs restarting.

Launch one new process with `KEV_SHADOW_TRIAL=1 KEV_SHADOW_URL=http://127.0.0.1:8008 hermes`. Set `KEV_SHADOW_URL` to the Kev API address when it runs on another machine.
Optional `KEV_SHADOW_API_KEY` authenticates the comparison requests only.
The default remote endpoint serves Kev **0.8B**, unlike the earlier 4B benchmark.
Each record includes endpoint model metadata; do not combine these results.

The plugin retains actual request tool schemas and at most eight recent
user/assistant text messages, each capped at 4,000 characters, in memory.
After Hermes executes its first tool for that API request, a bounded background
queue calls the same `kev_select_tool` helper. It never changes the agent's
request, result, arguments, permissions, or selected tool. Requests go to the
configured Kev endpoint; logs omit message text, arguments, and tool results.

Private output: `~/.hermes/kev-shadow/comparisons.jsonl`, mode 0600.
Content-free counters in `~/.hermes/kev-shadow/status.json` report observed
hooks, queued/completed comparisons and the latest skip reason. Hermes may
replace oversized sanitized request payloads with a preview; these are skipped
because they do not provide a complete tool roster. Counters reset per process.
Only one process can hold the recording lock. Queue overflow drops samples;
daemon shutdown may also lose pending samples. Unsupported request formats,
missing schemas, direct answers, and subsequent parallel tools are not sampled.
This measures agreement on bounded context, not correctness or full coverage.
The three-second HTTP timeout applies in the worker, not the agent hook.

Disable by launching Hermes without `KEV_SHADOW_TRIAL=1`. Remove the plugin
folder to uninstall. No gateway or global model configuration is changed.
