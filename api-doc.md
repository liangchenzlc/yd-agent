# yd-Agent API 文档

## 版本
v0.3.0

## 基础信息
- 协议：HTTP/1.1
- 格式：JSON（请求/响应 body）
- 字符编码：UTF-8

---

## GET /health

健康检查接口。

### 请求
```
GET /health
```

### 响应
```json
{
    "status": "ok",
    "version": "0.1.0",
    "llm_model": "qwen3.6-flash"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 服务状态，正常为 "ok" |
| version | string | 服务版本号 |
| llm_model | string | 当前使用的 LLM 模型 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |

---

## POST /chat

对话接口（非流式）。向多智能体系统发送消息，返回最终回答。

### 请求
```
POST /chat
Content-Type: application/json
```

```json
{
    "message": "你好",
    "session_id": null,
    "user_id": "default",
    "max_refinements": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息，不能为空 |
| session_id | string \| null | 否 | 会话 ID，用于后续记忆功能 |
| user_id | string | 否 | 用户标识，默认 "default"，用于跨会话记忆 |
| max_refinements | int | 否 | 最大反思次数，默认 2，范围 0-5 |

### 响应
```json
{
    "answer": "你好！有什么我可以帮你的吗？",
    "reasoning": "用户简单问候，直接由 summary Worker 回答",
    "workers_used": ["summary"],
    "worker_results": [],
    "refinements": 0,
    "session_id": null,
    "memories_updated": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| answer | string | 最终回答 |
| reasoning | string | Supervisor 的调度理由 |
| workers_used | string[] | 被调用的 Worker 列表 |
| worker_results | object[] | 各 Worker 的执行结果详情 |
| worker_results[].worker | string | Worker 名称 |
| worker_results[].content | string | Worker 输出内容 |
| worker_results[].error | string \| null | 错误信息（无错误时为 null） |
| worker_results[].metadata | object | 额外元数据 |
| refinements | int | 实际反思重试次数 |
| session_id | string \| null | 会话 ID |
| memories_updated | bool | 本次对话是否提取并存储了新的长期记忆 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 422 | 请求参数校验失败（如 message 为空） |
| 500 | 服务内部错误（如 LLM 调用失败） |

---

## POST /chat/stream

对话接口（SSE 流式）。与 `/chat` 相同功能，但通过 Server-Sent Events 实时推送处理进度。

### 请求
```
POST /chat/stream
Content-Type: application/json
```

请求体与 `POST /chat` 相同。

### 响应
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

### SSE 事件类型

| 事件类型 | 数据字段 | 说明 |
|----------|----------|------|
| supervisor | reasoning, workers | Supervisor 完成调度决策 |
| worker_start | worker | Worker 开始执行 |
| worker_end | worker, result | Worker 执行完成，包含结果和错误信息 |
| summary_chunk | content | 最终回答内容 |
| refiner | score, passed | Refiner 评估结果 |
| done | answer, workers_used, refinements | 处理完成 |
| error | detail | 发生错误 |

### 示例流
```
data: {"type": "supervisor", "reasoning": "用户简单问候", "workers": ["summary"]}

data: {"type": "worker_start", "worker": "summary"}

data: {"type": "worker_end", "worker": "summary", "result": {"content": "你好！"}}

data: {"type": "summary_chunk", "content": "你好！有什么可以帮你的？"}

data: {"type": "refiner", "score": 7, "passed": true}

data: {"type": "done", "answer": "你好！", "workers_used": ["summary"], "refinements": 0, "session_id": null}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功（SSE 流开始） |
| 422 | 请求参数校验失败 |

---

## POST /documents/ingest

文档摄入接口。将文档分块、抽取实体关系、向量嵌入并存储到知识库。供 GraphRAG 检索使用。

### 请求
```
POST /documents/ingest
Content-Type: application/json
```

```json
{
    "documents": [
        {
            "id": "doc1",
            "content": "人工智能是计算机科学的一个分支...",
            "metadata": {"source": "wiki"}
        }
    ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| documents | object[] | 是 | 待摄入的文档列表，至少 1 个 |
| documents[].id | string | 否 | 文档 ID，不传则自动生成 |
| documents[].content | string | 是 | 文档正文内容 |
| documents[].metadata | object | 否 | 附加元数据 |

### 响应
```json
{
    "ingested": 1,
    "skipped": 1,
    "total_chunks": 42,
    "total_entities": 15,
    "total_relationships": 8
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| ingested | int | 成功摄入的文档数 |
| skipped | int | 跳过的重复文档数 |
| total_chunks | int | 总文本块数 |
| total_entities | int | 总实体数 |
| total_relationships | int | 总关系数 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 422 | 请求参数校验失败 |
| 503 | 存储管理器未初始化 |

---

## GET /documents/stats

获取文档库统计信息。

### 请求
```
GET /documents/stats
```

### 响应
```json
{
    "total_documents": 5,
    "total_chunks": 120,
    "total_entities": 45,
    "total_relationships": 30
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total_documents | int | 文档总数 |
| total_chunks | int | 文本块总数 |
| total_entities | int | 实体总数 |
| total_relationships | int | 关系总数 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 存储管理器未初始化 |

---

## GET /documents

列出所有已摄入的文档。

### 请求
```
GET /documents
```

### 响应
```json
{
    "documents": [
        {"id": "doc1", "chunks": 12, "entities": 5},
        {"id": "doc2", "chunks": 8, "entities": 3}
    ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| documents | object[] | 文档列表 |
| documents[].id | string | 文档 ID |
| documents[].chunks | int | 文档块数 |
| documents[].entities | int | 实体数 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 存储管理器未初始化 |

---

## GET /memory/{user_id}

获取指定用户的长期记忆（核心记忆 + 工作记忆）。

### 请求
```
GET /memory/{user_id}
```

### 响应
```json
{
    "user_id": "user1",
    "core_memories": [
        {
            "id": "user1_session1_0",
            "type": "fact",
            "content": "用户是 Python 后端工程师",
            "importance": 0.9,
            "timestamp": "2026-05-06T10:00:00+00:00"
        }
    ],
    "working_memories": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户标识 |
| core_memories | object[] | 核心记忆列表（永久保留） |
| core_memories[].id | string | 记忆 ID |
| core_memories[].type | string | 记忆类型：fact / preference / pattern / template |
| core_memories[].content | string | 记忆内容 |
| core_memories[].importance | float | 重要性分数（0-1） |
| core_memories[].timestamp | string | 创建时间 |
| working_memories | object[] | 工作记忆列表（24h 滑动窗口） |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 记忆服务未就绪 |

---

## DELETE /memory/{user_id}

删除指定用户的所有记忆和画像。

### 请求
```
DELETE /memory/{user_id}
```

### 响应
```json
{
    "deleted": true,
    "user_id": "user1"
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 记忆服务未就绪 |

---

## GET /profile/{user_id}

获取指定用户的画像信息。

### 请求
```
GET /profile/{user_id}
```

### 响应
```json
{
    "user_id": "user1",
    "topics": {"Python": 5, "Go": 3},
    "total_interactions": 12,
    "last_active": "2026-05-06T12:00:00+00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户标识 |
| topics | object | 话题频次统计（话题名 → 提及次数） |
| total_interactions | int | 总交互次数 |
| last_active | string | 最近活跃时间（ISO 8601） |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 记忆服务未就绪 |

---

## DELETE /documents/{doc_id}

删除指定文档及其关联数据。

### 请求
```
DELETE /documents/{doc_id}
```

### 响应
```json
{
    "deleted": true
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 存储管理器未初始化 |

---

## GET /eval/summary

获取评估系统整体统计信息，包括评分分布、通过率、难例数量和近20次平均分。

### 请求
```
GET /eval/summary
```

### 响应
```json
{
    "total_eval_runs": 42,
    "total_hard_cases": 3,
    "total_feedback": 10,
    "avg_score": 7.5,
    "pass_rate": 0.85,
    "score_distribution": {
        "0-3": 2,
        "4-6": 5,
        "7-8": 20,
        "9-10": 15
    },
    "recent_avg_score": 7.8
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total_eval_runs | int | 评估运行总数 |
| total_hard_cases | int | 难例总数 |
| total_feedback | int | 用户反馈总数 |
| avg_score | float | 整体平均分（0-10） |
| pass_rate | float | 通过率（≥6分占比） |
| score_distribution | object | 分数段分布（0-3/4-6/7-8/9-10） |
| recent_avg_score | float | 近20次评估平均分 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## GET /eval/runs

获取评估运行记录列表，支持分页和分数过滤。

### 请求
```
GET /eval/runs?limit=50&offset=0&min_score=0&max_score=10
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | int | 否 | 50 | 每页数量（1-500） |
| offset | int | 否 | 0 | 偏移量 |
| min_score | int | 否 | 0 | 最低分过滤（0-10） |
| max_score | int | 否 | 10 | 最高分过滤（0-10） |

### 响应
```json
{
    "runs": [
        {
            "run_id": "u1_abc123",
            "user_id": "u1",
            "session_id": "s1",
            "message": "你好",
            "answer": "你好！有什么可以帮助你的？",
            "worker_results": [],
            "refinements": 0,
            "overall_score": 8,
            "dimensions": [
                {"name": "faithfulness", "score": 8, "passed": true, "feedback": ""},
                {"name": "relevance", "score": 7, "passed": true, "feedback": ""},
                {"name": "completeness", "score": 9, "passed": true, "feedback": ""}
            ],
            "is_hard_case": false,
            "timestamp": "2026-05-06T10:00:00+00:00"
        }
    ],
    "total": 42
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## GET /eval/runs/{run_id}

获取单个评估运行记录的详情。

### 请求
```
GET /eval/runs/u1_abc123
```

### 响应
返回单个 `EvalRunItem` 对象（结构同列表项）。

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 404 | 评估记录不存在 |
| 503 | 评估服务未就绪 |

---

## DELETE /eval/runs

清空所有评估运行记录并重置统计。

### 请求
```
DELETE /eval/runs
```

### 响应
```json
{
    "deleted": true,
    "count": 42
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## GET /eval/hard-cases

获取难例列表，支持按审核状态过滤。

### 请求
```
GET /eval/hard-cases?reviewed=false&limit=50&offset=0
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| reviewed | bool \| null | 否 | null | 审核状态过滤：true=已审核，false=未审核，不传=全部 |
| limit | int | 否 | 50 | 每页数量（1-500） |
| offset | int | 否 | 0 | 偏移量 |

### 响应
```json
{
    "cases": [
        {
            "case_id": "u1_def456",
            "user_id": "u1",
            "message": "复杂的数学问题",
            "original_answer": "不太准确的回答...",
            "golden_answer": "正确的金标答案...",
            "score": 3,
            "timestamp": "2026-05-06T11:00:00+00:00",
            "reviewed": false
        }
    ],
    "total": 3
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## GET /eval/hard-cases/{case_id}

获取单个难例详情。

### 请求
```
GET /eval/hard-cases/u1_def456
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 404 | 难例不存在 |
| 503 | 评估服务未就绪 |

---

## PATCH /eval/hard-cases/{case_id}/review

标记难例为已审核。

### 请求
```
PATCH /eval/hard-cases/u1_def456/review
```

### 响应
返回更新后的 `HardCaseItem` 对象（`reviewed` 字段变为 `true`）。

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 404 | 难例不存在 |
| 503 | 评估服务未就绪 |

---

## DELETE /eval/hard-cases

清空所有难例。

### 请求
```
DELETE /eval/hard-cases
```

### 响应
```json
{
    "deleted": true,
    "count": 3
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## POST /feedback

提交用户反馈（👍/👎）。

### 请求
```
POST /feedback
Content-Type: application/json
```

```json
{
    "user_id": "u1",
    "session_id": "s1",
    "thumbs_up": true,
    "comment": "回答准确有帮助",
    "message": "你好",
    "answer": "你好！有什么可以帮助你的？"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户标识 |
| session_id | string \| null | 否 | 会话 ID |
| thumbs_up | bool | 是 | true=👍，false=👎 |
| comment | string | 否 | 附加评论 |
| message | string | 是 | 对应的用户消息 |
| answer | string | 是 | 对应的系统回答 |

### 响应
```json
{
    "feedback_id": "u1_ghi789",
    "user_id": "u1",
    "session_id": "s1",
    "thumbs_up": true,
    "comment": "回答准确有帮助",
    "message": "你好",
    "answer": "你好！有什么可以帮助你的？",
    "timestamp": "2026-05-06T12:00:00+00:00"
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 422 | 请求参数校验失败 |
| 503 | 评估服务未就绪 |

---

## GET /feedback

获取反馈列表，支持按用户过滤。

### 请求
```
GET /feedback?user_id=u1&limit=50&offset=0
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| user_id | string \| null | 否 | null | 按用户过滤，不传返回全部 |
| limit | int | 否 | 50 | 每页数量（1-500） |
| offset | int | 否 | 0 | 偏移量 |

### 响应
```json
{
    "feedback": [
        {
            "feedback_id": "u1_ghi789",
            "user_id": "u1",
            "session_id": "s1",
            "thumbs_up": true,
            "comment": "回答准确有帮助",
            "message": "你好",
            "answer": "你好！",
            "timestamp": "2026-05-06T12:00:00+00:00"
        }
    ],
    "total": 1,
    "thumbs_up_count": 1,
    "thumbs_down_count": 0
}
```

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |

---

## GET /feedback/stats

获取反馈统计数据。

### 请求
```
GET /feedback/stats
```

### 响应
```json
{
    "thumbs_up": 8,
    "thumbs_down": 2,
    "total": 10
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| thumbs_up | int | 👍 数量 |
| thumbs_down | int | 👎 数量 |
| total | int | 反馈总数 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 503 | 评估服务未就绪 |
