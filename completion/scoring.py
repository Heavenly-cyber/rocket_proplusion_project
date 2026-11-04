"""Strict structured-answer and dimensional scoring. No LLM judges."""
import json
import math
from .physics import reference

FIELDS = {"decision", "value", "unit", "issue", "evidence_ids", "assumptions", "explanation"}
ISSUES = {"none", "missing_inputs", "internal_shock", "variable_gamma", "unchoked"}


def reject_constant(value):
    raise ValueError("Nonstandard JSON constant: " + value)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON key")
        result[name] = value
    return result


def decode(text):
    try:
        data = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != FIELDS:
            return None
        if data["decision"] not in {"answer", "abstain"} or data["issue"] not in ISSUES:
            return None
        if not all(isinstance(data[x], list) and all(isinstance(v, str) for v in data[x])
                   for x in ("evidence_ids", "assumptions")):
            return None
        if not isinstance(data["explanation"], str):
            return None
        if data["decision"] == "answer":
            value = data["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return None
            if not isinstance(data["unit"], str) or not data["unit"].strip():
                return None
        elif data["value"] is not None or data["unit"] is not None:
            return None
        return data
    except (ValueError, TypeError, OverflowError):
        return None


def evaluate(case, text, passages):
    # This function is called only after the raw model response has been saved.
    gold, target_unit = reference(case)
    data = decode(text)
    result = dict(schema_valid=data is not None, correct=False, decision_correct=False,
                  issue_correct=False, numeric_correct=None, unit_correct=None,
                  raw_number_correct=None, converted_value=None, relative_error=None,
                  reference_value=gold, reference_unit=target_unit,
                  expected_decision=case["reference"]["decision"],
                  expected_issue=case["reference"]["issue"], failure="schema",
                  cited_ids=[], citation_id_precision=None,
                  retrieved_reference_recall=None, assumptions_present=False)
    available = {p["id"] for p in passages}
    relevant = set(case["reference"]["relevant_ids"])
    if passages:
        result["retrieved_reference_recall"] = len(available & relevant)/len(relevant)
    if data is None:
        return result
    result["parsed_answer"] = data
    result["cited_ids"] = data["evidence_ids"]
    result["assumptions_present"] = bool(data["assumptions"])
    if passages:
        cited = set(data["evidence_ids"])
        result["citation_id_precision"] = len(cited & available)/len(cited) if cited else 0.0
    result["decision_correct"] = data["decision"] == case["reference"]["decision"]
    result["issue_correct"] = data["issue"] == case["reference"]["issue"]
    if not result["decision_correct"]:
        result["failure"] = "decision"
        return result
    if gold is None:
        result["correct"] = result["issue_correct"]
        result["failure"] = "none" if result["correct"] else "issue"
        return result
    tolerance = max(case["reference"]["atol"], .01*abs(gold))
    result["raw_number_correct"] = abs(data["value"]-gold) <= tolerance
    import pint
    try:
        units = pint.UnitRegistry()
        quantity = units.Quantity(data["value"], data["unit"]).to(target_unit)
        value = float(quantity.magnitude)
        if not math.isfinite(value):
            raise ValueError("Nonfinite converted quantity")
        result["unit_correct"] = True
        result["converted_value"] = value
        result["relative_error"] = abs(value-gold)/abs(gold) if gold else None
        result["numeric_correct"] = abs(value-gold) <= tolerance
    except Exception:
        # Unit strings are untrusted model output. A parser or dimensional error
        # is a scored unit failure, never a reason to discard a model answer.
        result["unit_correct"] = False
        result["numeric_correct"] = False
    result["correct"] = bool(result["issue_correct"] and result["unit_correct"] and result["numeric_correct"])
    result["failure"] = ("none" if result["correct"] else "issue" if not result["issue_correct"]
                         else "unit" if not result["unit_correct"] else "numeric")
    return result
