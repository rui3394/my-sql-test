import os
import sys
import json

import sqlglot
import sqlglot.expressions as exp

from layer2_ast.parser import MasterLineageVisitor
from layer3_risk.risk_state import RiskStateEngine
from layer3_risk.risk_engine import RiskPropagationEngine
from layer4_memory.layer4_context import global_session_manager
from layer5_llm.layer5_llm import StructuredLLMArbitrator
from layer5_llm.deterministic_matrix import arbitrate_by_matrix


def _safe_text(msg: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return str(msg).encode(encoding, errors="replace").decode(encoding, errors="replace")


def _extract_insert_mapping(ast_root):
    target_table = None
    name_mapping = {}
    warnings = []

    if not isinstance(ast_root, exp.Insert):
        return target_table, name_mapping, warnings

    table_node = ast_root.find(exp.Table)
    if table_node:
        target_table = table_node.name

    if not isinstance(ast_root.this, exp.Schema):
        warnings.append("INSERT has no explicit target schema; skip persistence column mapping.")
        return target_table, name_mapping, warnings

    insert_cols = [col.name for col in ast_root.this.expressions]
    source_exprs = []

    if isinstance(ast_root.expression, exp.Select):
        source_exprs = list(ast_root.expression.expressions or [])
    elif isinstance(ast_root.expression, exp.Values) and ast_root.expression.expressions:
        first_row = ast_root.expression.expressions[0]
        source_exprs = list(getattr(first_row, "expressions", []) or [])
    else:
        warnings.append("INSERT source is not SELECT/VALUES; persistence mapping may be incomplete.")
        return target_table, name_mapping, warnings

    source_names = []
    for i, item in enumerate(source_exprs):
        alias_name = getattr(item, "alias_or_name", None)
        source_names.append(alias_name if alias_name else f"expr_{i + 1}")

    if len(insert_cols) != len(source_names):
        warnings.append(
            f"INSERT mapping length mismatch: target_cols={len(insert_cols)}, source_cols={len(source_names)}. "
            "Only aligned prefix will be mapped."
        )

    name_mapping = dict(zip(source_names, insert_cols))
    return target_table, name_mapping, warnings


def process_query(sql: str, session_id: str, query_name: str):
    print("\n" + "=" * 60)
    print(f"[Query] {query_name}")
    print(f"[SQL] {sql.strip()}")
    print("=" * 60)

    ast_root = sqlglot.parse_one(sql)
    target_table, name_mapping, mapping_warnings = _extract_insert_mapping(ast_root)

    if isinstance(ast_root, exp.Insert):
        print(f"[*] INSERT detected -> table={target_table}, column_mapping={name_mapping}")
        for item in mapping_warnings:
            print(f"[!] INSERT mapping warning: {item}")

    visitor = MasterLineageVisitor()
    lineage_graph = visitor.parse(sql)
    nx_graph = lineage_graph.to_networkx()

    state_engine = RiskStateEngine(nx_graph)
    state_space = state_engine.initialize_state_space(session_id=session_id)

    prop_engine = RiskPropagationEngine(nx_graph, state_space)
    final_state_space = prop_engine.propagate()

    if target_table:
        for node_id, state in final_state_space.items():
            node_name = nx_graph.nodes[node_id]["name"]
            node_type = nx_graph.nodes[node_id]["type"]
            if node_type == "COLUMN" and node_name in name_mapping and state.r_current > 0:
                inserted_col_name = name_mapping[node_name]
                global_session_manager.save_taint_state(session_id, target_table, inserted_col_name, state.r_current)

    print(f"\n[Risk Summary] {query_name}")
    llm_payload = []

    for node_id, state in final_state_space.items():
        if state.r_current <= 0:
            continue

        node_name = nx_graph.nodes[node_id]["name"]
        node_type = nx_graph.nodes[node_id]["type"]
        formal = getattr(state, "formal_state", None)
        node_meta = nx_graph.nodes[node_id]["obj"].metadata

        print(f"  - [{node_name}] score={state.r_current:.2f}")
        for trace in state.taint_trace:
            print(f"      {_safe_text(trace)}")

        llm_payload.append(
            {
                "node_id": node_id,
                "node_name": node_name,
                "node_type": node_type,
                "final_risk_score": state.r_current,
                "taint_propagation_trace": state.taint_trace,
                "formal_src_sens": formal.src_sens.name if formal else None,
                "formal_r_level": formal.r_level.name if formal else None,
                "formal_o_level": formal.o_level.name if formal else None,
                "formal_e_level": formal.e_level.name if formal else None,
                "is_projection_output": node_meta.get("is_projection_output", False),
            }
        )

    if not llm_payload:
        print("  [OK] No risky node found in this query graph.")
        return

    print("\n" + "-" * 50)
    matrix_result = arbitrate_by_matrix(llm_payload)
    print("[Deterministic Matrix Result]")
    print(json.dumps(matrix_result, indent=2, ensure_ascii=False))

    if os.environ.get("ENABLE_LLM_ARBITRATION", "0") == "1":
        print("\n[LLM Arbitration] enabled")
        arbitrator = StructuredLLMArbitrator()
        llm_result = arbitrator.arbitrate(sql, llm_payload)
        print(json.dumps(llm_result.model_dump(), indent=2, ensure_ascii=False))
    else:
        print("\n[Info] ENABLE_LLM_ARBITRATION != 1, skipped LLM arbitration.")


if __name__ == "__main__":
    current_session = "SESSION_USER_9999"

    test_cases = [
        {
            "name": "TestCase 1: direct sensitive projection",
            "sql": "SELECT u.password FROM users u WHERE u.id = 1",
            "expected": "Critical / DataExfiltration",
        },
        {
            "name": "TestCase 2: business declassification",
            "sql": "SELECT MD5(SUBSTR(u.password, 1, 4)) AS safe_token FROM users u",
            "expected": "Safe or Low / SafeOperation",
        },
        {
            "name": "TestCase 3: aggregation",
            "sql": "SELECT COUNT(u.password) AS pw_filled_count FROM users u",
            "expected": "Safe or Low / SafeOperation",
        },
        {
            "name": "TestCase 4: boolean blind inference",
            "sql": "SELECT u.username FROM users u WHERE SUBSTR(u.password, 1, 1) = 'a'",
            "expected": "High / BooleanBlind",
        },
        {
            "name": "TestCase 5.1: second-order write",
            "sql": "INSERT INTO temp_audit_logs (log_time, user_pwd) SELECT '2026-03-30', u.password FROM users u",
            "expected": "Medium/High / DataExfiltration",
        },
        {
            "name": "TestCase 5.2: second-order read",
            "sql": "SELECT user_pwd FROM temp_audit_logs",
            "expected": "Critical / DataExfiltration",
        },
    ]

    for case in test_cases:
        process_query(case["sql"], current_session, case["name"])
