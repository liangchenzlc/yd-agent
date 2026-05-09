from __future__ import annotations

import json
from typing import Any

from app.agent.constants import DEFAULT_ENTITY_TYPES, GRAPH_FIELD_SEP
from app.agent.llm import factory as llm_factory
from app.domain.llm_output import EntityExtractionOutput

EXTRACT_SYSTEM_PROMPT = """## 角色
你是一个信息抽取助手，负责从文本中提取实体和关系。

## 实体类型
{entity_types}

## 任务
从以下文本中提取所有提到的实体和它们之间的关系。

## 规则
1. 实体名称尽量保持原文。
2. 关系类型用简洁的英文或中文描述（如 "depends_on"、"负责"、"属于"）。
3. 如果文本中没有实体，返回空数组。
"""

EXTRACT_USER_PROMPT = """## 文本
{text}

## 输出
请提取实体和关系。"""

GLEAN_PROMPT = """## 任务
检查以下实体和关系列表中是否遗漏了重要的实体或关系。

## 已提取的实体
{entities_str}

## 已提取的关系
{relationships_str}

## 文本
{text}

## 缺失的实体和关系
请补充遗漏的实体和关系。如果已完整，返回空数组。
"""


def _merge_entities(existing: list[dict], new: list[dict], source_id: str) -> list[dict]:
    """合并实体，同名实体合并 source_id。"""
    name_map = {e["name"]: e for e in existing}
    for ne in new:
        name = ne.get("name", "").strip()
        if not name:
            continue
        if name in name_map:
            existing_entry = name_map[name]
            existing_entry.setdefault("source_id", "")
            existing_entry["source_id"] += f"{GRAPH_FIELD_SEP}{source_id}"
            existing_entry["source_id"] = existing_entry["source_id"].strip(GRAPH_FIELD_SEP)
        else:
            ne["source_id"] = source_id
            name_map[name] = ne
    return list(name_map.values())


def _deduplicate_relationships(rels: list[dict]) -> list[dict]:
    """去重对称关系。"""
    seen = set()
    result = []
    for r in rels:
        key = (r.get("source", ""), r.get("target", ""), r.get("type", ""))
        rev_key = (r.get("target", ""), r.get("source", ""), r.get("type", ""))
        if key not in seen and rev_key not in seen:
            seen.add(key)
            result.append(r)
    return result


def _extract_with_llm(
    system_prompt: str,
    user_prompt: str,
) -> dict[str, list]:
    """用结构化输出调用 LLM 抽取实体和关系。"""
    llm = llm_factory.create_llm(temperature=0)
    structured_llm = llm.with_structured_output(EntityExtractionOutput)

    result: EntityExtractionOutput = structured_llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    return {
        "entities": [{"name": e.name, "type": e.type, "description": e.description} for e in result.entities if e.name],
        "relationships": [
            {"source": r.source, "target": r.target, "type": r.type, "description": r.description}
            for r in result.relationships if r.source and r.target
        ],
    }


def extract_entities(
    chunks: list[dict],
    entity_types: list[str] | None = None,
    max_gleaning: int = 1,
) -> dict[str, list]:
    """从文档块中抽取实体和关系。

    返回 {"entities": [...], "relationships": [...]}
    """
    if entity_types is None:
        entity_types = DEFAULT_ENTITY_TYPES

    all_entities: list[dict] = []
    all_relationships: list[dict] = []

    system_prompt = EXTRACT_SYSTEM_PROMPT.replace("{entity_types}", "\n".join(f"- {t}" for t in entity_types))

    for chunk in chunks:
        content = chunk["content"]
        source_id = chunk["chunk_id"]

        user_prompt = EXTRACT_USER_PROMPT.replace("{text}", content)
        result = _extract_with_llm(system_prompt, user_prompt)

        chunk_entities = _merge_entities([], result.get("entities", []), source_id)
        chunk_relationships = _deduplicate_relationships(result.get("relationships", []))

        # gleaning 轮次
        for _ in range(max_gleaning):
            entities_str = json.dumps(chunk_entities, ensure_ascii=False, indent=2)
            rels_str = json.dumps(chunk_relationships, ensure_ascii=False, indent=2)
            glean_prompt = GLEAN_PROMPT.replace("{entities_str}", entities_str).replace(
                "{relationships_str}", rels_str
            ).replace("{text}", content)
            glean_result = _extract_with_llm(system_prompt, glean_prompt)

            new_entities = glean_result.get("entities", [])
            new_rels = glean_result.get("relationships", [])
            if not new_entities and not new_rels:
                break
            chunk_entities = _merge_entities(chunk_entities, new_entities, source_id)
            chunk_relationships.extend(new_rels)
            chunk_relationships = _deduplicate_relationships(chunk_relationships)

        all_entities = _merge_entities(all_entities, chunk_entities, source_id)
        all_relationships.extend(chunk_relationships)

    all_relationships = _deduplicate_relationships(all_relationships)

    return {"entities": all_entities, "relationships": all_relationships}
