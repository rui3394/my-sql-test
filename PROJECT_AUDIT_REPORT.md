# SQL Auditor 项目审查报告

## 1. 项目框架梳理（含子目录）

### 1.1 Python 文件总览

- `main_pipeline.py`：主流程入口，串联 Layer2/3/4/5。
- `layer1_sql/__init__.py`：空模块占位。
- `layer2_ast/parser.py`：SQL AST 解析与血缘图构建（核心）。
- `layer2_ast/parser - 副本.py`：历史副本实现，逻辑与主版本有偏差。
- `layer3_risk/formal_lattice.py`：IFC 三维格定义与 LUB 聚合。
- `layer3_risk/risk_state.py`：初始风险状态生成（静态资产 + 会话历史）。
- `layer3_risk/risk_operators.py`：函数算子传递规则（COUNT/MD5/SUBSTR 等）。
- `layer3_risk/risk_engine.py`：风险传播引擎（图拓扑传播）。
- `layer4_memory/layer4_context.py`：全局会话态（跨查询污点记忆）。
- `layer5_llm/layer5_llm.py`：LLM 结构化仲裁器（主版本）。
- `layer5_llm/layer5_llm - 副本.py`：历史副本实现，含不同 API 路线。
- 其余 `__init__.py`：模块初始化占位。

### 1.2 分层调用链

1. `main_pipeline.py` 调用 `MasterLineageVisitor.parse(sql)` 生成图谱。
2. `RiskStateEngine.initialize_state_space(session_id)` 初始化节点风险。
3. `RiskPropagationEngine.propagate()` 执行 IFC 风险传播。
4. Layer4 保存 INSERT 污点，支持“二阶注入”跨查询回溯。
5. Layer5 将图谱特征打包给 LLM，输出结构化 JSON 判定。

### 1.3 当前架构评价

- 分层思路清晰，具备论文系统原型常见的“解析-传播-记忆-仲裁”闭环。
- 但“理论声明”和“工程实现”存在多处不一致，尚不能直接认定为论文级完备实现。

## 2. 代码逻辑审查（是否合格 + 边界条件）

## 2.1 高严重问题（必须先修）

1. 密钥硬编码，存在严重泄露风险（不合格）
- 位置：`layer5_llm/layer5_llm.py:25`、`layer5_llm/layer5_llm - 副本.py:36`
- 问题：`os.environ.get(..., "sk-...")` 将真实格式密钥写入代码仓库。
- 影响：任何源码访问者可直接调用模型接口，属于高危安全缺陷。
- 建议：删除默认密钥，仅从环境变量读取；缺失时抛错并终止。

2. “3D-IFC 输入给 LLM”的理论与实现不一致（不合格）
- 理论宣称：Layer5 基于 L_R/L_O/L_E 做受约束判定。
- 实际载荷：`main_pipeline.py:69-74` 仅传 `final_risk_score` 与 `taint_propagation_trace`。
- 影响：LLM 不能稳定依据 3D 状态执行确定性矩阵，复现性不足。
- 建议：在 payload 中显式传递 `src_sens/r_level/o_level/e_level`。

3. 声称“香农熵动态衰减”，实际未实现（不合格）
- 位置：`layer3_risk/risk_operators.py:32-39`、`layer3_risk/risk_engine.py:71-72`、`layer2_ast/parser.py:194`
- 问题：
- `ProjectionPreservingTransfer` 固定将 `r_level` 降到 `PARTIAL`，未读取 `SUBSTR length`。
- `apply(ast_node=...)` 参数设计存在，但 `risk_engine` 调用时未传入 AST 节点。
- 影响：论文中的 `alpha_F = H(F(X))/H(X)` 当前是“叙述”，不是“实现”。

## 2.2 中严重问题（建议尽快修）

1. 风险标量化丢失 O/E 维度信息
- 位置：`layer3_risk/risk_engine.py:82-86`
- 问题：`r_current` 仅由 `src_sens` 与 `r_level` 计算，忽略 `o_level/e_level`。
- 影响：如 Boolean Blind 等控制流风险只能依赖 trace 文本间接表达，判定脆弱。

2. 无表前缀列绑定存在非确定性
- 位置：`layer2_ast/parser.py:137`
- 问题：`tables = list(set(...)); return tables[0]` 依赖集合迭代顺序，可能跨运行波动。
- 影响：多表查询中 `SELECT password` 可能绑定到不同表，结果不可复现。

