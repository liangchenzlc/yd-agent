from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from app.agent.ingestion.chunker import chunk_text
from app.agent.ingestion.extractor import extract_entities
from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.agent.state import AgentState
from app.config.settings import get_settings
from app.runtime import AgentRuntime
from app.services.documents import delete_document, document_stats, ingest_document, list_documents

console = Console()
APP_VERSION = "dev"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yd-agent", description="yd-Agent 命令行助手")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="向 yd-Agent 提问")
    chat_parser.add_argument("message", nargs="?", default="", help="用户消息")
    chat_parser.add_argument("--user-id", default="default", help="用户标识")
    chat_parser.add_argument("--session-id", default=None, help="会话 ID")
    chat_parser.add_argument("--stream", action="store_true", help="流式输出执行进度")
    chat_parser.add_argument("--json", action="store_true", help="输出 JSON 或 JSON Lines")
    chat_parser.add_argument("-i", "--interactive", action="store_true", help="进入连续对话界面")

    documents_parser = subparsers.add_parser("documents", help="管理 GraphRAG 文档")
    document_subparsers = documents_parser.add_subparsers(dest="document_command", required=True)

    ingest_parser = document_subparsers.add_parser("ingest", help="摄入本地文本文件")
    ingest_parser.add_argument("path", help="文档路径")
    ingest_parser.add_argument("--id", default="", help="文档 ID，默认由内容生成")

    document_subparsers.add_parser("list", help="列出已摄入文档")
    document_subparsers.add_parser("stats", help="查看文档统计")

    delete_parser = document_subparsers.add_parser("delete", help="删除文档")
    delete_parser.add_argument("doc_id", help="文档 ID")
    delete_parser.add_argument("--yes", action="store_true", help="确认删除")

    memory_parser = subparsers.add_parser("memory", help="管理用户记忆")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_list_parser = memory_subparsers.add_parser("list", help="列出用户记忆")
    memory_list_parser.add_argument("--user-id", required=True, help="用户标识")
    memory_clear_parser = memory_subparsers.add_parser("clear", help="清理用户记忆")
    memory_clear_parser.add_argument("--user-id", required=True, help="用户标识")
    memory_clear_parser.add_argument("--yes", action="store_true", help="确认清理")

    profile_parser = subparsers.add_parser("profile", help="查看用户画像")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_show_parser = profile_subparsers.add_parser("show", help="显示用户画像")
    profile_show_parser.add_argument("--user-id", required=True, help="用户标识")

    eval_parser = subparsers.add_parser("eval", help="查看评估记录")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_subparsers.add_parser("summary", help="显示评估摘要")
    eval_runs_parser = eval_subparsers.add_parser("runs", help="列出评估运行记录")
    eval_runs_parser.add_argument("--limit", type=int, default=50)
    eval_runs_parser.add_argument("--offset", type=int, default=0)
    eval_runs_parser.add_argument("--min-score", type=int, default=0)
    eval_runs_parser.add_argument("--max-score", type=int, default=10)
    hard_cases_parser = eval_subparsers.add_parser("hard-cases", help="列出难例")
    hard_cases_parser.add_argument("--reviewed", choices=["true", "false", "all"], default="all")
    hard_cases_parser.add_argument("--limit", type=int, default=50)
    hard_cases_parser.add_argument("--offset", type=int, default=0)

    subparsers.add_parser("doctor", help="检查 CLI 运行环境")
    return parser


def _initial_state(message: str, user_id: str, session_id: str | None = None) -> AgentState:
    return _state_from_messages([HumanMessage(content=message)], user_id, session_id or "main")


def _state_from_messages(messages: list[BaseMessage], user_id: str, session_id: str = "main") -> AgentState:
    return AgentState(
        messages=list(messages),
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=user_id,
        session_id=session_id,
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )


