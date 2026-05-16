"""所有 Worker 节点的统一导出入口。

graph.py 通过此模块引用节点函数，避免直接导入各节点的内部细节。
同时作为模块间依赖关系的显式文档 —— 新增 Worker 节点必须在此注册，
否则 graph.py 无法发现。

Worker 节点分类：
  - load_memory / save_memory  : 记忆读写（依赖 MemoryManager）
  - supervisor                  : 任务分解与分发
  - retrieval_worker            : 知识库检索（依赖 StorageManager）
  - docs_worker                 : 文档处理
  - data_analyst_worker         : 数据分析 + 图表
  - summary_worker              : 回答汇总
  - refiner                     : 质量反思与改进
"""

from app.agent.nodes.supervisor import supervisor_node
from app.agent.nodes.retrieval_worker import retrieval_worker_node
from app.agent.nodes.docs_worker import docs_worker_node
from app.agent.nodes.data_analyst_worker import data_analyst_worker_node
from app.agent.nodes.summary_worker import summary_worker_node
from app.agent.nodes.refiner import refiner_node
from app.agent.nodes.load_memory import load_memory_node
from app.agent.nodes.save_memory import save_memory_node

__all__ = [
    "supervisor_node",
    "retrieval_worker_node",
    "docs_worker_node",
    "data_analyst_worker_node",
    "summary_worker_node",
    "refiner_node",
    "load_memory_node",
    "save_memory_node",
]
