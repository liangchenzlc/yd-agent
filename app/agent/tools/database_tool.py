from __future__ import annotations

from app.agent.tools.base import BaseTool, as_tool


class DatabaseTool(BaseTool):
    """数据库查询工具 — 提供只读的 SQL 数据库访问能力。"""

    name = "database"
    description = "数据库查询工具"

    def _get_engine(self):
        """惰性创建 SQLAlchemy engine。"""
        from sqlalchemy import create_engine

        from app.config.settings import get_settings

        settings = get_settings()
        if not settings.db_database:
            return None

        port = settings.db_port or 3306
        if settings.db_type == "sqlite":
            conn_str = f"sqlite:///{settings.db_host}"
        elif settings.db_type == "postgresql":
            conn_str = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{port}/{settings.db_database}"
        else:
            conn_str = f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{port}/{settings.db_database}"
        return create_engine(conn_str)

    @staticmethod
    def _is_select_query(query: str) -> bool:
        """检查是否为只读查询且不包含多语句。

        同时检查：
        1. 仅允许以 SELECT/WITH/EXPLAIN/SHOW/DESCRIBE/DESC 开头的只读查询
        2. 禁止多语句注入（分号），防止 `SELECT 1; DROP TABLE users` 绕过前缀检查
        """
        stripped = query.strip()
        if stripped.count(";") > 1:
            return False
        # 忽略末尾分号（SQL 语法允许单条语句以分号结尾）
        cleaned = stripped.rstrip(";").strip()
        if ";" in cleaned:
            return False
        upper = cleaned.upper()
        return any(
            upper.startswith(kw)
            for kw in ("SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE", "DESC")
        )

    @as_tool(
        name="list_tables",
        description="列出数据库中所有表名。",
    )
    def list_tables(self) -> str:
        """查询 information_schema 获取所有表名。"""
        engine = self._get_engine()
        if engine is None:
            return "错误：数据库未配置，请在环境变量中设置数据库连接信息。"
        from sqlalchemy import inspect

        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                tables = inspector.get_table_names()
            if not tables:
                return "数据库中未找到任何表。"
            lines = [f"共 {len(tables)} 张表：", ""]
            for t in sorted(tables):
                lines.append(f"  - {t}")
            return "\n".join(lines)
        except Exception as e:
            return f"查询表名失败：{e}"

    @as_tool(
        name="get_table_schema",
        description="查看指定表的列名、类型、可空、主键、注释等结构信息。",
    )
    def get_table_schema(self, table_name: str) -> str:
        """查询表的详细结构。"""
        engine = self._get_engine()
        if engine is None:
            return "错误：数据库未配置。"
        from sqlalchemy import inspect

        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                columns = inspector.get_columns(table_name)
                pk_constraint = inspector.get_pk_constraint(table_name)
                pk_columns = pk_constraint.get("constrained_columns", []) if pk_constraint else []

            if not columns:
                return f"表 '{table_name}' 不存在或没有列。"
            lines = [f"表名: {table_name}", ""]
            lines.append(f"{'列名':<30} {'类型':<25} {'可空':<6} {'主键':<6} {'注释'}")
            lines.append("-" * 90)
            for col in columns:
                col_name = col["name"]
                col_type = str(col["type"])
                nullable = "YES" if col.get("nullable", True) else "NO"
                is_pk = "PRI" if col_name in pk_columns else ""
                comment = col.get("comment", "")
                lines.append(f"{col_name:<30} {col_type:<25} {nullable:<6} {is_pk:<6} {comment}")
            if pk_columns:
                lines.append(f"\n主键: {', '.join(pk_columns)}")
            return "\n".join(lines)
        except Exception as e:
            return f"查询表结构失败：{e}"

    @as_tool(
        name="execute_sql",
        description="执行 SELECT 查询并返回结果表格。仅允许 SELECT / WITH / EXPLAIN 等只读查询，最多返回 200 行。",
    )
    def execute_sql(self, query: str) -> str:
        """执行 SQL 查询并返回格式化结果。"""
        if not self._is_select_query(query):
            return "错误：只允许执行 SELECT 查询。为确保数据库安全，已拒绝执行非查询语句。请使用 precheck_sql 工具验证你的查询。"

        engine = self._get_engine()
        if engine is None:
            return "错误：数据库未配置。"
        from sqlalchemy import text

        try:
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchmany(201)
                if not rows:
                    return "查询执行成功，但未返回任何数据。"
                truncated = len(rows) > 200
                rows = rows[:200]
                col_names = list(result.keys())
                lines = ["  ".join(f"{c:<20}" for c in col_names)]
                lines.append("  ".join("-" * 20 for _ in col_names))
                for row in rows:
                    vals = [str(v) if v is not None else "NULL" for v in row]
                    lines.append("  ".join(f"{v:<20}" for v in vals))
                summary = f"\n\n共返回 {len(rows)} 行"
                if truncated:
                    summary += "（仅显示前 200 行，如需更多数据请添加 LIMIT 子句）"
                return "\n".join(lines) + summary
        except Exception as e:
            return f"SQL 执行失败：{e}"

    @as_tool(
        name="precheck_sql",
        description="在执行前验证 SQL 查询的语法和安全性。会执行 EXPLAIN 来检查查询计划。",
    )
    def precheck_sql(self, query: str) -> str:
        """验证 SQL 语法和安全性。"""
        if not self._is_select_query(query):
            return "安全检查失败：只允许 SELECT 查询。"

        engine = self._get_engine()
        if engine is None:
            return "错误：数据库未配置。"
        from sqlalchemy import text

        try:
            with engine.connect() as conn:
                explain_result = conn.execute(text(f"EXPLAIN {query}"))
                explain_rows = explain_result.fetchall()
                lines = ["SQL 查询预检通过。", ""]
                lines.append("查询计划：")
                for row in explain_rows:
                    lines.append(f"  {row}")
                return "\n".join(lines)
        except Exception as e:
            return f"SQL 预检查失败（语法错误）：{e}"
