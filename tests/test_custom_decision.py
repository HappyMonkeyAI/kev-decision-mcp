import pytest

from kev_mcp_server import server


ABSTAIN = "__insufficient_information__"
OPTIONS = {"approve": "Approve under the supplied policy", "decline": "Decline the request"}


def answer(choice="approve", probabilities=None, reject=None):
    probabilities = probabilities or {"approve": 0.8, "decline": 0.1, ABSTAIN: 0.1}
    result = {"type": "choice", "choice": choice, "probabilities": probabilities}
    if reject is not None:
        result["reject"] = reject
    return {"model": "fixture", "latency_ms": 12,
            "answers": {"decision": result}, "usage": {"output_tokens": 1}}


def test_custom_decision_builds_dynamic_schema_and_returns_advisory(monkeypatch):
    seen = {}

    def evaluate(state, questions):
        seen["state"] = state
        seen["questions"] = questions
        return answer()

    monkeypatch.setattr(server, "kev_evaluate", evaluate)
    state = {"request": "please assess", "policy": {"eligible": True}}
    result = server.kev_custom_decision("Choose an outcome", state, OPTIONS)

    question = seen["questions"]["decision"]
    assert seen["state"] == state
    assert question["type"] == "choice"
    assert question["criteria"] == {**OPTIONS, ABSTAIN: question["criteria"][ABSTAIN]}
    assert "Choose an outcome" in question["instructions"]
    assert result["selected_option"] == "approve"
    assert result["conditional_model_choice"] == "approve"
    assert result["abstained"] is False
    assert result["executed"] is False
    assert result["execution_authorized"] is False
    assert result["probabilities_calibrated"] is False
    assert len(result["input_sha256"]) == 64


def test_custom_decision_abstains_on_reserved_option(monkeypatch):
    probabilities = {"approve": 0.1, "decline": 0.1, ABSTAIN: 0.8}
    monkeypatch.setattr(server, "kev_evaluate", lambda *args: answer(ABSTAIN, probabilities))

    result = server.kev_custom_decision("Choose an outcome", {}, OPTIONS)

    assert result["selected_option"] is None
    assert result["conditional_model_choice"] == ABSTAIN
    assert result["abstained"] is True


def test_custom_decision_abstains_when_gutsy_rejection_dominates(monkeypatch):
    monkeypatch.setenv("KEV_BACKEND", "gutsy")
    monkeypatch.setattr(server, "kev_evaluate", lambda *args: answer(reject=0.9))

    result = server.kev_custom_decision("Choose an outcome", {}, OPTIONS)

    assert result["selected_option"] is None
    assert result["conditional_model_choice"] == "approve"
    assert result["abstained"] is True
    assert result["rejection_probability"] == 0.9
    assert result["rejection_dominates"] is True


@pytest.mark.parametrize("task,options,message", [
    (" ", OPTIONS, "task"),
    ("x" * 1001, OPTIONS, "task"),
    ("Choose", {"only": "One"}, "between 2 and 8"),
    ("Choose", {"a": "A", "b": "B", ABSTAIN: "Reserved"}, "reserved"),
    ("Choose", {"a": "A", "b": " "}, "meaning"),
])
def test_custom_decision_rejects_invalid_schema(task, options, message):
    with pytest.raises(ValueError, match=message):
        server.kev_custom_decision(task, {}, options)


def test_custom_decision_rejects_non_json_or_oversized_state():
    with pytest.raises(ValueError, match="finite JSON"):
        server.kev_custom_decision("Choose", {"value": float("nan")}, OPTIONS)
    with pytest.raises(ValueError, match="65536"):
        server.kev_custom_decision("Choose", "x" * 65536, OPTIONS)


@pytest.mark.parametrize("bad_answer", [
    {},
    {"type": "choice", "choice": "unknown", "probabilities": {"unknown": 1}},
    {"type": "choice", "choice": "approve", "probabilities": {"approve": 1}},
    {"type": "choice", "choice": "approve", "probabilities": {
        "approve": 0.4, "decline": 0.4, ABSTAIN: 0.1}},
])
def test_custom_decision_rejects_invalid_upstream_answers(monkeypatch, bad_answer):
    monkeypatch.setattr(server, "kev_evaluate", lambda *args: {"answers": {"decision": bad_answer}})
    with pytest.raises(RuntimeError):
        server.kev_custom_decision("Choose an outcome", {}, OPTIONS)
