from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from html import escape
from html.parser import HTMLParser

from data.universe.loader import load_china_etf_universe
from decision.current_market.instrument_ids import load_execution_instrument_aliases
from engine.asset_registry import load_execution_universe, load_research_universe

from backend.site_map import route_context


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
TEXT_CONTAINERS = {
    "td",
    "th",
    "tr",
    "li",
    "p",
    "h1",
    "h2",
    "h3",
    "summary",
    "figcaption",
    "div",
    "section",
    "header",
    "body",
}
SKIP_TEXT_TAGS = {"script", "style", "title", "textarea", "code", "pre"}


GLOBAL_READABILITY_CSS = """
  html { overflow-x:hidden; }
  body { min-width:0; }
  header, main, footer, section, article, div { min-width:0; }
  p, li, td, th, summary, a { overflow-wrap:anywhere; word-break:normal; }
  table { max-width:100%; font-size:14px; }
  th { white-space:normal; }
  pre, code { max-width:100%; white-space:pre-wrap; overflow-wrap:anywhere; }
  svg, canvas, img { max-width:100%; height:auto; }
  .page-context { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:10px 0 0; color:#5b6874; font-size:13px; }
  .page-context a { color:#175ea8; text-decoration:none; }
  .page-context .context-level { border:1px solid #b8c2ca; padding:1px 6px; color:#34424d; background:#fff; }
  @media (max-width:700px) {
    table { font-size:13px; }
    table { display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }
    th, td { padding:7px 6px; }
    .page-context { align-items:flex-start; }
  }
"""


@dataclass(frozen=True)
class _Token:
    kind: str
    raw: str
    ancestors: tuple[int, ...] = ()


