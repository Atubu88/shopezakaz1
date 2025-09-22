from __future__ import annotations

import json
import os
import re
from html.entities import name2codepoint
from html.parser import HTMLParser
from typing import Any

import httpx

__all__ = ["create_telegraph_page", "TelegraphError"]

_TELEGRAPH_API_URL = "https://api.telegra.ph/createPage"
_ALLOWED_TAGS = {
    "a",
    "aside",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h3",
    "h4",
    "hr",
    "i",
    "iframe",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
    "video",
}
_SELF_CLOSING_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "menuitem",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "canvas",
    "dd",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hgroup",
    "hr",
    "li",
    "main",
    "nav",
    "noscript",
    "ol",
    "output",
    "p",
    "pre",
    "section",
    "table",
    "tfoot",
    "ul",
    "video",
}
_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)
_TAG_DETECTION_RE = re.compile(r"<([a-zA-Z!/][^>]*)>")
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


class TelegraphError(RuntimeError):
    """Base exception for Telegraph integration errors."""


class _TelegraphContentError(TelegraphError):
    """Raised when provided HTML cannot be converted to Telegraph nodes."""


class _TelegraphHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._nodes: list[Any] = []
        self._node_stack: list[list[Any]] = [self._nodes]
        self._open_tags: list[str] = []
        self._last_text: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_TAGS:
            raise _TelegraphContentError(f"Тег <{tag}> не поддерживается Telegraph.")

        if tag in _BLOCK_TAGS:
            self._last_text = None

        node: dict[str, Any] = {"tag": tag}

        if attrs:
            attrs_dict = {name: value for name, value in attrs if value is not None}
            if attrs_dict:
                node["attrs"] = attrs_dict

        self._node_stack[-1].append(node)

        if tag not in _SELF_CLOSING_TAGS:
            children: list[Any] = []
            node["children"] = children
            self._node_stack.append(children)
            self._open_tags.append(tag)
        else:
            self._last_text = None

    def handle_endtag(self, tag: str) -> None:
        if tag in _SELF_CLOSING_TAGS:
            return

        if not self._open_tags:
            raise _TelegraphContentError(f"Для </{tag}> не найден открывающий тег.")

        expected = self._open_tags.pop()
        if expected != tag:
            raise _TelegraphContentError(
                f"Нарушен порядок закрытия тегов: ожидался </{expected}>, получен </{tag}>."
            )

        children = self._node_stack.pop()
        node = self._node_stack[-1][-1]

        if not node.get("children"):
            node.pop("children", None)

        self._last_text = None

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def handle_entityref(self, name: str) -> None:
        self._append_text(chr(name2codepoint[name]))

    def handle_charref(self, name: str) -> None:
        try:
            if name.lower().startswith("x"):
                code_point = int(name[1:], 16)
            else:
                code_point = int(name)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise _TelegraphContentError(
                f"Не удалось распознать HTML сущность &#{name};"
            ) from exc

        self._append_text(chr(code_point))

    def error(self, message: str) -> None:  # pragma: no cover - HTMLParser requirement
        raise _TelegraphContentError(message)

    def get_nodes(self) -> list[Any]:
        if self._open_tags:
            raise _TelegraphContentError(
                f"Тег <{self._open_tags[-1]}> не закрыт."
            )
        return self._nodes

    def _append_text(self, text: str) -> None:
        if not text:
            return

        current = self._node_stack[-1]

        if "pre" not in self._open_tags:
            text = _WHITESPACE_RE.sub(" ", text)
            if self._last_text is None or self._last_text.endswith(" "):
                text = text.lstrip(" ")
            if not text:
                self._last_text = None
                return
            self._last_text = text

        if current and isinstance(current[-1], str):
            current[-1] += text
        else:
            current.append(text)


def _prepare_html_input(html: str) -> str:
    """Convert plain text into minimal HTML before parsing if needed."""
    if not html:
        return ""

    if _TAG_DETECTION_RE.search(html):
        return html

    paragraphs = []
    for block in html.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        block = block.replace("\r", "").replace("\n", "<br>")
        paragraphs.append(f"<p>{block}</p>")

    if paragraphs:
        return "".join(paragraphs)

    return html.replace("\r", "").replace("\n", "<br>")


def _convert_html_to_content(html: str) -> str:
    prepared_html = _prepare_html_input(html or "")
    parser = _TelegraphHTMLParser()

    try:
        parser.feed(prepared_html)
        parser.close()
        nodes = parser.get_nodes()
    except _TelegraphContentError:
        sanitized = _WHITESPACE_RE.sub(" ", _TAG_STRIP_RE.sub(" ", html or "")).strip()
        nodes: list[Any] = [sanitized] if sanitized else [""]
    else:
        nodes = nodes if nodes else [""]

    return json.dumps(nodes, ensure_ascii=False)


async def create_telegraph_page(title: str, html: str) -> str:
    """Create a Telegraph page and return its public URL."""

    access_token = os.getenv("TELEGRAPH_TOKEN")
    if not access_token:
        raise TelegraphError("Переменная окружения TELEGRAPH_TOKEN не установлена.")

    payload = {
        "access_token": access_token,
        "title": title or "Описание товара",
        "content": _convert_html_to_content(html or ""),
        "return_content": False,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(_TELEGRAPH_API_URL, data=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TelegraphError(f"Ошибка при обращении к Telegraph: {exc}") from exc

    try:
        response_data = response.json()
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise TelegraphError("Telegraph вернул некорректный ответ.") from exc

    if not response_data.get("ok"):
        error_message = response_data.get("error") or "Неизвестная ошибка Telegraph."
        raise TelegraphError(f"Telegraph API: {error_message}")

    result = response_data.get("result") or {}
    url = result.get("url")
    if not url:
        raise TelegraphError("Telegraph не вернул ссылку на созданную страницу.")

    return url
