"""LLM access via OpenRouter (OpenAI-compatible chat completions).

LLM_MODE=live  -> real calls with OPENROUTER_API_KEY
LLM_MODE=mock  -> deterministic in-process 'LLM' that follows the same
                  tool-calling protocol, so the whole pipeline (tool loop,
                  trace, structured output, UI) runs identically offline.
"""

import json
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


# Runtime override set through POST /api/llm/mode (the demo toggle). None means
# follow the environment. Deliberately in-process and non-persistent: a restart
# falls back to the configured default, and the safe default is mock.
_runtime_mode: str | None = None


def set_runtime_mode(mode: str | None) -> None:
    global _runtime_mode
    _runtime_mode = mode


def runtime_mode() -> str | None:
    return _runtime_mode


def llm_mode() -> str:
    if _runtime_mode == "mock":
        return "mock"
    if _runtime_mode == "live":
        return "live" if os.getenv("OPENROUTER_API_KEY") else "mock"
    if os.getenv("LLM_MODE", "").lower() == "mock":
        return "mock"
    return "live" if os.getenv("OPENROUTER_API_KEY") else "mock"


def llm_model() -> str:
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)


def chat(messages: list[dict], tools: list[dict]) -> dict:
    """One completion turn. Returns the assistant message dict
    (may contain tool_calls). Raises on transport/API errors."""
    resp = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "HTTP-Referer": "https://github.com/amarshikhar",
            "X-Title": "PM Triage Assistant",
        },
        json={
            "model": llm_model(),
            "messages": messages,
            "tools": tools,
            "temperature": 0.2,
            "max_tokens": 1600,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


class MockLLM:
    """Scripted policy that mirrors what the live agent does: inspect the
    machine, pull the telemetry trend, search history, then answer with the
    top-matching historical work order as the root-cause hypothesis."""

    def __init__(self, anomaly_ctx: dict):
        self.ctx = anomaly_ctx
        self.step = 0
        self.history_matches: list[dict] = []

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.step += 1
        mid = self.ctx["machine_id"]
        if self.step == 1:
            return _tool_call("get_machine_info", {"machine_id": mid})
        if self.step == 2:
            return _tool_call("get_recent_telemetry", {"machine_id": mid, "n": 20})
        if self.step == 3:
            keywords = f"{self.ctx['metric'].split('_')[0]} {self.ctx['severity']} rising trend"
            return _tool_call("search_maintenance_history", {
                "machine_type": self.ctx["machine_type"], "keywords": keywords, "machine_id": mid})

        # final answer: build it from the last tool result (history search)
        last = json.loads(messages[-1]["content"])
        matches = last.get("matches", [])
        # A scripted policy can still tell forensics from housekeeping: prefer
        # corrective records over routine ones (PM routes, inspections,
        # calibrations, false alarms). Keyword ranking alone would happily cite
        # a "false vibration alarm" for a real vibration ramp; the record type
        # is the CMMS field that says which is which.
        failures = [m for m in matches
                    if m.get("record_type", "corrective") == "corrective"]
        self.history_matches = failures or matches
        matches = self.history_matches
        if matches:
            top = matches[0]
            answer = {
                "root_cause": top["root_cause"],
                "confidence": 0.75 if top["machine_id"] == mid else 0.6,
                "explanation": (
                    f"The {self.ctx['metric'].replace('_', ' ')} trend on {mid} matches "
                    f"work order {top['work_order']} ({top['date']}): '{top['failure_mode']}' — "
                    f"symptoms then were: {top['symptoms']}. That incident was resolved by: "
                    f"{top['action_taken']}."
                ),
                "recommended_actions": [
                    f"Inspect for signs of: {top['failure_mode']}",
                    f"Reference remedy from {top['work_order']}: {top['action_taken']}",
                    "Confirm findings before any intervention; do not stop the machine without planner sign-off",
                ],
                "cited_work_orders": [m["work_order"] for m in matches[:3]],
                "priority_adjustment": 1 if top.get("safety_related") else 0,
                "adjustment_justification": (
                    "Closest historical match was safety-related" if top.get("safety_related")
                    else "No adjustment; formula priority stands"
                ),
            }
        else:
            answer = {
                "root_cause": "No matching failure pattern in maintenance history — novel anomaly",
                "confidence": 0.3,
                "explanation": (
                    f"The {self.ctx['metric']} excursion on {mid} does not resemble any recorded "
                    "work order for this machine type. Recommend a manual inspection to characterise it."
                ),
                "recommended_actions": ["Schedule manual inspection", "Increase monitoring frequency"],
                "cited_work_orders": [],
                "priority_adjustment": 0,
                "adjustment_justification": "Insufficient evidence for adjustment",
            }
        return {"role": "assistant", "content": json.dumps(answer)}


def _tool_call(name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": f"mock_{name}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }],
    }
