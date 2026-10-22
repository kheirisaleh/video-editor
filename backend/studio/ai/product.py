"""Product understanding: read the product page, then build a product card.

The card is what every later step uses: an English product name, short benefit lines
for the overlays and hints for emoji and hashtags. With a model the card is written
from the page, the description and the Persian idea prompt; without one it falls back
to the page title and the description lines.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from studio.ai.client import AiClient, AiError

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
MAX_PAGE_TEXT = 12_000


@dataclass
class PageInfo:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    structured: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def useful(self) -> bool:
        return bool(self.title or self.description or self.structured or len(self.text) > 200)

    def summary(self) -> str:
        parts = [f"URL: {self.url}"]
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.structured:
            parts.append(
                "Structured data: " + json.dumps(self.structured, ensure_ascii=False)[:4000]
            )
        if self.text:
            parts.append(f"Page text:\n{self.text}")
        return "\n".join(parts)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.ld_json: list[str] = []
        self.text: list[str] = []
        self._in: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])
        if tag == "script" and "ld+json" in a.get("type", ""):
            self._in.append("ld")
        elif tag in ("script", "style", "noscript", "svg", "template"):
            self._in.append("skip")
        elif tag == "title":
            self._in.append("title")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg", "template", "title") and self._in:
            self._in.pop()

    def handle_data(self, data: str) -> None:
        state = self._in[-1] if self._in else None
        if state == "ld":
            self.ld_json.append(data)
        elif state == "title":
            self.title += data
        elif state is None and data.strip():
            self.text.append(data.strip())


def _products(value: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(value, list):
        for v in value:
            found += _products(v)
    elif isinstance(value, dict):
        kind = value.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Product" in kinds:
            keep = ("name", "description", "brand", "color", "material", "offers", "category")
            found.append({k: value[k] for k in keep if k in value})
        for key in ("@graph", "itemListElement"):
            if key in value:
                found += _products(value[key])
    return found


def parse_page(url: str, html: str) -> PageInfo:
    parser = _PageParser()
    try:
        parser.feed(html)
    except Exception:  # broken markup must not stop the workflow
        log.warning("could not fully parse %s", url)
    structured: list[dict[str, Any]] = []
    for raw in parser.ld_json:
        try:
            structured += _products(json.loads(raw))
        except ValueError:
            continue
    meta = parser.meta
    text = re.sub(r"\s+", " ", " ".join(parser.text))[:MAX_PAGE_TEXT]
    return PageInfo(
        url=url,
        title=(meta.get("og:title") or parser.title).strip(),
        description=(meta.get("og:description") or meta.get("description") or "").strip(),
        text=text,
        structured=structured[:3],
    )


def fetch_page(url: str, timeout: float = 20.0) -> PageInfo:
    try:
        res = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en,de;q=0.8"},
            follow_redirects=True,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return PageInfo(url=url, error=f"could not open the link: {exc}")
    if res.status_code >= 400:
        return PageInfo(url=url, error=f"the shop answered {res.status_code}")
    page = parse_page(str(res.url), res.text)
    if not page.useful:
        page.error = "the page did not contain readable product information"
    return page


# Product card -------------------------------------------------------------------------


class ProductCard(BaseModel):
    name: str = Field(description="short English product name for overlays, lowercase friendly")
    category: str = ""
    features: list[str] = Field(
        default_factory=list, description="short English benefit lines, best first"
    )
    emojis: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    audience: str = ""
    idea: str = Field(default="", description="the creator's idea prompt, in English")
    source: str = "rule based"


CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "category": {"type": "string"},
        "features": {"type": "array", "items": {"type": "string"}},
        "emojis": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "audience": {"type": "string"},
        "idea": {"type": "string"},
    },
    "required": ["name", "category", "features", "emojis", "hashtags", "audience", "idea"],
    "additionalProperties": False,
}

CARD_SYSTEM = """You prepare product facts for short TikTok product videos.

The creator films product samples (unboxing or promotion) in a soft, cozy lifestyle
aesthetic. The videos have no voice; short English text overlays carry the message.
The creator writes in Persian or English; everything you return must be in English,
except emojis.

Return:
* name: the product as a creator would call it in an overlay, 1 to 4 words, lowercase
  except brand names (for example "teddy office chair", "Philips Sonicare 4100").
* category: one or two words.
* features: 4 to 8 overlay lines, each at most 40 characters, concrete and true to the
  sources, best selling point first. Turn spec sheets into felt benefits
  ("135° reclining" stays, "Material: polyester 100%" becomes "Soft teddy fabric").
  No marketing exaggeration, no prices.
* emojis: 3 soft emojis that fit the product and its colour (for example 🤍 ✨ 🧸).
* hashtags: 2 to 4 product hashtags without spaces, starting with #.
* audience: who it is for, a few words.
* idea: the creator's idea prompt translated to English and kept faithful; empty if
  there is none.

Use only facts from the sources. If the sources disagree, prefer the creator's text."""


def build_card(
    client: AiClient | None, title: str, text: str, prompt: str, page: PageInfo | None
) -> ProductCard:
    if client is not None:
        sources = []
        if title:
            sources.append(f"Creator's title: {title}")
        if text:
            sources.append(f"Creator's product text:\n{text}")
        if page and page.useful:
            sources.append(f"Product page:\n{page.summary()}")
        if prompt:
            sources.append(f"Creator's idea prompt:\n{prompt}")
        if not sources:
            sources.append("No product information was given.")
        data = client.json(
            system=CARD_SYSTEM, parts=["\n\n".join(sources)], schema=CARD_SCHEMA, max_tokens=4000
        )
        try:
            card = ProductCard.model_validate({**data, "source": client.name})
        except ValidationError as exc:
            raise AiError(f"the product card from the model was invalid: {exc}") from exc
        card.features = [f.strip() for f in card.features if f.strip()][:8]
        card.hashtags = [h if h.startswith("#") else f"#{h}" for h in card.hashtags if h][:4]
        return card
    return rule_card(title, text, page)


def rule_card(title: str, text: str, page: PageInfo | None) -> ProductCard:
    from studio.planning.baseline import ProductInfo, product_features

    combined = text
    if page and page.useful and not text.strip():
        combined = "\n".join(filter(None, [page.description]))
    name, features, _ = product_features(
        ProductInfo(title or (page.title if page else ""), combined, "", "")
    )
    return ProductCard(name=name, features=features)
