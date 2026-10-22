import json
from pathlib import Path
from typing import Any

from studio.ai.client import AiError
from studio.ai.product import PageInfo, ProductCard, build_card, fetch_page, rule_card
from studio.db import session_scope
from studio.models import Workflow
from studio.planning.baseline import ProductInfo, product_features
from studio.worker.context import StepContext
from studio.worker.steps import ai_client, ai_failed

CARD_FILE = "product.json"


def load_card(work_dir: Path) -> ProductCard | None:
    path = work_dir / CARD_FILE
    if not path.is_file():
        return None
    return ProductCard.model_validate(json.loads(path.read_text())["card"])


class ProductStep:
    """Read the product link and build the product card."""

    name = "product"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        with session_scope() as s:
            wf = s.get(Workflow, ctx.workflow_id)
            assert wf is not None
            title, text, url, prompt = wf.title, wf.product_text, wf.product_url, wf.prompt

        page: PageInfo | None = None
        if url:
            ctx.progress(0.1, "reading the product page")
            page = fetch_page(url)
            if page.error:
                ctx.log(f"product link: {page.error}; using the description", "warning")
            else:
                ctx.log(f"product page: {page.title or url}")
        ctx.check_cancel()

        settings, client = ai_client(ctx)
        card: ProductCard
        if client is not None:
            ctx.progress(0.4, f"writing the product card with {client.name}")
            try:
                card = build_card(client, title, text, prompt, page)
            except AiError as exc:
                ai_failed(ctx, settings, exc)
                card = rule_card(title, text, page)
        else:
            card = rule_card(title, text, page)
            for note in product_features(ProductInfo(title, text, url, prompt))[2]:
                ctx.log(note, "warning")

        if not card.features and not text and (page is None or page.error):
            ctx.log(
                "no product details found: only the hook and call to action are shown", "warning"
            )
        (ctx.work_dir / CARD_FILE).write_text(json.dumps({
            "card": card.model_dump(),
            "page": {"url": page.url, "title": page.title, "error": page.error} if page else None,
        }, indent=1, ensure_ascii=False))  # fmt: skip
        ctx.log(f"product: {card.name}; features: {', '.join(card.features) or 'none'}")
        return {
            "name": card.name,
            "features": len(card.features),
            "source": card.source,
            "page": "read" if page and not page.error else (page.error if page else None),
        }
