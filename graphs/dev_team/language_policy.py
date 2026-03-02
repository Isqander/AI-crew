"""
Language policy for user-facing agent communication.

Rules:
1. Explicit language request from user has highest priority.
2. Otherwise use the language of the latest user input.
3. Default to English when unknown.
"""

from __future__ import annotations

import re
from typing import Any


DEFAULT_LANGUAGE = "en"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "it": "Italian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
}

LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "en": ("english", "английский", "английском", "англ"),
    "ru": ("russian", "русский", "русском", "по-русски", "на русском"),
    "es": ("spanish", "espanol", "español", "испанский", "испанском"),
    "de": ("german", "deutsch", "немецкий", "немецком"),
    "fr": ("french", "francais", "français", "французский", "французском"),
    "pt": ("portuguese", "portugues", "português", "португальский", "португальском"),
    "it": ("italian", "italiano", "итальянский", "итальянском"),
    "zh": ("chinese", "中文", "китайский", "китайском"),
    "ja": ("japanese", "日本語", "японский", "японском"),
    "ko": ("korean", "한국어", "корейский", "корейском"),
    "ar": ("arabic", "العربية", "арабский", "арабском"),
    "hi": ("hindi", "हिन्दी", "хинди"),
    "tr": ("turkish", "türkçe", "турецкий", "турецком"),
}

_EN_REQUEST_VERB = re.compile(
    r"\b(reply|respond|answer|write|speak|communicate|talk|use)\b",
    re.IGNORECASE,
)
_RU_REQUEST_VERB = re.compile(
    r"(отвечай|ответь|пиши|говори|общайся|общайтесь|используй|используйте)",
    re.IGNORECASE,
)
_LANGUAGE_DECLARATION = re.compile(r"\b(language|язык)\b\s*[:=-]", re.IGNORECASE)


def _message_content(message: Any) -> str:
    """Extract text content from dict-like or LangChain message objects."""
    if isinstance(message, dict):
        content = message.get("content", "")
        return content if isinstance(content, str) else str(content)

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _message_type(message: Any) -> str:
    """Extract normalized message type."""
    if isinstance(message, dict):
        t = str(message.get("type", "")).lower()
        if t == "human":
            return "human"
        if t in ("ai", "assistant"):
            return "ai"
        return t

    t = str(getattr(message, "type", "")).lower()
    if t in ("human", "ai"):
        return t

    role = str(getattr(message, "role", "")).lower()
    if role in ("human", "user"):
        return "human"
    if role in ("assistant", "ai"):
        return "ai"
    return t or role


def _iter_user_texts(state: dict[str, Any] | None) -> list[str]:
    """Return user-originated texts ordered from newest to oldest."""
    if not state:
        return []

    texts: list[str] = []

    clarification = state.get("clarification_response")
    if isinstance(clarification, str) and clarification.strip():
        texts.append(clarification)

    messages = state.get("messages", [])
    if isinstance(messages, list):
        for msg in reversed(messages):
            if _message_type(msg) == "human":
                content = _message_content(msg).strip()
                if content:
                    texts.append(content)

    context = state.get("context")
    if isinstance(context, str) and context.strip():
        texts.append(context)

    task = state.get("task")
    if isinstance(task, str) and task.strip():
        texts.append(task)

    return texts


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(alias.lower() in low for alias in aliases)


def extract_explicit_language_request(text: str) -> str | None:
    """Return language code if text explicitly asks to switch communication language."""
    if not text or not text.strip():
        return None

    low = text.lower().replace("ё", "е")
    has_request_context = bool(
        _EN_REQUEST_VERB.search(low)
        or _RU_REQUEST_VERB.search(low)
        or _LANGUAGE_DECLARATION.search(low)
    )
    if not has_request_context:
        return None

    for code, aliases in LANGUAGE_ALIASES.items():
        if _contains_alias(low, aliases):
            return code
    return None


def detect_text_language(text: str) -> str:
    """Lightweight script-based language detection for latest user message."""
    if not text or not text.strip():
        return DEFAULT_LANGUAGE

    if re.search(r"[\u0400-\u04FF]", text):
        return "ru"
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if re.search(r"[\u3040-\u30FF]", text):
        return "ja"
    if re.search(r"[\uAC00-\uD7AF]", text):
        return "ko"
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh"

    # Latin or unknown script defaults to English.
    return DEFAULT_LANGUAGE


def resolve_user_language(state: dict[str, Any] | None) -> str:
    """Resolve communication language with explicit-request priority."""
    user_texts = _iter_user_texts(state)

    # Highest priority: explicit language switch request (newest wins).
    for text in user_texts:
        explicit = extract_explicit_language_request(text)
        if explicit:
            return explicit

    # Fallback: language of latest user input.
    for text in user_texts:
        detected = detect_text_language(text)
        if detected:
            return detected

    return DEFAULT_LANGUAGE


def resolve_user_language_name(state: dict[str, Any] | None) -> str:
    """Return readable language name for prompt instructions."""
    code = resolve_user_language(state)
    return LANGUAGE_NAMES.get(code, LANGUAGE_NAMES[DEFAULT_LANGUAGE])


def build_user_language_system_instruction(state: dict[str, Any] | None) -> str:
    """Build a safe system instruction for user-facing language behavior."""
    language_name = resolve_user_language_name(state)
    return (
        "User communication language policy:\n"
        f"- User-facing communication MUST be in {language_name}.\n"
        "- This applies to clarifying questions, status updates, reports, and summaries.\n"
        "- Keep machine-readable output in English (JSON keys, schemas, required markers, verdict labels, section headers).\n"
        "- Keep code blocks, file paths, commands, logs, and identifiers as required for execution."
    )


def choose_user_text(state: dict[str, Any] | None, *, en: str, ru: str) -> str:
    """Return localized static text (Russian/English) for user-visible system messages."""
    return ru if resolve_user_language(state) == "ru" else en
