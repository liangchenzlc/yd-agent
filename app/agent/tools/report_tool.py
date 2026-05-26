from __future__ import annotations

from pathlib import Path

from app.agent.tools.base import BaseTool, as_tool


class ReportTool(BaseTool):
    """图表生成工具集 — 每个图表类型一个独立工具函数。

    每个工具函数都有明确的参数签名（区别于单一的 generate_chart(chart_type, data)），
    让 LLM 能更准确地选择工具并填充参数。支持 matplotlib（PNG）和 plotly（HTML）两种输出。
    """

    name = "report"
    description = "图表生成工具集，支持柱状图、折线图、饼图、散点图、直方图"

    def _get_output_dir(self) -> Path:
        from app.config.settings import get_settings

        settings = get_settings()
        base = Path(settings.charts_output_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base

    # ---- 内部渲染引擎 ----

    def _render_matplotlib(self, chart_type: str, data: dict, title: str, output_path: Path) -> str:
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
        return f"图表已保存: {output_path.resolve()}"

    def _render_plotly(self, chart_type: str, data: dict, title: str, output_path: Path) -> str:
        import plotly.express as px
        import pandas as pd

        if chart_type in ("bar", "line", "histogram"):
            df = pd.DataFrame({"x": data["labels"], "y": data["values"]})
            if chart_type == "bar":
                fig = px.bar(df, x="x", y="y", title=title)
            elif chart_type == "line":
                fig = px.line(df, x="x", y="y", title=title, markers=True)
            else:
                fig = px.histogram(df, x="y", title=title)
        elif chart_type == "pie":
            df = pd.DataFrame({"labels": data["labels"], "values": data["values"]})
            fig = px.pie(df, names="labels", values="values", title=title)
        elif chart_type == "scatter":
            df = pd.DataFrame({"x": data["x_values"], "y": data["y_values"]})
            fig = px.scatter(df, x="x", y="y", title=title)
        else:
            return f"错误：不支持的图表类型 '{chart_type}'"

        fig.write_html(str(output_path))
        return f"交互式图表已保存: {output_path.resolve()}"

    def _generate(self, chart_type: str, data: dict, title: str, output_filename: str) -> str:
        output_dir = self._get_output_dir()
        output_path = output_dir / output_filename

        try:
            if output_filename.lower().endswith(".html"):
                return self._render_plotly(chart_type, data, title, output_path)
            return self._render_matplotlib(chart_type, data, title, output_path)
        except KeyError as e:
            return f"生成 {chart_type} 图表缺少必要参数: {e}"
        except Exception as e:
            return f"生成 {chart_type} 图表失败: {e}"

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
