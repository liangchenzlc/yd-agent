from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_text(path: Path) -> tuple[str, dict[str, Any]]:
    """根据文件扩展名提取文本内容和元数据。

    支持：txt, md, json, csv, pdf, docx。
    新增解析器只需实现 (Path) -> (str, dict) 函数并注册到 _PARSERS 字典。
    """
    suffix = path.suffix.lower()

    parser = _PARSERS.get(suffix)
    if parser is None:
        raise ValueError(f"不支持的文件类型: {suffix}")

    return parser(path)


def _parse_txt(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return text, {"file_type": "text"}


def _parse_md(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return text, {"file_type": "markdown"}


def _parse_json(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return text, {"file_type": "json"}


def _parse_csv(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return text, {"file_type": "csv"}


def _parse_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("请安装 pypdf 库：pip install pypdf")

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            pages.append(page_text)

    text = "\n\n".join(pages)
    return text, {
        "file_type": "pdf",
        "page_count": len(reader.pages),
    }


def _parse_docx(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        from docx import Document
        from docx.opc.exceptions import PackageNotFoundError
    except ImportError:
        raise ValueError("请安装 python-docx 库：pip install python-docx")

    try:
        doc = Document(str(path))
    except PackageNotFoundError:
        if path.suffix.lower() == ".doc":
            raise ValueError("不支持旧版 .doc 格式，请另存为 .docx 后再上传")
        raise

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)
    return text, {
        "file_type": "docx",
        "paragraph_count": len(paragraphs),
    }


_PARSERS: dict[str, Any] = {
    ".txt": _parse_txt,
    ".md": _parse_md,
    ".json": _parse_json,
    ".csv": _parse_csv,
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
    ".doc": _parse_docx,  # 尝试解析，旧版格式会抛出清晰错误
}
