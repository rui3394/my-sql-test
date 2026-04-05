# layer3_risk/formal_lattice.py
from enum import IntEnum
from dataclasses import dataclass
from typing import List

# ==========================================
# 形式化定义 1 & 2：源敏感度与三维信息流乘积格
# ==========================================

class SrcSensitivity(IntEnum):
    """ S_src: 源敏感度标签 (静态 Schema 注入) """
    PUBLIC = 0
    LOW = 1
    HIGH = 2
    SECRET = 3

class RetLattice(IntEnum):
    """ L_R: 机密保真度 (Confidentiality Retention) """
    NONE = 0
    LOW = 1
    PARTIAL = 2
    HIGH = 3
    FULL = 4

class ObsLattice(IntEnum):
    """ L_O: 可观察性 (Observability) """
    INTERNAL = 0    # 内部流转
    INFERRED = 1    # 谓词/侧信道推断 (WHERE/HAVING)
    EXPOSED = 2     # 直接投影暴露 (SELECT)

class ExpLattice(IntEnum):
    """ L_E: 可利用性/可枚举性 (Exploitability) """
    HARD = 0        # 强加密/加盐哈希
    MODERATE = 1    # 复杂组合
    TRIVIAL = 2     # 明文或弱哈希 (如 MD5, 极易枚举)

@dataclass
class SecurityState3D:
    """ 
    三维格状态向量 ell(v) \in L_R x L_O x L_E 
    满足偏序关系与最小上界 (LUB) 运算
    """
    src_sens: SrcSensitivity
    r_level: RetLattice
    o_level: ObsLattice
    e_level: ExpLattice

    def join(self, other: 'SecurityState3D') -> 'SecurityState3D':
        """ 
        最小上界操作 (Least Upper Bound, ⊔) 
        所有维度独立取最大值 (Point-wise Maximum)
        """
        return SecurityState3D(
            src_sens=max(self.src_sens, other.src_sens),
            r_level=max(self.r_level, other.r_level),
            o_level=max(self.o_level, other.o_level),
            e_level=max(self.e_level, other.e_level)
        )

def lattice_join(states: List[SecurityState3D]) -> SecurityState3D:
    """ 汇聚输入通道状态：R(v) = ⊔ { R(u_i) } """
    if not states:
        return SecurityState3D(SrcSensitivity.PUBLIC, RetLattice.NONE, ObsLattice.INTERNAL, ExpLattice.HARD)
    
    result = states[0]
    for s in states[1:]:
        result = result.join(s)
    return result