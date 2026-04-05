import sqlglot
import sqlglot.expressions as exp
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json
import networkx as nx

# ==========================================
# 1. 核心数据结构 (【修改 1】：增加 FUNCTION 类型)
# ==========================================
class NodeType(Enum):
    TABLE = auto()
    COLUMN = auto()
    LITERAL = auto()
    OPERATOR = auto()
    FUNCTION = auto() # 【新增】用于承载 L3 的算子实体

class EdgeType(Enum):
    DATA_FLOW = auto()       
    CONTROL_FLOW = auto()    
    BELONGS_TO = auto()      

@dataclass
class Node:
    id: str
    node_type: NodeType
    name: str
    alias: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    context: Optional[str] = None

@dataclass
class LineageGraph:
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def export_to_json(self) -> str:
        payload = {
            "graph_metadata": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges)
            },
            "nodes": [
                {
                    "id": n.id,
                    "type": n.node_type.name,
                    "name": n.name,
                    "alias": n.alias,
                    "metadata": n.metadata
                } for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation": e.edge_type.name,
                    "context": e.context
                } for e in self.edges
            ]
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def to_networkx(self) -> nx.DiGraph:
        nx_graph = nx.DiGraph()
        for node_id, node in self.nodes.items():
            nx_graph.add_node(node_id, obj=node, type=node.node_type.name, name=node.name)
        for edge in self.edges:
            nx_graph.add_edge(edge.source_id, edge.target_id, relation=edge.edge_type.name, context=edge.context)
        return nx_graph

# ==========================================
# 2. 作用域管理工具
# ==========================================
class Scope:
    def __init__(self, name: str):
        self.name = name
        self.ctes: Dict[str, exp.Expression] = {}
        self.table_aliases: Dict[str, str] = {}
        self.pending_columns: List[tuple] = []

