from __future__ import annotations

from pathlib import Path
import re

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin


class KnowledgePlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="knowledge.search",
        description="检索平台文档与知识条目。",
        risk_level="low",
        side_effect_level="read",
        required_scope="knowledge:read",
        input_schema={"required": ["query"]},
        output_schema={"required": ["summary", "matches"]},
    )

    def __init__(self) -> None:
        repo_root = Path(__file__).resolve().parents[5]
        docs_dir = repo_root / "docs"
        self._documents: list[dict[str, str]] = []
        for path in sorted(docs_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            self._documents.append(
                {
                    "id": path.stem,
                    "title": path.stem,
                    "content": content,
                }
            )

    def invoke(self, payload: dict[str, str]) -> dict[str, object]:
        query = payload["query"].strip()
        terms = self._tokenize(query)
        matches: list[tuple[int, SourceReference]] = []
        for document in self._documents:
            score = self._score(document=document, query=query, terms=terms)
            if score > 0:
                snippet = self._build_snippet(document["content"], query, terms)
                matches.append(
                    (
                        score,
                        SourceReference(
                            id=document["id"],
                            title=document["title"],
                            snippet=snippet,
                            source_type="knowledge",
                        ),
                    )
                )
        ordered_matches = [item for _score, item in sorted(matches, key=lambda item: item[0], reverse=True)]
        summary = "已从平台文档中整理出与你问题最相关的要点。" if ordered_matches else "未在当前已发布知识源中检索到相关内容。"
        return {
            "summary": summary,
            "matches": ordered_matches[:3],
            "retrieval": {
                "backend": "local_docs_keyword",
                "query": query,
                "matched": bool(ordered_matches),
                "candidate_count": len(self._documents),
                "match_count": len(ordered_matches),
            },
        }

    @staticmethod
    def _tokenize(query: str) -> list[str]:
        terms = re.findall(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]{2,}", query.lower())
        return [term for term in terms if term.strip()]

    @staticmethod
    def _score(*, document: dict[str, str], query: str, terms: list[str]) -> int:
        title = document["title"].lower()
        content = document["content"].lower()
        normalized_query = query.lower()
        score = 0
        if normalized_query and normalized_query in title:
            score += 20
        if normalized_query and normalized_query in content:
            score += 10
        for term in terms:
            if term in title:
                score += 6
            if term in content:
                score += min(content.count(term), 5)
        return score

    @staticmethod
    def _build_snippet(content: str, query: str, terms: list[str]) -> str:
        index = content.lower().find(query.lower())
        if index == -1:
            index = next((content.lower().find(term) for term in terms if content.lower().find(term) != -1), -1)
        if index == -1:
            return content[:120].replace("\n", " ")
        start = max(index - 40, 0)
        end = min(index + 80, len(content))
        return content[start:end].replace("\n", " ")
