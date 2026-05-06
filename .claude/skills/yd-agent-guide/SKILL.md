---
name: yd-agent-guide
description: yd-agent的项目指南书，涉及到项目概述，要求，技术栈，架构设计等功能
---

## 项目概述
本项目是一个**面向私有化部署即时通讯（IM）软件的企业级 AI 助手系统**。主要功能包括：
- 多智能体协作：基于 LangGraph 构建 Supervisor + 4 类 Worker（检索、代码执行、IM 动作、总结）的解耦架构，支持并行调度、自我反思与纠错。
- GraphRAG 增强推理：融合知识图谱（实体-关系抽取）与向量检索，解决跨文档多跳推理问题（如“A项目依赖的B模块负责人是谁”）
- 长期记忆与用户画像：实现分级记忆管理（MemGPT 风格），跨会话记忆用户偏好与历史决策，自动复用模板生成周报等重复任务。
- 自评估与主动学习闭环：集成 LLM-as-Judge 实时评估回答质量，低分样本触发后台难例库积累与重排序模型增量训练。

目标场景：企业内部IM，用户通过 @机器人 形式提问，机器人可调用 IM API 完成操作。

## 要求（重点）
- 本项目以IM API的形式暴露，API的风格是RestFul风格
- 每添加一个API，需要创建test/api/xxx.py文件测试api
- 每测试完一个API，需要在根目录下创建api-doc.md文件编写api文档
- 每新增一个文件，需要在dir-structure.md文件补充目录结构树并说明文件的用处
- 重要的代码需要注释


## 技术栈

| 类别 | 技术选型 |
|------|----------|
| 语言 | Python 3.12+ |
| AI 编排 | LangGraph (状态机 + 多智能体) |
| LLM | qwen3.6-flash（阿里百炼https://dashscope.aliyuncs.com/compatible-mode/v1） |
| 嵌入模型 | text-embedding-v4 |
| 重排序模型| qwen3-vl-rerank |
| 向量数据库 | Chroma |
| 图数据库 | SQLite (邻接表 + 递归 CTE) (用于 GraphRAG) |
| 关系/缓存 | Redis (会话记忆 + 缓存) |
| 异步任务 |  后台线程+SQLite |
| Web 框架 | FastAPI (提供 IM webhook 接口) |
| 容器化 | Docker + Docker Compose (私有化一键部署) |
|评估框架|	RAGAS + 自定义 LLM Judge 忠实度、相关性、幻觉率自动评估|
| 单元测试与集成测试	| pytest + 模拟 IM API |

## 架构方案
|维度|方案|
| 架构模式| 多智能体协作（Supervisor + Worker）|
| 推理能力 | 反思（Reflection）+ 自我纠错 + 多步规划（Plan-and-Execute）|
| 记忆机制 |短期记忆（滑动窗口）+ 长期向量记忆（用户偏好/历史决议）|
| 知识检索 | 加入GraphRAG（知识图谱+向量检索联合推理） |
| 评估与监控| 集成RAGAS自动评估 + 对话追踪LangSmith + 未命中反馈闭环|

## 技术架构与实现
1. 多智能体编排
                ┌─────────────┐
                │  Supervisor │
                └──────┬──────┘
         ┌───────┬─────┴─────┬───────┐
         ▼       ▼           ▼       ▼
    ┌────────┐┌────────┐┌────────┐┌────────┐
    │Retrieval││  Code ││ Action ││Summary │
    │ Worker ││ Worker ││ Worker ││ Worker │
    └────────┘└────────┘└────────┘└────────┘
         │          │         │         │
         └──────────┴────┬────┴─────────┘
                         ▼
               ┌─────────────────┐
               │  Refiner (反思) │
               └─────────────────┘
- Supervisor：分析用户意图，分发给对应Worker（可并行调用多个Worker）
- Retrieval Worker：执行GraphRAG检索（见后）
- Code Worker：执行生成的Python代码（如数据分析、表格计算）
- Action Worker：调用IM API发送消息/创建待办/获取在线状态
- Summary Worker：汇总多Worker结果，生成最终回复
Refiner节点：对答案进行自我批评，如果质量低则重新路由到相应Worker重试（最多2次）

1. GraphRAG
- 从知识库文档提取实体和关系，构建小型知识图谱（使用llm_graph_transformer）
- 查询时同时执行：
   向量检索（Top-10 chunks）
   图谱检索（提取子图并转换为文本表示）
- 用图注意力机制对两类结果加权融合，输入LLM
- 可处理“A部门和B部门的KPI对比逻辑是什么”这类需多跳推理的问题

1. 长期记忆与用户画像
- 每个用户长期保存：历史提问偏好、常见决策、之前自动生成的报告模板
- 使用MemGPT风格的分级记忆管理：核心记忆（永久）+ 工作记忆（24小时滑动）
- 示例：第二次问“帮我写周报”，自动根据上次的格式 + 本次知识库更新内容生成
  
1. 自我评估与主动学习
- 每次回答后，后台异步用LLM-as-Judge评估忠实度、相关性、完整性
- 低于阈值时，自动触发：
   记录到“未命中案例库”
   隔天后台尝试用更强模型（如GPT-4o）生成正确答案并纳入长期记忆
- 提供简单的人工反馈接口（👍👎），用于微调重排序模型权重


## 代码编写要求
- 提供llmfactory，构建llm采用langchain的init_chat_model方法