# ==========================================
# 3. 大一统解析引擎
# ==========================================
class MasterLineageVisitor:
    def __init__(self, dialect: str = "postgres"):
        self.dialect = dialect
        self.graph = LineageGraph()
        self.scope_stack: List[Scope] = [Scope("global")]
        self._node_registry: Dict[str, str] = {}

    def _current_scope(self) -> Scope:
        return self.scope_stack[-1]

    def _push_scope(self, name: str):
        self.scope_stack.append(Scope(name))

    def _pop_scope(self):
        if len(self.scope_stack) > 1:
            self._flush_pending_columns(self.scope_stack[-1])
            self.scope_stack.pop()

    def _resolve_table_source(self, table_name: str) -> str:
        for scope in reversed(self.scope_stack):
            if table_name in scope.ctes:
                return f"CTE_VIRTUAL_TABLE:{table_name}"
        return f"PHYSICAL_TABLE:{table_name}"

    def _resolve_table_node_id(self, prefix: str) -> Optional[str]:
        for scope in reversed(self.scope_stack):
            if prefix in scope.table_aliases:
                return scope.table_aliases[prefix]
        return None

    def _add_belongs_to_edge(self, source_id: str, target_id: str):
        for e in self.graph.edges:
            if e.source_id == source_id and e.target_id == target_id and e.edge_type == EdgeType.BELONGS_TO:
                return
        self.graph.add_edge(Edge(source_id, target_id, EdgeType.BELONGS_TO, "DEFERRED_BELONGS_TO"))

    def _flush_pending_columns(self, scope: Scope):
        for node_id, prefix in scope.pending_columns:
            parent_table_id = self._resolve_table_node_id(prefix)
            if parent_table_id:
                self._add_belongs_to_edge(node_id, parent_table_id)

    def _get_or_create_node(self, node_type: NodeType, name: str, prefix: Optional[str] = None) -> str:
        scope_name = self._current_scope().name
        prefix_str = prefix or 'NONE'
        signature = f"{scope_name}::{prefix_str}::{name}::{node_type.name}"
        
        if signature in self._node_registry:
            return self._node_registry[signature]
            
        new_id = f"{node_type.name.lower()}_{len(self._node_registry) + 1}"
        new_node = Node(id=new_id, node_type=node_type, name=name, alias=prefix)
        new_node.metadata["table_prefix"] = prefix
        self.graph.add_node(new_node)
        self._node_registry[signature] = new_id
        
        if node_type == NodeType.COLUMN and prefix:
            parent_table_id = self._resolve_table_node_id(prefix)
            if parent_table_id:
                self._add_belongs_to_edge(new_id, parent_table_id)
            else:
                self._current_scope().pending_columns.append((new_id, prefix))
                
        return new_id

    # ==========================================
    # 【修改 2：新增核心方法】递归管道构造器
    # ==========================================
    def _build_pipeline(self, expr: exp.Expression, target_id: str, edge_type: EdgeType, context: str):
        """精准拆解嵌套函数，构建一条首尾相连的有向无环链条"""
        # 终点 1：遇到基础列，直接连向 target
        if isinstance(expr, exp.Column):
            src_id = self._get_or_create_node(NodeType.COLUMN, expr.name, expr.table)
            self.graph.add_edge(Edge(source_id=src_id, target_id=target_id, edge_type=edge_type, context=context))
        
        # 终点 2：遇到基础常量，连向 target
        elif isinstance(expr, exp.Literal):
            lit_id = self._get_or_create_node(NodeType.LITERAL, expr.name, None)
            self.graph.add_edge(Edge(source_id=lit_id, target_id=target_id, edge_type=edge_type, context=context))
            
        # 【关键拦截】：遇到函数！
        elif isinstance(expr, exp.Func):
            func_name = expr.key.upper()
            # 1. 创建函数节点
            func_id = self._get_or_create_node(NodeType.FUNCTION, func_name, None)
            
            # 2. 让当前函数流向它的上一级 Target (比如外层函数或最终别名)
            self.graph.add_edge(Edge(source_id=func_id, target_id=target_id, edge_type=edge_type, context=f"{func_name}_OUT"))
            
            # 3. 递归：让函数内部的参数继续解析，并将流向目标设定为当前函数节点
            for k, v in expr.args.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp.Expression):
                            self._build_pipeline(item, func_id, edge_type, f"{func_name}_ARG")
                elif isinstance(v, exp.Expression):
                    self._build_pipeline(v, func_id, edge_type, f"{func_name}_ARG")
        else:
            # 其他节点 (如 AND, OR, 括号)，剥开外壳继续往下解析
            for k, v in expr.args.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp.Expression):
                            self._build_pipeline(item, target_id, edge_type, context)
                elif isinstance(v, exp.Expression):
                    self._build_pipeline(v, target_id, edge_type, context)

    def parse(self, sql: str) -> LineageGraph:
        ast_root = sqlglot.parse_one(sql, read=self.dialect)
        self._visit(ast_root)
        self._flush_pending_columns(self.scope_stack[0])
        return self.graph

    def _visit(self, node):
        if not isinstance(node, exp.Expression):
            return

        is_subquery = isinstance(node, exp.Subquery)
        if is_subquery:
            sub_alias = node.alias or "anonymous_subquery"
            self._push_scope(f"Subquery_{sub_alias}")

        immediate_children = []
        for k, v in node.args.items():
            if isinstance(v, list):
                immediate_children.extend([item for item in v if isinstance(item, exp.Expression)])
            elif isinstance(v, exp.Expression):
                immediate_children.append(v)

        for child in immediate_children:
            if isinstance(child, exp.With):
                for cte in child.expressions:
                    cte_name = cte.alias
                    if cte_name not in self._current_scope().ctes:
                        self._current_scope().ctes[cte_name] = cte.this

        # ----------------------------------------
        # 融合点 A: Table
        # ----------------------------------------
        if isinstance(node, exp.Table):
            table_name = node.name
            real_source = self._resolve_table_source(table_name)
            alias = node.alias or table_name
            
            t_id = self._get_or_create_node(NodeType.TABLE, table_name, alias)
            self.graph.nodes[t_id].metadata["source_type"] = real_source
            
            self._current_scope().table_aliases[alias] = t_id
            self._current_scope().table_aliases[table_name] = t_id

        # ----------------------------------------
        # 融合点 B: Join
        # ----------------------------------------
        if isinstance(node, exp.Join):
            join_type = str(node.args.get("side") or "INNER").upper()
            on_clause = node.args.get("on")
            if on_clause:
                columns = list(on_clause.find_all(exp.Column))
                if len(columns) >= 2:
                    left_col, right_col = columns[0], columns[1]
                    lc_id = self._get_or_create_node(NodeType.COLUMN, left_col.name, left_col.table)
                    rc_id = self._get_or_create_node(NodeType.COLUMN, right_col.name, right_col.table)
                    self.graph.add_edge(Edge(source_id=lc_id, target_id=rc_id, edge_type=EdgeType.CONTROL_FLOW, context=f"{join_type}_JOIN_ON"))

        # ----------------------------------------
        # 【修改 3】：融合点 C: Select (启用管道构造器)
        # ----------------------------------------
        if isinstance(node, exp.Select):
            for expression in node.expressions:
                actual_expr = expression.this if isinstance(expression, exp.Alias) else expression
                alias_name = expression.alias if isinstance(expression, exp.Alias) else None
                
                # 确定输出目标节点名称
                if not alias_name:
                    if isinstance(actual_expr, exp.Column):
                        alias_name = actual_expr.name
                    elif isinstance(actual_expr, exp.Func):
                        alias_name = f"{actual_expr.key}_out"
                    else:
                        alias_name = "expr_out"
                        
                # 创建目标锚点
                target_id = self._get_or_create_node(NodeType.COLUMN, alias_name, None)
                
                # 调用管道引擎，处理无限级嵌套
                self._build_pipeline(actual_expr, target_id, EdgeType.DATA_FLOW, "ALIAS_PROJECTION")

        # ----------------------------------------
        # 融合点 D: Where (修复控制流方向：让污染源流向验证列)
        # ----------------------------------------
        if isinstance(node, exp.Where):
            for condition in node.find_all(exp.Binary):
                left_expr = condition.left
                right_expr = condition.right

                if left_expr and right_expr:
                    # 将目标锚点 (Target) 锁定为左侧的列 (例如 u.status)
                    if isinstance(left_expr, exp.Column):
                        target_id = self._get_or_create_node(NodeType.COLUMN, left_expr.name, left_expr.table)
                    else:
                        target_id = self._get_or_create_node(NodeType.OPERATOR, "EVALUATION", None)
                        
                    # 管道构造器：让右侧的输入 (例如 '1=1') 作为源头，流向左侧的列
                    self._build_pipeline(right_expr, target_id, EdgeType.CONTROL_FLOW, "WHERE_CLAUSE")

        for child in [c for c in immediate_children if isinstance(c, exp.With)]:
            self._visit(child)
        for child in [c for c in immediate_children if not isinstance(c, exp.With)]:
            self._visit(child)

        if is_subquery:
            self._pop_scope()

