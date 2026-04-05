from typing import Dict


class SessionStateManager:
    """Global/session taint state manager."""

    def __init__(self):
        # { session_id: { "table.column": risk_score } }
        self._store: Dict[str, Dict[str, float]] = {}

    def save_taint_state(self, session_id: str, table_name: str, column_name: str, risk_score: float):
        if session_id not in self._store:
            self._store[session_id] = {}

        asset_key = f"{table_name}.{column_name}"
        current_score = self._store[session_id].get(asset_key, 0.0)
        self._store[session_id][asset_key] = max(current_score, risk_score)
        print(f"[GLOBAL_STATE] persist taint label: [{asset_key}] -> score: {risk_score}")

    def get_taint_state(self, session_id: str, table_name: str, column_name: str) -> float:
        if session_id not in self._store:
            return 0.0
        asset_key = f"{table_name}.{column_name}"
        return self._store[session_id].get(asset_key, 0.0)


# singleton
global_session_manager = SessionStateManager()
