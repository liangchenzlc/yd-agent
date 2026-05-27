from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app.agent.tools.base import BaseTool, as_tool


class ReportTool(BaseTool):
    """图表生成工具集 — 每个图表类型一个独立工具函数。

    每个工具函数都有明确的参数签名（区别于单一的 generate_chart(chart_type, data)），
    让 LLM 能更准确地选择工具并填充参数。仅支持 matplotlib（PNG）输出。
    """

    name = "report"
    description = "图表生成工具集，支持柱状图、折线图、饼图、散点图、直方图"

    def __init__(self, base_dir: str | None = None):
        super().__init__()
        self._base_dir = base_dir

    def _get_output_dir(self) -> Path:
        from app.config.settings import get_settings

        settings = get_settings()
        base = Path(self._base_dir or settings.charts_output_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """清洗 LLM 生成的文件名，移除路径分隔符和危险字符。"""
        name = os.path.basename(filename)
        name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', name)
        name = name.strip('. ') or f"chart_{uuid.uuid4().hex[:8]}.png"
        return name

    def _make_unique_path(self, output_dir: Path, filename: str) -> Path:
        """生成唯一文件路径，避免覆盖已有文件。"""
        filename = self._sanitize_filename(filename)
        stem = Path(filename).stem
        suffix = Path(filename).suffix or ".png"
        candidate = output_dir / filename
        counter = 1
        while candidate.exists():
            candidate = output_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    @staticmethod
    def _get_mime_type(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix, "image/png")

    @staticmethod
    def _get_chart_type(filename: str) -> str:
        name = Path(filename).stem.lower()
        for ct in ("bar", "line", "pie", "scatter", "histogram"):
            if ct in name:
                return ct
        return "unknown"

    # ---- 渲染引擎 ----

    def _render_matplotlib(self, chart_type: str, data: dict, title: str, output_path: Path) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar":
            ax.bar(data["labels"], data["values"], color="steelblue")
            ax.set_xlabel("类别")
            ax.set_ylabel("值")
        elif chart_type == "line":
            ax.plot(data["labels"], data["values"], marker="o", linestyle="-", color="steelblue")
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
        elif chart_type == "pie":
            ax.pie(data["values"], labels=data["labels"], autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
        elif chart_type == "scatter":
            ax.scatter(data["x_values"], data["y_values"], color="steelblue", alpha=0.7)
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
        elif chart_type == "histogram":
            ax.hist(data["values"], bins=data.get("bins", 10), color="steelblue", edgecolor="white")
            ax.set_xlabel("值")
            ax.set_ylabel("频数")

        if title:
            ax.set_title(title)

        fig.tight_layout()
        fig.savefig(str(output_path), dpi=150)
        plt.close(fig)

    def _generate(self, chart_type: str, data: dict, title: str, output_filename: str) -> str:
        output_dir = self._get_output_dir()
        output_path = self._make_unique_path(output_dir, output_filename)

        try:
            self._render_matplotlib(chart_type, data, title, output_path)
        except KeyError as e:
            return f"生成 {chart_type} 图表缺少必要参数: {e}"
        except Exception as e:
            return f"生成 {chart_type} 图表失败: {e}"

        # 登记产物（侧信道，供 Worker 提取）
        actual_filename = output_path.name
        size_bytes = output_path.stat().st_size
        self.register_artifact(
            filepath=str(output_path),
            filename=actual_filename,
            mime_type=self._get_mime_type(actual_filename),
            kind="image",
            worker="data_analyst",
            metadata={"chartType": chart_type, "title": title},
        )

        return "图表已生成"

    # ---- 独立工具函数 ----

    @as_tool(
        name="generate_bar_chart",
        description="生成柱状图。用于展示各类别的数值对比。labels 是类别名称列表，values 是对应的数值列表。",
    )
    def generate_bar_chart(
        self, labels: list[str], values: list[float], title: str = "", output_filename: str = "bar.png"
    ) -> str:
        return self._generate("bar", {"labels": labels, "values": values}, title, output_filename)

    @as_tool(
        name="generate_line_chart",
        description="生成折线图。用于展示数据随时间或序列的变化趋势。labels 是 X 轴标签，values 是 Y 轴数值。",
    )
    def generate_line_chart(
        self, labels: list[str], values: list[float], title: str = "", output_filename: str = "line.png"
    ) -> str:
        return self._generate("line", {"labels": labels, "values": values}, title, output_filename)

    @as_tool(
        name="generate_pie_chart",
        description="生成饼图。用于展示各部分占整体的比例关系。labels 是各部分名称，values 是对应的数值（自动计算百分比）。",
    )
    def generate_pie_chart(
        self, labels: list[str], values: list[float], title: str = "", output_filename: str = "pie.png"
    ) -> str:
        return self._generate("pie", {"labels": labels, "values": values}, title, output_filename)

    @as_tool(
        name="generate_scatter_chart",
        description="生成散点图。用于展示两个变量之间的相关关系。x_values 和 y_values 是两个维度的数值列表，长度必须一致。",
    )
    def generate_scatter_chart(
        self, x_values: list[float], y_values: list[float], title: str = "", output_filename: str = "scatter.png"
    ) -> str:
        return self._generate("scatter", {"x_values": x_values, "y_values": y_values}, title, output_filename)

    @as_tool(
        name="generate_histogram",
        description="生成直方图。用于展示数值分布情况。values 是数值列表，bins 是分组数量（默认 10）。",
    )
    def generate_histogram(
        self, values: list[float], bins: int = 10, title: str = "", output_filename: str = "histogram.png"
    ) -> str:
        return self._generate("histogram", {"values": values, "bins": bins}, title, output_filename)
