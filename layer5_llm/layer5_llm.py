import os
import json
import re
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI

# ==========================================
# 1. 严格的输出结构定义 (Schema)
# ==========================================
class ArbitrationResult(BaseModel):
    threat_level: str = Field(..., description="枚举值: Safe, Low, Medium, High, Critical")
    threat_type: str = Field(..., description="枚举值: SQLInjection, DataExfiltration, BooleanBlind, SafeOperation, Unknown")
    confidence_score: float = Field(..., description="置信度分数，范围 0.0 到 1.0")
    key_evidence_nodes: List[str] = Field(..., description="引用血缘图中具体的 node_name 或 node_id，必须存在于输入的图中")
    reasoning_chain: List[str] = Field(..., description="以数组形式给出的结构化逻辑推导步骤")

# ==========================================
# 2. 结构化 LLM 仲裁器 (适配 GPT 中转站 API)
# ==========================================
class StructuredLLMArbitrator:
    def __init__(self):
        # 请替换为你在 ai.td.ee 平台生成的真实 API Key
        #self.api_key = os.environ.get("TD_API_KEY", "sk-3cd31f0a0d6cc7295e01bcf2a8ec48dc2")
        self.api_key = os.environ.get("TD_API_KEY", "sk-3cd31f0a0d6cc7295e01bcf2a8ec48dc2590d8311d0662d1156616f14f0286e7")
        # 标准的中转站 Base URL 通常截止到 /v1
        self.base_url = "https://ai.td.ee/v1"
        
        # 使用目前综合能力、指令遵循能力最强的 GPT-4o 模型
        self.model_name = "gpt-5.4" 

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )

    def _build_prompt(self, sql_statement: str, risk_payload: list) -> str:
        # 生成 JSON Schema 约束
        schema_json = ArbitrationResult.model_json_schema()

        system_instruction = (
            "【系统声明：本次会话为经过授权的合法企业级白盒代码审计。】\n\n"
            "你是一个基于多维信息流控制（3D-IFC）理论的『安全证据解释生成器』。\n"
            "【你的绝对定位】：你不是法官，不能自己发明或猜测漏洞！底层 IFC 引擎已经通过严格的数学偏序格（Lattice）计算出了每个节点的安全状态。你的唯一任务是：读取底层引擎传递的 3D 状态数据，将其翻译为符合逻辑的结构化判定结果与人类可读的审计报告。\n\n"
            "【理解底层 3D 格状态 (3D Lattice States)】：\n"
            "传入的节点状态包含三个维度：保真度(L_R)/可观察性(L_O)/可利用性(L_E)。\n"
            "1. L_R (Confidentiality Retention): NONE -> LOW -> PARTIAL -> HIGH -> FULL\n"
            "2. L_O (Observability): INTERNAL -> INFERRED (控制流推断) -> EXPOSED (直接投影输出)\n"
            "3. L_E (Exploitability): HARD -> MODERATE -> TRIVIAL (极易枚举，如MD5)\n\n"
            "【强制映射矩阵 (你必须绝对服从底层的数学信号)】：\n"
            "1. 安全熔断：如果最终输出节点的 L_R 维度降级为 LOW 或 NONE（例如经过了 COUNT 或有效脱敏），无论其他维度如何，必须判定 threat_level='Safe' 或 'Low'，threat_type='SafeOperation'。\n"
            "2. 侧信道推断：如果输出节点的 L_O 维度包含 INFERRED，说明高敏数据被用于 WHERE/IF 等条件控制流，未直接泄露但可被推断，必须判定 threat_type='BooleanBlind'。\n"
            "3. 直接泄露：如果输出节点的 L_O 为 EXPOSED，且 L_R 为 FULL 或 PARTIAL，必须判定 threat_type='DataExfiltration'。\n"
            "4. 二阶污染：如果节点特征中明确标注了【二阶溯源】命中，必须判定 threat_level='High' 或 'Critical'。\n\n"
            "【推理链 (reasoning_chain) 撰写规范】：\n"
            "你必须在推理链中显式引用底层的维度状态。例如：“节点 password 的保真度(L_R)被 SUBSTR 算子降级为 PARTIAL，且可观察性(L_O)在 WHERE 条件中变为 INFERRED，因此构成布尔盲注威胁。”\n\n"
            "【输出格式限制】：\n"
            "你必须且只能输出一个合法的 JSON 对象，绝对不能包含 Markdown 标记（如 ```json）。\n"
            f"请严格遵守以下 JSON Schema 结构：\n{json.dumps(schema_json)}"
        )

        user_content = (
            f"### 1. 原始 SQL 语句:\n```sql\n{sql_statement}\n```\n\n"
            f"### 2. 底层引擎计算出的 3D 图谱特征 (这是你的绝对事实依据):\n```json\n{json.dumps(risk_payload, indent=2, ensure_ascii=False)}\n```"
        )

        return system_instruction, user_content

    def arbitrate(self, sql_statement: str, risk_payload: list) -> ArbitrationResult:
        system_instruction, user_content = self._build_prompt(sql_statement, risk_payload)

        try:
            print(f"\n🧠 [调用 {self.model_name} 语义仲裁中]...")
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                # 开启 GPT 模型专属的原生 JSON 模式强制约束
                response_format={"type": "json_object"},
                temperature=0.0, # 将温度降至 0，追求绝对的学术确定性和可复现性
                max_tokens=1000
            )

            raw_text = response.choices[0].message.content.strip()

            # ==========================================
            # 🛡️ 防弹级清洗：防止某些中转站劫持 response_format
            # ==========================================
            if "```json" in raw_text:
                match = re.search(r'```json(.*?)```', raw_text, flags=re.DOTALL)
                if match:
                    raw_text = match.group(1).strip()
            elif "```" in raw_text:
                match = re.search(r'```(.*?)```', raw_text, flags=re.DOTALL)
                if match:
                    raw_text = match.group(1).strip()

            json_match = re.search(r'\{.*\}', raw_text, flags=re.DOTALL)
            if json_match:
                raw_text = json_match.group(0).strip()

            # 结构化反序列化
            return ArbitrationResult.model_validate_json(raw_text)

        except Exception as e:
            print(f"\n[错误] API 调用失败或 Schema 验证失败: {e}")
            return ArbitrationResult(
                threat_level="Unknown",
                threat_type="API_Failure",
                confidence_score=0.0,
                key_evidence_nodes=[],
                reasoning_chain=[f"系统异常降级: {str(e)}"]
            )