import hashlib
import re
from typing import Dict

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover - runtime fallback when dependency is missing
    GoogleTranslator = None


_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_ENGLISH_PATTERN = re.compile(r"[A-Za-z]")


def _contains_chinese(text: str) -> bool:
    if not text:
        return False
    return bool(_CHINESE_PATTERN.search(text))


def _english_char_count(text: str) -> int:
    if not text:
        return 0
    return len(_ENGLISH_PATTERN.findall(text))


def should_show_translate_button(paper: Dict) -> bool:
    """
    仅对英文文献展示翻译按钮：标题和摘要中存在英文且不包含中文。
    """
    title = str(paper.get("title", "") or "")
    abstract = str(paper.get("abstract", "") or "")
    combined = f"{title} {abstract}".strip()

    if not combined or combined == "暂无数据":
        return False
    if _contains_chinese(combined):
        return False
    return _english_char_count(combined) >= 8


def paper_translate_id(paper: Dict, index: int) -> str:
    """
    为每条文献生成稳定的翻译状态键。
    """
    raw = "|".join(
        [
            str(paper.get("doi", "") or ""),
            str(paper.get("title", "") or ""),
            str(paper.get("year", "") or ""),
            str(index),
        ]
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _split_text(text: str, max_len: int = 1200):
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_len:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            if len(sentence) <= max_len:
                current = sentence
            else:
                for i in range(0, len(sentence), max_len):
                    chunks.append(sentence[i : i + max_len])
                current = ""

    if current:
        chunks.append(current)

    return chunks if chunks else [text]


def translate_text_to_chinese(text: str) -> str:
    """
    将英文文本翻译为中文；失败时返回原文，保证页面稳定。
    """
    if not text or text == "暂无数据":
        return text
    if GoogleTranslator is None:
        return text

    chunks = _split_text(str(text), max_len=1200)
    translated_chunks = []

    for chunk in chunks:
        try:
            translated = GoogleTranslator(source="auto", target="zh-CN").translate(chunk)
            translated_chunks.append(translated if translated else chunk)
        except Exception:
            translated_chunks.append(chunk)

    return "\n".join(translated_chunks)


def translate_paper_to_chinese(paper: Dict) -> Dict:
    """
    翻译文献的可读字段，保留原始结构。
    """
    translated = dict(paper)
    translated["title"] = translate_text_to_chinese(str(paper.get("title", "") or ""))
    translated["abstract"] = translate_text_to_chinese(str(paper.get("abstract", "") or ""))
    translated["source"] = translate_text_to_chinese(str(paper.get("source", "") or ""))
    return translated
