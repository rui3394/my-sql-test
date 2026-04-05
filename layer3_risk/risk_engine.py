# layer3_risk/risk_engine.py
import networkx as nx
from typing import Any, Dict, List
from .formal_lattice import SecurityState3D, SrcSensitivity, RetLattice, ObsLattice, ExpLattice, lattice_join
from .risk_operators import get_operator


class RiskPropagationEngine:
    def __init__(self, lineage_graph: nx.DiGraph, state_space: Dict[str, Any]):
        self.graph = lineage_graph
        self.state_space = state_space

    def _init_formal_state(self, state) -> SecurityState3D:
        if not hasattr(state, "formal_state"):
            if state.r_init >= 80:
                src = SrcSensitivity.SECRET
            elif state.r_init >= 50:
                src = SrcSensitivity.HIGH
            elif state.r_init > 0:
                src = SrcSensitivity.LOW
            else:
                src = SrcSensitivity.PUBLIC

            r_lvl = RetLattice.FULL if src > SrcSensitivity.PUBLIC else RetLattice.NONE
            state.formal_state = SecurityState3D(src, r_lvl, ObsLattice.INTERNAL, ExpLattice.TRIVIAL)
        return state.formal_state

    def _node_metadata(self, node_id: str) -> Dict[str, Any]:
        node_obj = self.graph.nodes[node_id].get("obj")
        if node_obj is not None and hasattr(node_obj, "metadata"):
            return node_obj.metadata
        return {}

    def _is_projection_output(self, node_id: str) -> bool:
        return bool(self._node_metadata(node_id).get("is_projection_output", False))

    def _append_trace_once(self, state: Any, message: str) -> None:
        if message not in state.taint_trace:
            state.taint_trace.append(message)

    def _scalarize(self, formal_state: SecurityState3D) -> float:
        base_score_map = {0: 0.0, 1: 20.0, 2: 50.0, 3: 100.0}
        obs_multiplier = {
            ObsLattice.INTERNAL: 0.7,
            ObsLattice.INFERRED: 0.9,
            ObsLattice.EXPOSED: 1.0,
        }
        exp_multiplier = {
            ExpLattice.HARD: 0.8,
            ExpLattice.MODERATE: 0.9,
            ExpLattice.TRIVIAL: 1.0,
        }
        base_score = base_score_map.get(int(formal_state.src_sens), 0.0)
        retention_multiplier = int(formal_state.r_level) / 4.0
        return base_score * retention_multiplier * obs_multiplier[formal_state.o_level] * exp_multiplier[formal_state.e_level]

    def _propagate_single_node(self, node_id: str) -> bool:
        current_state = self.state_space[node_id]
        current_formal = self._init_formal_state(current_state)

        node_type = self.graph.nodes[node_id].get("type")
        node_name = self.graph.nodes[node_id].get("name")
        incoming_states: List[SecurityState3D] = []

        for parent_id in self.graph.predecessors(node_id):
            edge_data = self.graph.get_edge_data(parent_id, node_id)
            relation = edge_data.get("relation", "DATA_FLOW")
            if relation == "BELONGS_TO":
                continue

            parent_state = self.state_space[parent_id]
            parent_formal = self._init_formal_state(parent_state)
            if parent_formal.src_sens <= SrcSensitivity.PUBLIC:
                continue

            o_level = ObsLattice.INFERRED if relation == "CONTROL_FLOW" else parent_formal.o_level
            if relation == "DATA_FLOW" and self._is_projection_output(node_id):
                o_level = max(o_level, ObsLattice.EXPOSED)

            flow_state = SecurityState3D(
                src_sens=parent_formal.src_sens,
                r_level=parent_formal.r_level,
                o_level=max(o_level, current_formal.o_level),
                e_level=parent_formal.e_level,
            )
            incoming_states.append(flow_state)

            p_name = self.graph.nodes[parent_id].get("name")
            self._append_trace_once(
                current_state,
                f"-> receive from [{p_name}] ({relation}) | state {flow_state.r_level.name}/{flow_state.o_level.name}/{flow_state.e_level.name}",
            )

        if not incoming_states:
            return False

        if node_type == "FUNCTION":
            operator = get_operator(node_name)
            raw_ast = self._node_metadata(node_id).get("raw_ast")
            processed_state = operator.apply(incoming_states, ast_node=raw_ast)
            op_note = f", {operator.last_note}, alpha={operator.last_alpha:.2f}" if operator.last_alpha is not None else ""
            self._append_trace_once(
                current_state,
                f"* IFC operator [{operator.__class__.__name__}] -> {processed_state.r_level.name}/{processed_state.o_level.name}/{processed_state.e_level.name}{op_note}",
            )
        else:
            processed_state = lattice_join(incoming_states)

        next_formal = current_formal.join(processed_state)
        changed = next_formal != current_state.formal_state
        current_state.formal_state = next_formal

        next_score = self._scalarize(next_formal)
        if abs(next_score - current_state.r_current) > 1e-9:
            current_state.r_current = next_score
            changed = True

        return changed

    def propagate(self) -> Dict[str, Any]:
        try:
            ordered_nodes = list(nx.topological_sort(self.graph))
            has_cycle = False
        except nx.NetworkXUnfeasible:
            ordered_nodes = sorted(self.graph.nodes())
            has_cycle = True

        if not has_cycle:
            for node_id in ordered_nodes:
                self._propagate_single_node(node_id)
            return self.state_space

        max_iter = max(2, len(ordered_nodes) * 2)
        for _ in range(max_iter):
            changed_any = False
            for node_id in ordered_nodes:
                changed_any = self._propagate_single_node(node_id) or changed_any
            if not changed_any:
                break

        return self.state_space
