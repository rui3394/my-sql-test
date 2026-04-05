import sqlglot
import sqlglot.expressions as exp
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json
import networkx as nx

# ==========================================
# 1. 核心数据结构
# ==========================================
class NodeType(Enum):
    TABLE = auto()
    COLUMN = auto()
    LITERAL = auto()
    OPERATOR = auto()
    FUNCTION = auto()

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
        # 【疫苗 1】：绝对禁止自环 (Self-Loop)，保护 DAG 拓扑排序不崩溃！
        if edge.source_id == edge.target_id:
            return 
        # 绝对禁止重复边
        for e in self.edges:
            if e.source_id == edge.source_id and e.target_id == edge.target_id and e.edge_type == edge.edge_type:
                return
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

    def _resolve_table_node_id(self, prefix: Optional[str]) -> Optional[str]:
        """【疫苗 2】：盲认领机制。拯救没有前缀的孤儿字段 (如 SELECT password)"""
        for scope in reversed(self.scope_stack):
            if prefix:
                if prefix in scope.table_aliases:
                    return scope.table_aliases[prefix]
            else:
                # 如果字段没写别名，直接挂载到当前作用域下的第一张表上
                tables = list(dict.fromkeys(scope.table_aliases.values()))
                if tables:
                    return tables[0]
        return None

    def _add_belongs_to_edge(self, source_id: str, target_id: str):
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
        
        if node_type == NodeType.COLUMN:
            parent_table_id = self._resolve_table_node_id(prefix)
            if parent_table_id:
                self._add_belongs_to_edge(new_id, parent_table_id)
            else:
                self._current_scope().pending_columns.append((new_id, prefix))
                
        return new_id

    def _build_pipeline(self, expr: exp.Expression, target_id: str, edge_type: EdgeType, context: str):
        if isinstance(expr, exp.Column):
            src_id = self._get_or_create_node(NodeType.COLUMN, expr.name, expr.table)
            self.graph.add_edge(Edge(source_id=src_id, target_id=target_id, edge_type=edge_type, context=context))
        
        elif isinstance(expr, exp.Literal):
            lit_id = self._get_or_create_node(NodeType.LITERAL, expr.name, None)
            self.graph.add_edge(Edge(source_id=lit_id, target_id=target_id, edge_type=edge_type, context=context))
            
        elif isinstance(expr, exp.Func):
            if isinstance(expr, exp.Anonymous):
                func_name = expr.name.upper()
            else:
                func_name = expr.key.upper()
                
            func_id = self._get_or_create_node(NodeType.FUNCTION, func_name, None)
            
            # ==========================================================
            # 【终极修复 1】：将原生的 sqlglot AST 节点存入元数据，带给 Layer 3！
            # ==========================================================
            self.graph.nodes[func_id].metadata['raw_ast'] = expr
            
            self.graph.add_edge(Edge(source_id=func_id, target_id=target_id, edge_type=edge_type, context=f"{func_name}_OUT"))
            
            for k, v in expr.args.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp.Expression):
                            self._build_pipeline(item, func_id, EdgeType.DATA_FLOW, f"{func_name}_ARG")
                elif isinstance(v, exp.Expression):
                    self._build_pipeline(v, func_id, EdgeType.DATA_FLOW, f"{func_name}_ARG")
        else:
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

        if isinstance(node, exp.Table):
            table_name = node.name
            real_source = self._resolve_table_source(table_name)
            alias = node.alias or table_name
            t_id = self._get_or_create_node(NodeType.TABLE, table_name, alias)
            self.graph.nodes[t_id].metadata["source_type"] = real_source
            self._current_scope().table_aliases[alias] = t_id
            self._current_scope().table_aliases[table_name] = t_id

        if isinstance(node, exp.Join):
            join_type = str(node.args.get("side") or "INNER").upper()
            on_clause = node.args.get("on")
            
            if on_clause:
                for condition in on_clause.find_all((exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ, exp.Like, exp.ILike)):
                    left_expr = condition.left
                    right_expr = condition.right

                    if left_expr and right_expr:
                        if isinstance(left_expr, exp.Column):
                            target_id = self._get_or_create_node(NodeType.COLUMN, left_expr.name, left_expr.table)
                            self._build_pipeline(right_expr, target_id, EdgeType.CONTROL_FLOW, f"{join_type}_JOIN_ON")
                        elif isinstance(right_expr, exp.Column):
                            target_id = self._get_or_create_node(NodeType.COLUMN, right_expr.name, right_expr.table)
                            self._build_pipeline(left_expr, target_id, EdgeType.CONTROL_FLOW, f"{join_type}_JOIN_ON")
                        else:
                            # 【核心修复】：两边都不是纯列（比如都是函数或常量）
                            # 创建一个虚拟的 EVALUATION 节点作为判断锚点
                            target_id = self._get_or_create_node(NodeType.OPERATOR, "EVALUATION", None)
                            self._build_pipeline(left_expr, target_id, EdgeType.CONTROL_FLOW, f"{join_type}_JOIN_EVAL_L")
                            self._build_pipeline(right_expr, target_id, EdgeType.CONTROL_FLOW, f"{join_type}_JOIN_EVAL_R")

        if isinstance(node, exp.Select):
            for expression in node.expressions:
                actual_expr = expression.this if isinstance(expression, exp.Alias) else expression
                alias_name = expression.alias if isinstance(expression, exp.Alias) else None
                