class _StructuredPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tokens: list[_Token] = []
        self.stack: list[tuple[int, str]] = []
        self.tags: dict[int, str] = {}
        self.text_by_element: dict[int, list[str]] = {}
        self._next_id = 1
        self.has_viewport = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "meta" and dict(attrs).get("name") == "viewport":
            self.has_viewport = True
        element_id = self._next_id
        self._next_id += 1
        self.tags[element_id] = tag
        self.text_by_element[element_id] = []
        self.tokens.append(
            _Token(
                "start",
                self.get_starttag_text() or f"<{tag}>",
                tuple(item[0] for item in self.stack),
            )
        )
        if tag not in VOID_TAGS:
            self.stack.append((element_id, tag))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.tokens.append(_Token("raw", self.get_starttag_text() or f"<{tag}/>"))

    def handle_endtag(self, tag: str) -> None:
        self.tokens.append(_Token("end", f"</{tag}>", tuple(item[0] for item in self.stack)))
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][1] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        ancestors = tuple(item[0] for item in self.stack)
        self.tokens.append(_Token("data", data, ancestors))
        for element_id in ancestors:
            self.text_by_element[element_id].append(data)

    def handle_entityref(self, name: str) -> None:
        self.tokens.append(_Token("raw", f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.tokens.append(_Token("raw", f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        self.tokens.append(_Token("raw", f"<!--{data}-->"))

    def handle_decl(self, decl: str) -> None:
        self.tokens.append(_Token("raw", f"<!{decl}>"))

    def unknown_decl(self, data: str) -> None:
        self.tokens.append(_Token("raw", f"<![{data}]>"))


@lru_cache(maxsize=1)
def asset_name_catalog() -> dict[str, str]:
    names = {asset.asset_id: asset.name for asset in load_research_universe()}
    names.update({asset.asset_id: asset.name for asset in load_execution_universe()})

    aliases = load_execution_instrument_aliases()
    alias_map = (
        {
            row["legacy_asset_id"]: row["canonical_instrument_id"]
            for row in aliases.get("aliases", [])
        }
        if aliases.get("verified")
        else {}
    )
    for asset in load_china_etf_universe():
        legacy_id = str(asset["id"])
        name = str(asset["name"])
        names.setdefault(legacy_id, name)
        canonical_id = alias_map.get(legacy_id)
        if canonical_id:
            names.setdefault(canonical_id, name)

    for asset_id, name in tuple(names.items()):
        if asset_id.endswith((".SH", ".SZ")):
            names.setdefault(asset_id.split(".", 1)[0], name)
    return dict(sorted(names.items(), key=lambda item: (-len(item[0]), item[0])))


def enhance_page_html(html: str, path: str) -> str:
    parser = _parse(html)
    breadcrumb = _breadcrumb_html(path)
    output: list[str] = []
    for token in parser.tokens:
        if token.kind == "data":
            output.append(_label_data(token, parser))
        elif token.kind == "end" and token.raw == "</head>":
            if not parser.has_viewport:
                output.append('<meta name="viewport" content="width=device-width,initial-scale=1"/>')
            output.append(
                f'<style data-global-readability="true">{GLOBAL_READABILITY_CSS}</style>'
            )
            output.append(token.raw)
        elif token.kind == "end" and token.raw == "</header>":
            output.append(breadcrumb)
            output.append(token.raw)
        else:
            output.append(token.raw)
    return "".join(output)


def find_unlabeled_asset_codes(html: str) -> list[str]:
    parser = _parse(html)
    missing: set[str] = set()
    for token in parser.tokens:
        if token.kind != "data" or _skip_token(token, parser):
            continue
        container_text = _container_text(token, parser)
        for asset_id, name in asset_name_catalog().items():
            if _contains_identifier(token.raw, asset_id) and name not in container_text:
                missing.add(asset_id)
    return sorted(missing)


def _parse(html: str) -> _StructuredPageParser:
    parser = _StructuredPageParser()
    parser.feed(html)
    parser.close()
    return parser


def _label_data(token: _Token, parser: _StructuredPageParser) -> str:
    if _skip_token(token, parser):
        return token.raw
    container_text = _container_text(token, parser)
    labels = {
        asset_id: name
        for asset_id, name in asset_name_catalog().items()
        if name not in container_text
    }
    return _label_identifiers(token.raw, labels)


def _skip_token(token: _Token, parser: _StructuredPageParser) -> bool:
    return any(
        parser.tags.get(element_id) in SKIP_TEXT_TAGS
        for element_id in token.ancestors
    )


def _container_text(token: _Token, parser: _StructuredPageParser) -> str:
    for element_id in reversed(token.ancestors):
        if parser.tags.get(element_id) in TEXT_CONTAINERS:
            return " ".join(parser.text_by_element.get(element_id, []))
    return token.raw


def _label_identifiers(text: str, labels: dict[str, str]) -> str:
    if not text or not labels:
        return text
    result: list[str] = []
    index = 0
    identifiers = tuple(labels)
    while index < len(text):
        match = next(
            (
                asset_id
                for asset_id in identifiers
                if text.startswith(asset_id, index)
                and _is_boundary(text, index, len(asset_id))
            ),
            None,
        )
        if not match:
            result.append(text[index])
            index += 1
            continue
        result.append(f"{match} {labels[match]}")
        index += len(match)
    return "".join(result)


def _contains_identifier(text: str, asset_id: str) -> bool:
    start = text.find(asset_id)
    while start >= 0:
        if _is_boundary(text, start, len(asset_id)):
            return True
        start = text.find(asset_id, start + 1)
    return False


def _is_boundary(text: str, start: int, length: int) -> bool:
    before = text[start - 1] if start else ""
    after_index = start + length
    after = text[after_index] if after_index < len(text) else ""
    return not _identifier_character(before) and not _identifier_character(after)


def _identifier_character(value: str) -> bool:
    return bool(value) and (value.isalnum() or value in "._")


def _breadcrumb_html(path: str) -> str:
    context = route_context(path)
    level_labels = {
        "primary": "主要页面",
        "advanced": "研究验证",
        "audit": "高级审计",
        "archived": "历史归档",
        "system": "系统导航",
        "unclassified": "其他页面",
    }
    links: list[str] = ['<a href="/">系统首页</a>']
    parent = context["parent"]
    if parent and parent != "/":
        parent_context = route_context(parent)
        links.append(
            f'<a href="{escape(parent)}">{escape(parent_context["label"])}</a>'
        )
    if path != "/":
        links.append(f'<strong>{escape(context["label"])}</strong>')
    trail = '<span aria-hidden="true">/</span>'.join(links)
    level = escape(level_labels.get(context["level"], context["level"]))
    return (
        '<nav class="page-context" aria-label="页面层级">'
        f'<span>当前位置：</span>{trail}'
        f'<span class="context-level">{level}</span></nav>'
    )
