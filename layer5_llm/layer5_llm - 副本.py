import os
import json
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI

# ==========================================
# 1. 严格的输出结构定义 (Schema)
# 解决审稿人痛点: 无法计算 Precision/Recall，缺少评估基准
# ==========================================
class ArbitrationResult(BaseModel):
    threat_level: str = Field(..., description="枚举值: Safe, Low, Medium, High, Critical")
    threat_type: str = Field(..., description="枚举值: SQLInjection, DataExfiltration, BooleanBlind, SafeOperation, Unknown")
    confidence_score: float = Field(..., description="置信度分数，范围 0.0 到 1.0")
    key_evidence_nodes: List[str] = Field(..., description="引用血缘图中具体的 node_name 或 node_id，必须存在于输入的图中")
    reasoning_chain: List[str] = Field(..., description="以数组形式给出的结构化逻辑推导步骤")

# ==========================================
# 2. 结构化 LLM 仲裁器 (支持 OpenAI 与 DeepSeek 无缝切换)
# 解决审稿人痛点: 解决单点故障，支持未来开源模型复现
# ==========================================
class StructuredLLMArbitrator:
    def __init__(self, provider: str = "deepseek"):
        """
        初始化仲裁器
        :param provider: "openai" 或 "deepseek"
        """
        self.provider = provider.lower()
        
        # 【预留 DeepSeek 接口】：完全兼容 OpenAI SDK 的开源替代方案
        if self.provider == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY", "X0DSXLFHG0W1GOLP6AS9DZOPGOC44XAMRLSESADQ")
            base_url = "https://ai.gitee.com/v1"
            self.model_name = "DeepSeek-R1-Distill-Qwen-7B" # 或 deepseek-coder
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "sk-3cd31f0a0d6cc7295e01bcf2a8ec48dc2590d8311d0662d1156616f14f0286e7")
            base_url = "https://ai.td.ee"
            # 兼容你提到的较新模型，可根据实际使用情况替换为 gpt-4o 等
            self.model_name = "gpt-4o" 

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def _build_prompt(self, sql_statement: str, risk_payload: list) -> str:
        """
        构建强约束提示词，要求 LLM 将图结构特征与 SQL 语义结合
        """
        system_instruction = (
            "你是一个基于信息流控制（IFC）理论的 SQL 代码审计语义特征提取器。\n"
            "你的任务是结合用户输入的 '原始 SQL' 与前置引擎计算出的 'DAG 图谱风险特征'，"
            "进行最终的交叉验证与结构化特征提取。\n\n"
            "【重要约束】:\n"
            "1. 你必须严格遵循 JSON Schema 进行输出。\n"
            "2. key_evidence_nodes 必须严格引用图谱中 final_risk_score > 0 的节点名称。\n"
            "3. 如果前置图谱显示风险在聚合/脱敏算子中衰减（如 final_risk_score 极低），你应该将其判定为 Safe 或 Low。"
        )

        user_content = (
            f"### 1. 原始 SQL 语句:\n```sql\n{sql_statement}\n```\n\n"
            f"### 2. 前置引擎传递的结构化图谱风险特征:\n```json\n{json.dumps(risk_payload, indent=2, ensure_ascii=False)}\n```"
        )

        return system_instruction, user_content

    def arbitrate(self, sql_statement: str, risk_payload: list) -> ArbitrationResult:
        """
        执行结构化仲裁，返回 Pydantic 对象，彻底消除解析异常的风险
        """
        system_instruction, user_content = self._build_prompt(sql_statement, risk_payload)

        try:
            # 使用 OpenAI 提供的 Structured Outputs (JSON Schema 模式)
            response = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                response_format=ArbitrationResult,
                temperature=0.1, # 保持极低温度以提高确定性
                max_tokens=1000
            )
            
            # 返回经过严格验证的 Pydantic 对象
            return response.choices[0].message.parsed
            
        except Exception as e:
            print(f"[错误] API 调用失败或 Schema 验证失败: {e}")
            # 解决审稿人痛点：增加降级策略 (Fallback)
            return ArbitrationResult(
                threat_level="Unknown",
                threat_type="API_Failure",
                confidence_score=0.0,
                key_evidence_nodes=[],
                reasoning_chain=[f"系统异常降级: {str(e)}"]
            )