# 修改过的代码：
                if not alias_name:
                    if isinstance(actual_expr, exp.Column):
                        alias_name = actual_expr.name
                    elif isinstance(actual_expr, exp.Func):
                        if isinstance(actual_expr, exp.Anonymous):
                            alias_name = f"{actual_expr.name}_out".lower()
                        else:
                            alias_name = f"{actual_expr.key}_out".lower()
                    else:
                        alias_name = "expr_out"
                        
                # Keep projection node independent from source column node with the same name.
                target_id = self._get_or_create_node(NodeType.COLUMN, alias_name, "__OUTPUT__")
                self.graph.nodes[target_id].metadata["is_projection_output"] = True
                self._build_pipeline(actual_expr, target_id, EdgeType.DATA_FLOW, "ALIAS_PROJECTION")

        # 【疫苗 3】：精准提取 Where 条件对，彻底消灭由 AND/OR 造成的结构环
        if isinstance(node, exp.Where):
            for condition in node.find_all((exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ, exp.Like, exp.ILike)):
                left_expr = condition.left
                right_expr = condition.right

                if left_expr and right_expr:
                    if isinstance(left_expr, exp.Column):
                        target_id = self._get_or_create_node(NodeType.COLUMN, left_expr.name, left_expr.table)
                        self._build_pipeline(right_expr, target_id, EdgeType.CONTROL_FLOW, "WHERE_CONDITION")
                    elif isinstance(right_expr, exp.Column):
                        target_id = self._get_or_create_node(NodeType.COLUMN, right_expr.name, right_expr.table)
                        self._build_pipeline(left_expr, target_id, EdgeType.CONTROL_FLOW, "WHERE_CONDITION")
                    else:
                        # 【核心修复】：处理 WHERE MD5(pw) = '123' 这种场景
                        target_id = self._get_or_create_node(NodeType.OPERATOR, "EVALUATION", None)
                        self._build_pipeline(left_expr, target_id, EdgeType.CONTROL_FLOW, "WHERE_EVAL_L")
                        self._build_pipeline(right_expr, target_id, EdgeType.CONTROL_FLOW, "WHERE_EVAL_R")

        for child in [c for c in immediate_children if isinstance(c, exp.With)]:
            self._visit(child)
        for child in [c for c in immediate_children if not isinstance(c, exp.With)]:
            self._visit(child)

        if is_subquery:
            self._pop_scope()
