from agent_platform.plugins.knowledge import KnowledgePlugin


def test_knowledge_search_does_not_fabricate_sources_for_unmatched_query() -> None:
    result = KnowledgePlugin().invoke({"query": "母爱去哪"})

    assert result["summary"] == "未在当前已发布知识源中检索到相关内容。"
    assert result["matches"] == []
    assert result["retrieval"]["matched"] is False
    assert result["retrieval"]["match_count"] == 0


def test_knowledge_search_returns_scored_document_matches() -> None:
    result = KnowledgePlugin().invoke({"query": "标准查询链路"})

    assert result["retrieval"]["matched"] is True
    assert result["retrieval"]["match_count"] >= 1
    assert result["matches"][0].source_type == "knowledge"
    assert "标准查询链路" in result["matches"][0].snippet
