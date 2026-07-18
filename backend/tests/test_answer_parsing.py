"""Parsing of the agent's final answer.

Live models wrap the answer object in prose and/or a markdown fence despite the
system prompt asking for bare JSON. Discarding those replies loses a fully
correct triage, so the parser has to see through the packaging.
"""

import json

from app.agent.triage import _extract_json

ANSWER = {
    "root_cause": "Bearing lubrication issue",
    "confidence": 0.72,
    "explanation": "Vibration climbed from 2.6 to 6.0 mm/s.",
    "recommended_actions": ["Check the auto-lubrication system"],
    "cited_work_orders": ["WO-1009", "WO-1007"],
    "priority_adjustment": 0,
    "adjustment_justification": "Formula priority stands",
}


def test_bare_object():
    assert _extract_json(json.dumps(ANSWER)) == ANSWER


def test_fenced_object():
    assert _extract_json(f"```json\n{json.dumps(ANSWER)}\n```") == ANSWER


def test_fence_without_language_tag():
    assert _extract_json(f"```\n{json.dumps(ANSWER)}\n```") == ANSWER


def test_prose_preamble_before_fenced_object():
    """The exact shape that produced 'Agent returned unstructured output' in
    production: Sonnet 4.5 prefixed the fence with a sentence of prose."""
    reply = f"Based on my investigation, here is my analysis:\n\n```json\n{json.dumps(ANSWER)}\n```"
    assert _extract_json(reply) == ANSWER


def test_prose_preamble_without_fence():
    reply = f"Here is my analysis:\n\n{json.dumps(ANSWER)}"
    assert _extract_json(reply) == ANSWER


def test_trailing_prose_after_object():
    reply = f"{json.dumps(ANSWER)}\n\nLet me know if you need more detail."
    assert _extract_json(reply) == ANSWER


def test_explanation_containing_braces_and_backticks():
    payload = dict(ANSWER, explanation="Pressure {stable} at 400 kPa; see `WO-1007`.")
    reply = f"Analysis:\n```json\n{json.dumps(payload)}\n```"
    assert _extract_json(reply) == payload


def test_genuinely_unstructured_reply_returns_none():
    assert _extract_json("I could not determine a root cause.") is None


def test_empty_and_non_object_replies_return_none():
    assert _extract_json("") is None
    assert _extract_json(None) is None
    assert _extract_json("[1, 2, 3]") is None