# ==========================================
# 4. 运行验证
# ==========================================
if __name__ == "__main__":
    # 模拟一条存在高层级嵌套加密和哈希脱敏的 SQL
    risk_sql = """
        SELECT 
            MD5(SUBSTR(u.password, 1, 5)) AS hash_pw,
            COUNT(u.id) AS user_count
        FROM users u 
        WHERE CONCAT(u.username, 'admin') = 'rootadmin';
    """
    
    print("正在启动 MasterLineageVisitor 解析带有函数的 SQL...")
    master_visitor = MasterLineageVisitor()
    result_graph = master_visitor.parse(risk_sql)
    
    nx_g = result_graph.to_networkx()
    print(f"\n引擎合并完毕！NetworkX 共生成 {nx_g.number_of_nodes()} 个节点，{nx_g.number_of_edges()} 条边。\n")
    
    print("--- 边关系 (Edges) 溯源验证 ---")
    for u, v, data in nx_g.edges(data=True):
        source = nx_g.nodes[u]['name']
        source_type = nx_g.nodes[u]['type']
        target = nx_g.nodes[v]['name']
        target_type = nx_g.nodes[v]['type']
        rel = data['relation']
        ctx = data['context']
        print(f"[{source}]({source_type}) --({rel} : {ctx})--> [{target}]({target_type})")