3. INSERT 映射存在边界条件风险
- 位置：`main_pipeline.py:28-31`
- 问题：默认以 `Schema + SELECT expressions` 的 zip 映射推断列关系，未覆盖 `VALUES`、列数不一致等情形。
- 影响：可能错配或静默丢失污点传播信息。

4. 拓扑排序失败后回退“原节点顺序”
- 位置：`layer3_risk/risk_engine.py:27-28`
- 问题：遇到环时直接 `list(self.graph.nodes())`，传播顺序不受控。
- 影响：循环依赖场景下结果不稳定。

## 2.3 低严重问题（可排期）

1. `RISK_THRESHOLD` 定义未使用
- 位置：`layer3_risk/risk_state.py:9`

2. 存在“副本文件”并且逻辑分叉
- 文件：`parser - 副本.py`、`layer5_llm - 副本.py`
- 影响：维护与评审时容易误用，削弱可追溯性。

3. 运行验证受写权限限制
- 现象：`python -m compileall .` 因 `__pycache__` 写入权限被拒绝而失败。
- 影响：当前环境未完成完整编译验证，不代表语法必然错误，但 CI 需要明确处理。

## 2.4 是否达到“专业论文级”

结论：**当前版本接近“有理论框架的工程原型”，但尚未达到严格论文级。**

主要缺口：
- 理论-实现闭环不完整（3D 维度与熵衰减未完整落地）。
- 缺少系统化实验框架（数据集、基线、统计显著性检验）。
- 可复现性不足（无 deterministic test harness、无固定版本实验脚本）。

## 2.5 创新性判断

结论：**有创新点，但需要“实现可验证”才能成立为论文贡献。**

可被认可的创新方向：
- IFC 格理论引入 SQL 审计图传播。
- 跨查询会话态用于二阶注入追踪。
- LLM 受结构化特征约束而非自由裁决。

当前风险：
- 若核心创新（熵驱动衰减、3D 决策矩阵）仅停留在提示词/注释层，评审会判定为“概念创新强、实现证据弱”。

## 3. 核心思想与公式提炼

## 3.1 核心思想（一句话）

以 AST 血缘图为载体，使用 IFC 格上的单调传播计算污点风险，再以受约束的结构化 LLM 完成高层语义归因。

## 3.2 核心数学对象

1. 污点安全格
- \(\mathcal{L} = \langle S, \sqsubseteq, \sqcup, \sqcap \rangle\)
- 多源汇聚采用最小上界：
- \(R(v) = \bigsqcup_i R(u_i)\)

2. 三维安全状态（实现中对应 `SecurityState3D`）
- \(\ell(v) = \langle L_R, L_O, L_E \rangle\)
- 逐维 join：
- \(\ell_1 \sqcup \ell_2 = \langle \max(L_R), \max(L_O), \max(L_E) \rangle\)

3. 信息降级（论文目标公式）
- \(\alpha_F = \frac{H(F(X))}{H(X)}\)
- 语义：函数 \(F\) 造成信息损失时，保真度按熵比动态衰减。

4. 当前代码中的代理打分（工程近似）
- `base_score(src_sens) ∈ {0,20,50,100}`
- `retention_multiplier = r_level / 4`
- `r_current = base_score * retention_multiplier`

## 3.3 理论与当前实现差距（必须在论文中诚实披露）

- 熵公式尚未在算子中真实计算。
- LLM 输入中未显式传 3D 离散状态，只传了标量分数与 trace。
- 当前“决策矩阵”更多体现在 prompt 约束，缺少程序级硬规则裁决器。

## 4. 建议的最小整改路线（可直接作为下一阶段计划）

1. 安全合规
- 移除全部硬编码密钥，接入 `.env` + 启动时强校验。

2. 理论落地
- 在 `parser.py` 提取函数参数（如 `SUBSTR length`）进入 metadata。
- 在 `risk_engine.py` 将 `raw_ast` 传入 `operator.apply(..., ast_node=...)`。
- 在 `risk_operators.py` 实现基于参数的 `alpha` 计算逻辑（至少离散分段版）。

3. 可复现评估
- 增加固定种子、固定模型版本、固定 schema 的评测脚本。
- 输出 Precision/Recall/F1 + 混淆矩阵，和 Semgrep/传统数据流/Vanilla LLM 做对比。

