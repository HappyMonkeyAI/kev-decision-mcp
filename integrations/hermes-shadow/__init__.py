"""Opt-in, observation-only Hermes hooks. No middleware or tool dispatch."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import threading
from collections import OrderedDict


def register(ctx):
    if os.environ.get("KEV_SHADOW_TRIAL") != "1":
        return
    import fcntl
    import httpx
    root = Path(os.environ.get("KEV_SHADOW_LOG_DIR", str(Path.home() / ".hermes/kev-shadow")))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (root / "trial.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    owner = os.getpid()
    snapshots = OrderedDict()
    mutex = threading.Lock()
    jobs = queue.Queue(maxsize=32)
    diagnostics = {"pid": owner, "pre_requests": 0, "post_tools": 0,
                   "snapshots": 0, "queued": 0, "completed": 0, "last_skip": None}
    endpoint = os.environ.get("KEV_SHADOW_URL", "http://127.0.0.1:8008").rstrip("/")

    def worker():
        retained_lock = lock  # Keep ownership after Hermes discards register(ctx).
        spec = importlib.util.spec_from_file_location("kev_shadow_adapter", Path(__file__).with_name("adapter.py"))
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            def request(method, path, *, payload=None):
                key = os.environ.get("KEV_SHADOW_API_KEY", "")
                response = client.request(method, endpoint + path, json=payload,
                    headers={"Authorization": "Bearer " + key} if key else {})
                response.raise_for_status()
                return response.json()
            adapter._request = request
            try:
                models = request("GET", "/v1/models")
            except Exception:
                models = None
            while True:
                fd = os.open(root / "status.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as output:
                    output.write(json.dumps(diagnostics))
                try:
                    state, tools, record = jobs.get(timeout=1.0)
                except queue.Empty:
                    continue
                try:
                    result = adapter.kev_select_tool(state, tools)
                    record.update(result)
                    record["agrees"] = result["suggested_tool"] == record["hermes_tool"]
                except Exception as exc:
                    record["error_type"] = type(exc).__name__
                record["endpoint_models"] = models
                record["endpoint"] = endpoint
                record["state_sha256"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
                fd = os.open(root / "comparisons.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a") as output:
                    output.write(json.dumps(record) + "\n")
                jobs.task_done()
                diagnostics["completed"] += 1

    def before(**event):
        if os.getpid() != owner:
            return
        diagnostics["pre_requests"] += 1
        body = (event.get("request") or {}).get("body") or {}
        if (event.get("request") or {}).get("_truncated"):
            diagnostics["last_skip"] = "Hermes sanitized request exceeded payload limit"
            return
        tools = {}
        for item in body.get("tools") or []:
            function = item.get("function", {}) if isinstance(item, dict) else {}
            if function.get("name") and function.get("description"):
                tools[function["name"]] = {key: function[key] for key in ("description", "parameters") if key in function}
        # Never persist or send system prompts, tool arguments, or tool results.
        messages = [{"role": item["role"], "content": item["content"][:4000]}
                    for item in body.get("messages", []) if isinstance(item, dict)
                    and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str)]
        if not tools or not messages or len(tools) > 254:
            diagnostics["last_skip"] = "missing tools/text or unsupported roster size"
            return
        diagnostics["snapshots"] += 1
        with mutex:
            snapshots[event.get("api_request_id")] = ({"messages": messages[-8:]}, tools)
            while len(snapshots) > 64:
                snapshots.popitem(last=False)

    def after(**event):
        if os.getpid() != owner:
            return
        diagnostics["post_tools"] += 1
        with mutex:
            snapshot = snapshots.pop(event.get("api_request_id"), None)
        if snapshot is None:
            diagnostics["last_skip"] = "no matching API request snapshot"
            return
        record = {"api_request_id": event.get("api_request_id"), "hermes_tool": event.get("tool_name"),
                  "sample_kind": "synthetic_smoke" if event.get("api_request_id") == "installation-smoke" else "agent_observation",
                  "hermes_status": event.get("status"), "tool_count": len(snapshot[1]),
                  "context": "bounded user/assistant text; excludes system and tool messages",
                  "comparison": "first executed tool per API request; Hermes choice is not a gold label"}
        try:
            jobs.put_nowait((*snapshot, record))
            diagnostics["queued"] += 1
        except queue.Full:
            diagnostics["last_skip"] = "comparison queue full"
            pass

    # Retain the lock for this process; no other opted-in process can record.
    ctx._kev_shadow_lock = lock
    threading.Thread(target=worker, name="kev-shadow", daemon=True).start()
    ctx.register_hook("pre_api_request", before)
    ctx.register_hook("post_tool_call", after)
