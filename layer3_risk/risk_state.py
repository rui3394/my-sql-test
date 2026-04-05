import networkx as nx
from dataclasses import dataclass, field
from typing import Dict, Any
from layer4_memory.layer4_context import global_session_manager

# ==========================================
# 1. 数学模型常量定义
# ==========================================
RISK_THRESHOLD = 100.0  # 阈值 tau

# 资产字典：定义真实表名与高危字段
SENSITIVE_ASSETS = {
    "users.password": 100.0,
    "users.id": 20.0,
    "profiles.level": 10.0,
    "active_users.raw_name": 50.0 
}

@dataclass
class RiskState:
    node_id: str
    r_init: float = 0.0     
    r_current: float = 0.0  
    is_sink: bool = False   
    taint_trace: list = field(default_factory=list)

class RiskStateEngine:
    def __init__(self, lineage_graph: nx.DiGraph):
        self.graph = lineage_graph
        self.state_space: Dict[str, RiskState] = {}
        
    def _evaluate_input_source(self, literal_value: str) -> float:
        val = str(literal_value).upper()
        if "OR" in val or "=" in val or "SLEEP" in val or "UNION" in val:
            return 100.0
        if "--" in val or "/*" in val:
            return 50.0
        return 0.0

    # 【核心修复】：基于图论的真实表名溯源
    def _find_real_table_name(self, node_id: str) -> str:
        """
        顺着 NetworkX 图中的 BELONGS_TO 边向外寻找，获取亲生父母的真实名字
        """
        # 遍历该节点所有向外的边
        for u, v, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == 'BELONGS_TO':
                target_node = self.graph.nodes[v]
                if target_node.get('type') == 'TABLE':
                    return target_node.get('name', '')
        return ""

    def initialize_state_space(self, session_id: str = "default_session") -> Dict[str, RiskState]:
        """
        【升级】：增加 session_id 参数，引入跨时空查库能力
        """
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type")
            node_name = data.get("name")
            
            state = RiskState(node_id=node_id)
            
            if node_type == "LITERAL":
                r_init = self._evaluate_input_source(node_name)
                if r_init > 0:
                    state.r_init = r_init
                    state.taint_trace.append(f"发现高危常量输入 [{node_name}], 注入动能: {r_init}")
                    
            elif node_type == "COLUMN":
                real_table_name = self._find_real_table_name(node_id)
                if real_table_name:
                    asset_key = f"{real_table_name}.{node_name}"
                    
                    # --------------------------------------------------
                    # 🌟 核心升级：双库融合寻源 (静态资产字典 + 动态历史状态库)
                    # --------------------------------------------------
                    # 1. 先查静态物理高敏字典 (里程碑一/二的能力)
                    static_risk = SENSITIVE_ASSETS.get(asset_key, 0.0)
                    
                    # 2. 再查跨查询的动态历史污染库 (里程碑四的杀手锏)
                    dynamic_risk = global_session_manager.get_taint_state(session_id, real_table_name, node_name)
                    
                    # 取两者最大值作为真正的初始动能
                    r_init = max(static_risk, dynamic_risk)
                    
                    if r_init > 0:
                        state.r_init = r_init
                        if dynamic_risk > static_risk:
                            state.taint_trace.append(f"🌐 [二阶溯源] 命中全局历史污染状态 [{asset_key}], 继承浓度: {r_init}")
                        else:
                            state.taint_trace.append(f"识别高敏数据资产 [{asset_key}], 初始价值: {r_init}")
            
            state.r_current = state.r_init
            self.state_space[node_id] = state
            
        return self.state_space