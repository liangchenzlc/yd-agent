# yd-Agent CLI 文档

## 版本

v0.4.0

## 基础信息

- 入口命令：`yd-agent`
- 默认输出：rich 美化的人类可读文本
- 结构化输出：支持 `--json` 的命令输出 JSON；流式 chat 输出 JSON Lines
- 字符编码：UTF-8

## 安装

```bash
pip install -r requirements.txt
```

确保项目根目录在 `PATH` 中，或将根目录下的 `yd-agent` 脚本复制到虚拟环境的可执行目录。

## 环境检查

```bash
yd-agent doctor
```

输出当前 storage、LLM 模型、Embedding 模型等关键配置。

## 对话

### 非流式对话

```bash
yd-agent chat "你好" --user-id user1 --session-id session1
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--user-id` | 用户标识，默认 `default` |
| `--session-id` | 会话 ID，可选 |
| `--json` | 输出结构化 JSON |

JSON 输出示例：

```json
{
  "answer": "你好！有什么我可以帮你的吗？",
  "reasoning": "用户简单问候",
  "workers_used": ["summary"],
  "worker_results": [],
  "refinements": 0,
  "session_id": "session1",
  "memories_updated": false
}
```

### 流式对话

```bash
yd-agent chat --stream "总结这份文档" --user-id user1
```

结构化流式输出：

```bash
yd-agent chat --stream "总结这份文档" --json
```

## 文档管理

### 摄入文档

```bash
yd-agent documents ingest docs/example.md --id example
```

`--id` 可选；不传时根据文件内容自动生成短 ID。

### 查看文档列表

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

删除命令必须传 `--yes`。

## 记忆与画像

### 查看用户记忆

```bash
yd-agent memory list --user-id user1
```

### 清理用户记忆

```bash
yd-agent memory clear --user-id user1 --yes
```

清理命令必须传 `--yes`。

### 查看用户画像

```bash
yd-agent profile show --user-id user1
```

## 评估记录

### 摘要

```bash
yd-agent eval summary
```

### 运行记录

```bash
yd-agent eval runs --limit 20 --offset 0 --min-score 0 --max-score 10
```

### 难例

```bash
yd-agent eval hard-cases --reviewed all
```

`--reviewed` 可选值：`all`、`true`、`false`。

## 本轮不迁移的能力

原 HTTP `/feedback` 相关提交和查询能力本轮不迁移到 CLI。

## 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 运行时错误 |
| 2 | 参数错误或缺少破坏性操作确认 |
