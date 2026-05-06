# yd-Agent API 文档

## 版本
v0.1.0

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
    "max_refinements": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息，不能为空 |
| session_id | string \| null | 否 | 会话 ID，用于后续记忆功能 |
| max_refinements | int | 否 | 最大反思次数，默认 2，范围 0-5 |

### 响应
```json
{
    "answer": "你好！有什么我可以帮你的吗？",
    "reasoning": "用户简单问候，直接由 summary Worker 回答",
    "workers_used": ["summary"],
    "worker_results": [],
    "refinements": 0,
    "session_id": null
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
