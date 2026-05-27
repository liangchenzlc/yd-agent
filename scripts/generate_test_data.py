"""生成测试数据用于手动验证产物展示功能。

用法:
    python -m scripts.generate_test_data [--db PATH]

默认写入 ./data/web.db，不覆盖已有数据。
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from app.web.auth import hash_password
from app.web.db import WebDatabase

TENANT = "default"


def _make_png(path: Path) -> None:
    """写入一个最小合法 PNG 文件（1×1 蓝色像素）。"""
    import struct, zlib

    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1×1 RGB8
    raw = zlib.compress(b"\x00\x00\x00\xff")  # filter=0, pixel=(0,0,255)
    path.write_bytes(signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", raw) + _chunk(b"IEND", b""))


def generate(db_path: Path) -> None:
    db = WebDatabase(db_path)
    db.initialize()

    # --- 用户 ---
    alice = db.create_user("alice", hash_password("alice123"), role="user", tenant_id=TENANT)
    bob = db.create_user("bob", hash_password("bob123"), role="user", tenant_id=TENANT)

    # --- 会话 + 消息 + 产物 ---
    artifact_dir = db_path.parent / "artifacts" / TENANT
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Alice 的会话
    sid_a = "sess_alice_001"
    db.ensure_session(alice["id"], sid_a, "季度销售分析", tenant_id=TENANT)
    db.add_message(sid_a, alice["id"], "user", "帮我分析一下本季度销售数据", tenant_id=TENANT)
    msg_a = db.add_message(sid_a, alice["id"], "assistant", "图表已生成，柱状图展示了各月销售额趋势。", tenant_id=TENANT)

    chart_path = artifact_dir / "art_demo_chart.png"
    _make_png(chart_path)
    db.add_artifact({
        "id": "art_demo_chart",
        "tenant_id": TENANT,
        "user_id": alice["id"],
        "session_id": sid_a,
        "message_id": msg_a["id"],
        "qa_log_id": None,
        "worker": "data_analyst",
        "kind": "image",
        "filename": "quarterly_sales.png",
        "mime_type": "image/png",
        "size_bytes": chart_path.stat().st_size,
        "storage_path": str(chart_path),
    })

    report_path = artifact_dir / "art_demo_report.txt"
    report_path.write_text("本季度总销售额：1,234,567 元\n月均增长率：5.2%", encoding="utf-8")
    db.add_artifact({
        "id": "art_demo_report",
        "tenant_id": TENANT,
        "user_id": alice["id"],
        "session_id": sid_a,
        "message_id": msg_a["id"],
        "qa_log_id": None,
        "worker": "data_analyst",
        "kind": "file",
        "filename": "quarterly_report.txt",
        "mime_type": "text/plain",
        "size_bytes": report_path.stat().st_size,
        "storage_path": str(report_path),
    })

    # Bob 的会话（无产物）
    sid_b = "sess_bob_001"
    db.ensure_session(bob["id"], sid_b, "IT 支持问题", tenant_id=TENANT)
    db.add_message(sid_b, bob["id"], "user", "VPN 怎么连？", tenant_id=TENANT)
    db.add_message(sid_b, bob["id"], "assistant", "请参考 IT 知识库中的 VPN 配置指南。", tenant_id=TENANT)

    print(f"测试数据已写入: {db_path}")
    print(f"  用户: alice / alice123,  bob / bob123")
    print(f"  Alice 会话 {sid_a}: 含 2 个产物（图片 + 文本）")
    print(f"  Bob   会话 {sid_b}: 无产物")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成产物展示功能测试数据")
    parser.add_argument("--db", type=Path, default=Path("data/web.db"))
    args = parser.parse_args()

    db_path: Path = args.db.resolve()
    if db_path.exists():
        confirm = input(f"{db_path} 已存在，覆盖？[y/N] ").strip().lower()
        if confirm != "y":
            print("已取消")
            return
        db_path.unlink()
        artifact_dir = db_path.parent / "artifacts"
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)

    generate(db_path)


if __name__ == "__main__":
    main()
