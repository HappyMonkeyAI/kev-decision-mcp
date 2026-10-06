# Per-call custom decisions

`kev_custom_decision(task, state, options)` provides a bounded, agent-defined
classification when none of the focused tools fits. The agent supplies the task,
case facts and 2–8 option IDs with concise meanings on every call. The MCP server
does not add tools or retain the supplied schema between calls.

```json
{
  "task": "Choose the next support-queue action for this ticket",
  "state": {
    "ticket_text": "The replacement arrived damaged",
    "order_status": "delivered",
    "photo_attached": true
  },
  "options": {
    "request_evidence": "Ask for clearer photos or other missing evidence",
    "offer_replacement": "Recommend a replacement under the stated policy",
    "escalate": "Refer the case to a human for policy review"
  }
}
```

The server adds `__insufficient_information__`, bounds task and option lengths,
limits combined state and schema JSON to 64 KiB, and validates that the response
contains exactly the declared choices and a finite probability distribution.
The response has `mode: "custom_advisory"`, `selected_option` (null on abstention),
`conditional_model_choice`, `abstained`, probabilities, model metadata and an
input hash. Gutsy's separate rejection signal is retained; if it dominates its
option distribution, the result abstains.

The model does not produce a rationale or take the selected action. Probabilities
are uncalibrated and schema-specific reliability has not been established. The
caller must keep its own permission, policy, verification and execution checks.
Task and option text define the classification request, so callers should use
trusted, concise descriptions rather than passing user-authored schema text
directly. Treat the returned label as an advisory signal, not an approval.

Use focused tools such as the trade review for known workflows: they encode
domain-specific input checks and output meaning that a per-call schema cannot
provide automatically. `kev_custom_decision` complements those tools for new or
less standardized tasks. `kev_evaluate` remains available for callers that need
Kev's underlying multi-question API format directly.
