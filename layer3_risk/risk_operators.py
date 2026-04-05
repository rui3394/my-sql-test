# layer3_risk/risk_operators.py
from typing import Any, List, Optional
from .formal_lattice import ExpLattice, RetLattice, SecurityState3D, lattice_join


class TransferFunction:
    """Abstract transfer function."""

    def __init__(self):
        self.last_alpha: Optional[float] = None
        self.last_note: str = ""

    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        raise NotImplementedError()


class IdentityTransfer(TransferFunction):
    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        return lattice_join(input_states)


class AggregationTransfer(TransferFunction):
    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        lub_state = lattice_join(input_states)
        lub_state.r_level = min(lub_state.r_level, RetLattice.LOW)
        self.last_alpha = 0.25
        self.last_note = "aggregation_declassification"
        return lub_state


class OneWayTransformTransfer(TransferFunction):
    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        lub_state = lattice_join(input_states)
        lub_state.r_level = min(lub_state.r_level, RetLattice.LOW)
        lub_state.e_level = ExpLattice.TRIVIAL
        self.last_alpha = 0.25
        self.last_note = "one_way_transform_low_retention"
        return lub_state


class ProjectionPreservingTransfer(TransferFunction):
    def _extract_length(self, ast_node: Any) -> Optional[float]:
        if ast_node is None:
            return None
        candidate = ast_node.args.get("length")
        if candidate is None:
            candidate = ast_node.args.get("len")
        if candidate is None:
            return None
        if hasattr(candidate, "is_int") and candidate.is_int:
            try:
                return float(candidate.name)
            except (TypeError, ValueError):
                return None
        if hasattr(candidate, "name"):
            try:
                return float(candidate.name)
            except (TypeError, ValueError):
                return None
        return None

    def _estimate_alpha(self, length: Optional[float]) -> float:
        # Entropy-ratio approximation: alpha = H(F(X))/H(X)
        if length is None:
            return 0.5
        if length <= 0:
            return 0.0
        if length <= 2:
            return 0.2
        if length <= 8:
            return 0.5
        return 0.8

    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        lub_state = lattice_join(input_states)
        alpha = self._estimate_alpha(self._extract_length(ast_node))
        self.last_alpha = alpha
        self.last_note = "projection_entropy_ratio"

        if alpha <= 0.0:
            target_r = RetLattice.NONE
        elif alpha <= 0.25:
            target_r = RetLattice.LOW
        elif alpha <= 0.60:
            target_r = RetLattice.PARTIAL
        else:
            target_r = RetLattice.HIGH

        lub_state.r_level = min(lub_state.r_level, target_r)
        return lub_state


class UnknownUDFTransfer(TransferFunction):
    def apply(self, input_states: List[SecurityState3D], ast_node: Any = None) -> SecurityState3D:
        lub_state = lattice_join(input_states)
        lub_state.r_level = RetLattice.FULL
        lub_state.e_level = ExpLattice.TRIVIAL
        self.last_alpha = 1.0
        self.last_note = "unknown_udf_conservative"
        return lub_state


OPERATOR_REGISTRY = {
    "AS": IdentityTransfer(),
    "CAST": IdentityTransfer(),
    "SUBSTR": ProjectionPreservingTransfer(),
    "SUBSTRING": ProjectionPreservingTransfer(),
    "MD5": OneWayTransformTransfer(),
    "COUNT": AggregationTransfer(),
    "SUM": AggregationTransfer(),
}


def get_operator(func_name: str) -> TransferFunction:
    return OPERATOR_REGISTRY.get(str(func_name).upper(), UnknownUDFTransfer())
