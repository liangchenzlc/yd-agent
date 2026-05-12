# yd-Agent CLI 指令清单

## 基础信息

- 入口命令：`yd-agent`
- 本地脚本运行：`python yd-agent ...`
- Web 服务启动：`uvicorn app.web.main:app --reload`
- 默认输出：Rich 美化的人类可读文本
- 结构化输出：`chat --json` 输出 JSON；`chat --stream --json` 输出 JSON Lines
- 字符编码：UTF-8

## 全局命令

```bash
yd-agent doctor
```

用途：检查 CLI 运行环境，输出 storage、LLM 模型、Embedding 模型等关键配置。

## Web 企业知识问答

```bash
uvicorn app.web.main:app --reload
```

用途：启动 FastAPI API 服务。后端只提供接口，用户端页面由 `front/` Vite React 应用提供，管理端页面由 `admin/` Vite React 应用承载。

默认访问地址：

```text
http://127.0.0.1:8000/docs
```

默认账号：

```text
admin / admin
```

用户端前端：

```bash
cd front
npm install
npm run dev
```

访问地址：`http://127.0.0.1:5173`

管理端前端：

```bash
cd admin
npm install
npm run dev
```

访问地址：`http://127.0.0.1:5174`

## 对话

### 单轮对话

```bash
yd-agent chat "你好"
```

完整形式：

```bash
yd-agent chat "你好" --user-id user1 --session-id session1
```

可选参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `message` | 用户消息；非交互模式必填 | 空 |
| `--user-id` | 用户标识 | `default` |
| `--session-id` | 会话 ID，用于输出标识和记忆归属 | 空 |
| `--json` | 输出结构化 JSON | 关闭 |
| `--stream` | 流式输出执行进度 | 关闭 |

JSON 输出：

```bash
yd-agent chat "你好" --user-id user1 --session-id session1 --json
```

### 流式对话

```bash
yd-agent chat "总结知识库内容" --stream --user-id user1
```

JSON Lines 流式输出：

```bash
yd-agent chat "总结知识库内容" --stream --json
```

### 连续对话界面

```bash
yd-agent chat --interactive
```

简写：

```bash
yd-agent chat -i
```

带初始消息：

```bash
yd-agent chat --interactive "你好"
```

可选参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `message` | 进入连续对话前先发送的一条消息 | 空 |
| `--user-id` | 用户标识 | `default` |
| `--session-id` | 会话 ID；不传时使用 `main`，并写入本轮记忆归属 | 空 |
| `-i`, `--interactive` | 进入连续对话界面 | 关闭 |

交互模式内置命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示交互模式命令 |
| `/clear` | 清空当前进程内的对话上下文 |
| `/exit` | 退出连续对话 |
| `/quit` | 退出连续对话 |
| `exit` | 退出连续对话 |
| `quit` | 退出连续对话 |

限制：交互模式暂不支持 `--json`。

## 文档管理

### 摄入文档

```bash
yd-agent documents ingest docs/example.md
```

指定文档 ID：

```bash
yd-agent documents ingest docs/example.md --id example
```

参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `path` | 文档路径 | 必填 |
| `--id` | 文档 ID；不传时根据文件内容生成 | 空 |

说明：

- Embedding 请求会按 `EMBEDDING_BATCH_SIZE` 分批，默认每批 10 条。
- 摄入写入阶段失败时会回滚已写入的 chunk、实体、关系和文档元数据，避免留下半成品文档。
- 如果路径不存在，CLI 会提示相近的本地路径。

### 列出文档

```bash
yd-agent documents list
```

### 查看文档统计

```bash
yd-agent documents stats
```

### 删除文档

```bash
yd-agent documents delete example --yes
```

参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `doc_id` | 文档 ID | 必填 |
| `--yes` | 确认删除；缺少时命令不会执行删除 | 关闭 |

## 记忆管理

### 查看用户记忆

```bash
yd-agent memory list --user-id user1
```

参数：

| 参数 | 说明 |
|------|------|
| `--user-id` | 用户标识，必填 |

### 清理用户记忆

```bash
yd-agent memory clear --user-id user1 --yes
```

参数：

| 参数 | 说明 |
|------|------|
| `--user-id` | 用户标识，必填 |
| `--yes` | 确认清理；缺少时命令不会执行清理 |

## 用户画像

### 查看用户画像

```bash
yd-agent profile show --user-id user1
```

参数：

| 参数 | 说明 |
|------|------|
| `--user-id` | 用户标识，必填 |

## 评估记录

### 查看评估摘要

```bash
yd-agent eval summary
```

### 查看评估运行记录

```bash
yd-agent eval runs
```

带分页和分数过滤：

```bash
yd-agent eval runs --limit 20 --offset 0 --min-score 0 --max-score 10
```

参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--limit` | 返回数量 | `50` |
| `--offset` | 偏移量 | `0` |
| `--min-score` | 最低评分 | `0` |
| `--max-score` | 最高评分 | `10` |

### 查看难例

```bash
yd-agent eval hard-cases
```

按 review 状态过滤：

```bash
yd-agent eval hard-cases --reviewed all --limit 20 --offset 0
```

参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--reviewed` | 过滤 review 状态，可选 `true`、`false`、`all` | `all` |
| `--limit` | 返回数量 | `50` |
| `--offset` | 偏移量 | `0` |

## 当前完整命令速查

```bash
yd-agent doctor
yd-agent chat "消息"
yd-agent chat "消息" --json
yd-agent chat "消息" --stream
yd-agent chat "消息" --stream --json
yd-agent chat --interactive
yd-agent chat -i
yd-agent chat --interactive "消息"
yd-agent documents ingest <path>
yd-agent documents ingest <path> --id <doc_id>
yd-agent documents list
yd-agent documents stats
yd-agent documents delete <doc_id> --yes
yd-agent memory list --user-id <user_id>
yd-agent memory clear --user-id <user_id> --yes
yd-agent profile show --user-id <user_id>
yd-agent eval summary
yd-agent eval runs
yd-agent eval runs --limit <n> --offset <n> --min-score <n> --max-score <n>
yd-agent eval hard-cases
yd-agent eval hard-cases --reviewed <true|false|all> --limit <n> --offset <n>
```

## 退出码

| 退出码 | 说明 |
|--------|------|
| `0` | 成功 |
| `1` | 运行时错误 |
| `2` | 参数错误或缺少破坏性操作确认 |