def _response_payload(result: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    return {
        "answer": result.get("final_answer", ""),
        "reasoning": result.get("dispatch_reasoning", ""),
        "workers_used": result.get("worker_assignments", []),
        "worker_results": result.get("worker_results", []),
        "refinements": result.get("refinement_count", 0),
        "session_id": session_id,
        "memories_updated": result.get("memories_updated", False),
    }


async def _run_chat(args: argparse.Namespace) -> int:
    if args.interactive:
        if args.json:
            console.print("[red]交互模式暂不支持 --json 输出[/red]")
            return 2
        return await _run_interactive_chat(args)

    if not args.message.strip():
        console.print("[red]消息不能为空[/red]")
        return 2

    async with AgentRuntime() as runtime:
        state = _initial_state(args.message, args.user_id, args.session_id or "main")
        if args.stream:
            return await _run_stream_chat(runtime.graph, state, args)

        result = await runtime.graph.ainvoke(state)

    payload = _response_payload(result, args.session_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    console.print(Panel(Markdown(payload["answer"] or "（无回答）"), title="yd-Agent"))
    console.print(f"Workers: {', '.join(payload['workers_used']) or 'none'}")
    if payload["refinements"]:
        console.print(f"Refinements: {payload['refinements']}")
    return 0


async def _run_interactive_chat(args: argparse.Namespace) -> int:
    session_id = args.session_id or "main"
    messages: list[BaseMessage] = []
    if args.message.strip():
        messages.append(HumanMessage(content=args.message.strip()))

    _print_chat_header(args.user_id, session_id)
    console.print("[dim]输入 /help 查看命令，/exit 退出。[/dim]")

    async with AgentRuntime() as runtime:
        if messages:
            await _run_interactive_turn(runtime.graph, messages, args.user_id, session_id)

        while True:
            try:
                user_input = console.input("[bold yellow]you > [/bold yellow]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 0

            if not user_input:
                continue

            command = user_input.lower()
            if command in {"/exit", "/quit", "exit", "quit"}:
                console.print("[dim]会话已结束。[/dim]")
                return 0
            if command == "/clear":
                messages.clear()
                console.rule("[dim]session cleared[/dim]")
                continue
            if command == "/help":
                _print_interactive_help()
                continue

            messages.append(HumanMessage(content=user_input))
            await _run_interactive_turn(runtime.graph, messages, args.user_id, session_id)


async def _run_interactive_turn(
    graph: Any,
    messages: list[BaseMessage],
    user_id: str,
    session_id: str,
) -> None:
    state = _state_from_messages(messages, user_id, session_id)
    with console.status("[bold cyan]agent running...[/bold cyan]", spinner="dots"):
        result = await graph.ainvoke(state)

    payload = _response_payload(result, session_id)
    workers = ", ".join(payload["workers_used"]) or "none"
    reasoning = payload["reasoning"] or "no reasoning"
    console.print(f"[dim]supervisor -> {workers} | {reasoning}[/dim]")
    console.print(Panel(Markdown(payload["answer"] or "（无回答）"), title="assistant", border_style="cyan"))
    if payload["refinements"]:
        console.print(f"[dim]refinements: {payload['refinements']}[/dim]")
    messages.append(AIMessage(content=payload["answer"] or ""))


def _print_chat_header(user_id: str, session_id: str) -> None:
    title = Text()
    title.append("yd-Agent ", style="bold red")
    title.append(APP_VERSION, style="bold")
    title.append(" - local multi-agent assistant", style="red")
    console.print(title)
    console.print(
        f"[bold yellow]yd-agent chat[/bold yellow] - agent main - session {session_id}"
    )
    console.print(
        f"[dim]user {user_id} | workers supervisor/retrieval/code/docs/summary | status idle[/dim]"
    )
    console.rule(style="dim")


def _print_interactive_help() -> None:
    table = Table(title="Interactive commands")
    table.add_column("command")
    table.add_column("description")
    table.add_row("/help", "显示命令")
    table.add_row("/clear", "清空当前进程内的对话上下文")
    table.add_row("/exit", "退出连续对话")
    console.print(table)


async def _run_stream_chat(graph: Any, state: AgentState, args: argparse.Namespace) -> int:
    final_answer = ""
    workers_used: list[str] = []
    refinement_count = 0

    async for chunk in graph.astream(state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if node_name == "supervisor":
                workers_used = node_output.get("worker_assignments", [])
                event = {
                    "type": "supervisor",
                    "reasoning": node_output.get("dispatch_reasoning", ""),
                    "workers": workers_used,
                }
            elif node_name == "summary_worker":
                final_answer = node_output.get("final_answer", final_answer)
                event = {"type": "summary", "content": final_answer}
            elif node_name == "refiner":
                refinement_count = node_output.get("refinement_count", refinement_count)
                event = {
                    "type": "refiner",
                    "passed": not node_output.get("refinement_needed", False),
                    "refinements": refinement_count,
                }
            else:
                event = {"type": "worker", "worker": node_name}

            if args.json:
                print(json.dumps(event, ensure_ascii=False))
            else:
                console.print(f"[{event['type']}] {event}")

    done = {"type": "done", "workers_used": workers_used, "refinements": refinement_count, "session_id": args.session_id}
    if args.json:
        print(json.dumps(done, ensure_ascii=False))
    else:
        if final_answer:
            console.print(Panel(Markdown(final_answer), title="yd-Agent"))
        console.print(f"Workers: {', '.join(workers_used) or 'none'}")
    return 0


async def _run_memory(args: argparse.Namespace) -> int:
    async with AgentRuntime() as runtime:
        if args.memory_command == "list":
            return _memory_list(runtime.memory_manager, args.user_id)
        if args.memory_command == "clear":
            return await _memory_clear(runtime.memory_manager, args)
    return 2


def _memory_list(memory_manager: Any, user_id: str) -> int:
    table = Table(title=f"Memories: {user_id}")
    table.add_column("scope")
    table.add_column("id")
    table.add_column("type")
    table.add_column("importance")
    table.add_column("content")

    for mem_id, meta in memory_manager.core_memory_vdb._id_to_meta.items():
        if meta.get("metadata", {}).get("user_id") == user_id:
            table.add_row("core", mem_id, meta.get("metadata", {}).get("type", ""), str(meta.get("metadata", {}).get("importance", 0.0)), meta.get("text", ""))
    for mem_id, meta in memory_manager.working_memory_vdb._id_to_meta.items():
        if meta.get("metadata", {}).get("user_id") == user_id:
            table.add_row("working", mem_id, meta.get("metadata", {}).get("type", ""), str(meta.get("metadata", {}).get("importance", 0.0)), meta.get("text", ""))

    console.print(table)
    return 0


async def _memory_clear(memory_manager: Any, args: argparse.Namespace) -> int:
    if not args.yes:
        console.print("[red]清理记忆需要 --yes 确认[/red]")
        return 2
    await memory_manager.forget_user(args.user_id)
    _print_mapping("Memory clear", {"deleted": True, "user_id": args.user_id})
    return 0


async def _run_profile(args: argparse.Namespace) -> int:
    async with AgentRuntime() as runtime:
        profile = await runtime.memory_manager.get_user_profile(args.user_id)
    _print_mapping(
        "Profile",
        {
            "user_id": args.user_id,
            "topics": profile.get("topics", {}),
            "total_interactions": profile.get("total_interactions", 0),
            "last_active": profile.get("last_active", ""),
        },
    )
    return 0


async def _run_eval(args: argparse.Namespace) -> int:
    async with AgentRuntime() as runtime:
        if args.eval_command == "summary":
            summary = await runtime.eval_manager.get_eval_summary()
            _print_mapping("Eval summary", summary)
            return 0
        if args.eval_command == "runs":
            runs = await runtime.eval_manager.list_eval_runs(
                limit=args.limit,
                offset=args.offset,
                min_score=args.min_score,
                max_score=args.max_score,
            )
            total = await runtime.eval_manager.count_eval_runs(min_score=args.min_score, max_score=args.max_score)
            _print_eval_runs(runs, total)
            return 0
        if args.eval_command == "hard-cases":
            reviewed = None if args.reviewed == "all" else args.reviewed == "true"
            cases = await runtime.eval_manager.list_hard_cases(reviewed=reviewed, limit=args.limit, offset=args.offset)
            total = await runtime.eval_manager.count_hard_cases(reviewed=reviewed)
            _print_hard_cases(cases, total)
            return 0
    return 2


def _print_eval_runs(runs: list[dict[str, Any]], total: int) -> None:
    table = Table(title=f"Eval runs ({total})")
    table.add_column("run_id")
    table.add_column("user_id")
    table.add_column("score")
    table.add_column("message")
    table.add_column("timestamp")
    for run in runs:
        table.add_row(run.get("run_id", ""), run.get("user_id", ""), str(run.get("overall_score", 0)), run.get("message", ""), run.get("timestamp", ""))
    console.print(table)


def _print_hard_cases(cases: list[dict[str, Any]], total: int) -> None:
    table = Table(title=f"Hard cases ({total})")
    table.add_column("case_id")
    table.add_column("user_id")
    table.add_column("score")
    table.add_column("reviewed")
    table.add_column("message")
    for case in cases:
        table.add_row(case.get("case_id", ""), case.get("user_id", ""), str(case.get("score", 0)), str(case.get("reviewed", False)), case.get("message", ""))
    console.print(table)


async def _run_documents(args: argparse.Namespace) -> int:
    if args.document_command == "ingest":
        path_error = _document_ingest_path_error(Path(args.path))
        if path_error:
            console.print(f"[red]{path_error}[/red]")
            return 2

    async with AgentRuntime() as runtime:
        if args.document_command == "ingest":
            return await _documents_ingest(runtime.storage_manager, args)
        if args.document_command == "list":
            return _documents_list(runtime.storage_manager)
        if args.document_command == "stats":
            return _documents_stats(runtime.storage_manager)
        if args.document_command == "delete":
            return await _documents_delete(runtime.storage_manager, args)
    return 2


async def _documents_ingest(storage_manager: Any, args: argparse.Namespace) -> int:
    result = await ingest_document(
        storage_manager,
        Path(args.path),
        args.id,
        chunker=chunk_text,
        entity_extractor=extract_entities,
        embeddings_factory=create_embeddings,
        embedder=embed_documents_batched,
    )
    _print_mapping("Documents ingest", result)
    return 0


def _documents_stats(storage_manager: Any) -> int:
    _print_mapping("Documents stats", document_stats(storage_manager))
    return 0


def _documents_list(storage_manager: Any) -> int:
    table = Table(title="Documents")
    table.add_column("id")
    table.add_column("source")
    table.add_column("chunks")
    table.add_column("entities")
    for doc in list_documents(storage_manager):
        table.add_row(doc["id"], doc["source"], str(doc["chunks"]), str(doc["entities"]))
    console.print(table)
    return 0


async def _documents_delete(storage_manager: Any, args: argparse.Namespace) -> int:
    if not args.yes:
        console.print("[red]删除文档需要 --yes 确认[/red]")
        return 2

    result = await delete_document(storage_manager, args.doc_id)
    _print_mapping("Documents delete", result)
    return 0


def _rollback_document_writes(storage_ctx: dict[str, Any], doc_id: str) -> None:
    from app.services.documents import rollback_document_writes

    rollback_document_writes(storage_ctx, doc_id)


def _document_ingest_path_error(path: Path) -> str:
    if not path.exists():
        message = f"文档文件不存在：{path}"
        suggestion = _suggest_existing_path(path)
        if suggestion:
            message += f"\n你是不是想输入：{suggestion}"
        return message
    if not path.is_file():
        return f"文档路径不是文件：{path}"
    return ""


def _suggest_existing_path(path: Path) -> str:
    """Return a close existing path for common CLI typos."""
    parts = path.parts
    if not parts:
        return ""

    base = Path.cwd()
    first = Path(parts[0]).name
    siblings = [item.name for item in base.iterdir() if item.is_dir()]
    matches = difflib.get_close_matches(first, siblings, n=1, cutoff=0.65)
    if matches:
        candidate = base.joinpath(matches[0], *parts[1:])
        if candidate.exists():
            return str(candidate.relative_to(base))

    parent = path.parent if str(path.parent) != "." else base
    if parent.exists() and path.name:
        names = [item.name for item in parent.iterdir()]
        file_matches = difflib.get_close_matches(path.name, names, n=1, cutoff=0.65)
        if file_matches:
            candidate = parent / file_matches[0]
            if candidate.exists():
                try:
                    return str(candidate.relative_to(base))
                except ValueError:
                    return str(candidate)

    return ""


def _print_mapping(title: str, values: dict[str, Any]) -> None:
    table = Table(title=title)
    table.add_column("key")
    table.add_column("value")
    for key, value in values.items():
        table.add_row(str(key), str(value))
    console.print(table)


def _run_doctor() -> int:
    settings = get_settings()
    table = Table(title="yd-Agent Doctor")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("yd-Agent", "ok")
    table.add_row("storage", settings.storage_dir)
    table.add_row("llm", settings.llm_model)
    table.add_row("embedding", settings.embedding_model)
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "chat":
            return asyncio.run(_run_chat(args))
        if args.command == "documents":
            return asyncio.run(_run_documents(args))
        if args.command == "memory":
            return asyncio.run(_run_memory(args))
        if args.command == "profile":
            return asyncio.run(_run_profile(args))
        if args.command == "eval":
            return asyncio.run(_run_eval(args))
        if args.command == "doctor":
            return _run_doctor()
    except Exception as exc:
        console.print(f"[red]错误：{exc}[/red]")
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
