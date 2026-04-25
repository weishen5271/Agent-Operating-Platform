from __future__ import annotations

import hashlib
import math
import re

EMBEDDING_DIMENSIONS = 64


def tokenize(text: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]{2,}", text.lower())
    return [term for term in terms if term.strip()]


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _split_paragraphs(block: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", block) if item.strip()]


def _pack_paragraphs(
    paragraphs: list[str], *, max_chars: int, overlap: int
) -> list[str]:
    """把段落贪心打包到接近 max_chars 的 chunk；超长段落按窗口滑动。"""
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        step = max(1, max_chars - overlap)
        for start in range(0, len(paragraph), step):
            chunks.append(paragraph[start : start + max_chars])
        current = ""
    if current:
        chunks.append(current)
    return chunks


def chunk_text(
    text: str,
    *,
    max_chars: int = 900,
    overlap: int = 120,
) -> list[dict]:
    """切分 markdown 文本为标题感知 chunk。

    返回 [{"content", "parents": ["一级标题", "二级标题", ...], "locator": "section:1.2"}]。
    遇到 `#`/`##`/`###` 时新建 section，并保留路径；section 内段落贪心打包到 ``max_chars``。
    无标题文档退化为按段落贪心打包，parents=[]。
    """
    normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not normalized:
        return []

    sections: list[tuple[list[str], list[str]]] = []  # (heading_path, body_lines)
    current_path: list[str] = []
    current_body: list[str] = []
    section_counters: list[int] = []  # 每级标题计数器，用于 locator

    def flush_section() -> None:
        if current_body or current_path:
            sections.append((list(current_path), list(current_body)))

    for raw_line in normalized.splitlines():
        match = _HEADING_PATTERN.match(raw_line)
        if match:
            flush_section()
            current_body = []
            level = len(match.group(1))
            title = match.group(2).strip()
            # 调整 path 与计数器到 level-1 长度
            current_path = current_path[: level - 1] + [title]
            section_counters = section_counters[: level - 1]
            while len(section_counters) < level - 1:
                section_counters.append(0)
            section_counters.append(0)  # 当前 level 计数；body 切分时再 +1
        else:
            current_body.append(raw_line)
    flush_section()

    if not sections:
        # 整段无内容
        return []

    chunks: list[dict] = []
    section_index = 0
    for parents, body_lines in sections:
        section_index += 1
        body_text = "\n".join(body_lines).strip()
        if not body_text:
            # 仅有标题、无正文：仍保留一条占位 chunk，便于检索命中标题
            if parents:
                chunks.append(
                    {
                        "content": " / ".join(parents),
                        "parents": parents,
                        "locator": f"section:{section_index}",
                    }
                )
            continue
        paragraphs = _split_paragraphs(body_text)
        if not paragraphs:
            continue
        packed = _pack_paragraphs(paragraphs, max_chars=max_chars, overlap=overlap)
        for sub_index, piece in enumerate(packed, start=1):
            locator = (
                f"section:{section_index}.{sub_index}" if len(packed) > 1 else f"section:{section_index}"
            )
            chunks.append(
                {
                    "content": piece,
                    "parents": list(parents),
                    "locator": locator,
                }
            )

    if not chunks:
        # 退化：完全没有标题，按段落打包
        paragraphs = _split_paragraphs(normalized)
        for index, piece in enumerate(
            _pack_paragraphs(paragraphs, max_chars=max_chars, overlap=overlap), start=1
        ):
            chunks.append({"content": piece, "parents": [], "locator": f"chunk:{index}"})
    return chunks


def embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
