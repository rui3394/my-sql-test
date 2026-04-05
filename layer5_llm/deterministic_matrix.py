from typing import Any, Dict, List


def _safe_level(value: str) -> int:
    order = {"Safe": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    return order.get(value, 0)


def _upgrade_level(current: str, target: str) -> str:
    return target if _safe_level(target) > _safe_level(current) else current


def _top_evidence(payload: List[Dict[str, Any]], top_k: int = 3) -> List[str]:
    ranked = sorted(payload, key=lambda x: float(x.get("final_risk_score", 0.0)), reverse=True)
    return [item.get("node_name", item.get("node_id", "unknown")) for item in ranked[:top_k]]


def arbitrate_by_matrix(risk_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not risk_payload:
        return {
            "threat_level": "Safe",
            "threat_type": "SafeOperation",
            "confidence_score": 1.0,
            "key_evidence_nodes": [],
            "reasoning_chain": ["No risky node found in graph."],
        }

    relevant = [n for n in risk_payload if n.get("node_type") == "COLUMN" and n.get("is_projection_output")]
    if not relevant:
        relevant = risk_payload

    all_r = [n.get("formal_r_level", "NONE") for n in relevant]
    all_o = [n.get("formal_o_level", "INTERNAL") for n in relevant]
    all_src = [n.get("formal_src_sens", "PUBLIC") for n in relevant]
    second_order = any("二阶溯源" in " ".join(n.get("taint_propagation_trace", [])) for n in relevant)

    result = {
        "threat_level": "Low",
        "threat_type": "SafeOperation",
        "confidence_score": 0.80,
        "key_evidence_nodes": _top_evidence(relevant),
        "reasoning_chain": [],
    }

    if all(level in ("LOW", "NONE") for level in all_r):
        result["threat_level"] = "Safe"
        result["threat_type"] = "SafeOperation"
        result["confidence_score"] = 0.95
        result["reasoning_chain"].append("All projection nodes are LOW/NONE on confidentiality retention.")
    elif "INFERRED" in all_o:
        result["threat_level"] = "High" if any(s in ("HIGH", "SECRET") for s in all_src) else "Medium"
        result["threat_type"] = "BooleanBlind"
        result["confidence_score"] = 0.90
        result["reasoning_chain"].append("Observed INFERRED observability on projection path (control-flow leakage).")
    elif "EXPOSED" in all_o and any(r in ("FULL", "PARTIAL", "HIGH") for r in all_r):
        if any(s == "SECRET" for s in all_src) and any(r == "FULL" for r in all_r):
            result["threat_level"] = "Critical"
        else:
            result["threat_level"] = "High"
        result["threat_type"] = "DataExfiltration"
        result["confidence_score"] = 0.92
        result["reasoning_chain"].append("Detected EXPOSED observability with retained sensitive content.")
    else:
        result["threat_level"] = "Medium"
        result["threat_type"] = "Unknown"
        result["confidence_score"] = 0.60
        result["reasoning_chain"].append("Rules did not hit strict safe/exfiltration/blind templates.")

    if second_order:
        result["threat_level"] = _upgrade_level(result["threat_level"], "High")
        if result["threat_type"] == "SafeOperation":
            result["threat_type"] = "DataExfiltration"
        result["reasoning_chain"].append("Second-order taint evidence detected from session memory.")

    return result
