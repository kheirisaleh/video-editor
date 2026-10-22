import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio.ai.client import AiError, OpenAICompatibleClient, parse_json
from studio.ai.product import fetch_page, parse_page
from studio.ai.settings import AiSettings
from studio.config import get_settings
from studio.worker.main import Worker
from tests.fake_ai import PRODUCT_HTML, FakeAi


@pytest.fixture
def fake() -> Iterator[FakeAi]:
    server = FakeAi().start()
    yield server
    server.stop()


def configure(client: TestClient, **settings: object) -> dict:
    res = client.put("/api/settings/ai", json=settings)
    assert res.status_code == 200, res.text
    return res.json()


def run_workflow(client: TestClient, sample_videos: dict[str, Path], **body: object) -> dict:
    wf = client.post("/api/workflows", json={
        "product_text": "یه کرم آبرسان خیلی سبک", "prompt": "اول نتیجه رو نشون بده",
        "options": {"min_duration": 5, "max_duration": 8, "quality": "standard"}, **body,
    }).json()  # fmt: skip
    for path in sample_videos.values():
        client.put(
            f"/api/workflows/{wf['id']}/clips",
            params={"filename": path.name},
            content=path.read_bytes(),
        )
    client.post(f"/api/workflows/{wf['id']}/submit")
    Worker().run_once()
    return client.get(f"/api/workflows/{wf['id']}").json()


def plans(workflow_id: str) -> list[dict]:
    folder = get_settings().work_dir / workflow_id / "plans"
    return [json.loads(p.read_text()) for p in sorted(folder.glob("variant_*.json"))]


def test_settings_never_expose_the_key(client: TestClient) -> None:
    out = configure(client, provider="anthropic", api_key="sk-ant-secret")
    assert out["api_key_set"] is True
    assert "secret" not in json.dumps(out)
    # Saving without a key keeps the stored one.
    out = configure(client, provider="anthropic", effort="medium")
    assert out["api_key_set"] is True and out["effort"] == "medium"
    assert client.put("/api/settings/ai", json={"provider": "openai"}).status_code == 422


def test_connection_test_with_claude(client: TestClient, fake: FakeAi) -> None:
    configure(client, provider="anthropic", api_key="sk-test", base_url=fake.url)
    result = client.post("/api/settings/ai/test").json()
    assert result["ok"] is True, result
    request = fake.requests[0]
    assert request["path"].split("?")[0] == "/v1/messages"
    assert request["headers"]["authorization"] == "Bearer sk-test"
    assert "server-side-fallback-2026-07-01" in request["headers"]["anthropic-beta"]
    body = request["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == "high"
    assert any(c["type"] == "image" for c in fake.requests[1]["body"]["messages"][0]["content"])


def test_connection_test_with_ollama_style_server(client: TestClient, fake: FakeAi) -> None:
    configure(
        client,
        provider="openai",
        base_url=f"{fake.url}/v1",
        text_model="qwen3",
        vision_model="qwen2.5vl",
    )
    result = client.post("/api/settings/ai/test").json()
    assert result["ok"] is True, result
    assert fake.requests[0]["body"]["model"] == "qwen3"
    assert fake.requests[1]["body"]["model"] == "qwen2.5vl"


def test_connection_test_reports_unreachable_server(client: TestClient) -> None:
    configure(client, provider="openai", base_url="http://127.0.0.1:9/v1", text_model="m")
    result = client.post("/api/settings/ai/test").json()
    assert result["ok"] is False
    assert "cannot reach" in result["detail"]


def test_full_workflow_with_claude(
    client: TestClient, fake: FakeAi, sample_videos: dict[str, Path]
) -> None:
    configure(client, provider="anthropic", api_key="sk-test", base_url=fake.url)
    done = run_workflow(client, sample_videos)
    assert done["status"] == "done", done["error"]
    steps = {s["name"]: s for s in done["steps"]}
    assert [s["name"] for s in done["steps"]] == [
        "ingest",
        "product",
        "analyze",
        "understand",
        "plan",
        "render",
    ]
    assert steps["understand"]["status"] == "done"
    assert steps["understand"]["result"]["labelled"] == steps["understand"]["result"]["moments"]
    assert "Claude" in steps["plan"]["result"]["planner"]
    assert steps["product"]["result"]["name"] == "cloud cream"

    hook, story, vibe = plans(done["id"])
    assert hook["texts"][0]["text"] == "POV: fake hook hook 🤍"
    assert vibe["texts"][0]["animation"] == "typewriter"
    # The two test clips hold only about 3s of usable footage, below the 5s minimum.
    assert all(
        sum(s["end"] - s["start"] for s in p["segments"]) <= 8.05 for p in (hook, story, vibe)
    )
    assert any("Not enough usable footage" in n for n in steps["plan"]["result"]["notes"])
    assert "#cloudcream #skincare" in hook["caption"]
    assert hook["caption"].startswith("hook caption")
    # Images were sent to the vision step, the Persian prompt reached the card step.
    assert any(
        c["type"] == "image" for r in fake.requests for c in r["body"]["messages"][0]["content"]
    )
    assert any("اول نتیجه" in json.dumps(r["body"], ensure_ascii=False) for r in fake.requests)
    assert len(done["outputs"]) == 3


def test_model_down_falls_back_to_rules(
    client: TestClient, fake: FakeAi, sample_videos: dict[str, Path]
) -> None:
    configure(client, provider="openai", base_url=f"{fake.url}/v1", text_model="m")
    fake.down = True
    done = run_workflow(client, sample_videos)
    assert done["status"] == "done", done["error"]
    steps = {s["name"]: s for s in done["steps"]}
    assert steps["understand"]["status"] == "skipped"
    assert steps["plan"]["result"]["planner"] == "rule based"


def test_model_down_fails_when_required(
    client: TestClient, fake: FakeAi, sample_videos: dict[str, Path]
) -> None:
    configure(client, provider="openai", base_url=f"{fake.url}/v1", text_model="m", required=True)
    fake.down = True
    done = run_workflow(client, sample_videos)
    assert done["status"] == "failed"
    assert "AI model unavailable" in done["error"]

    # Once the model is back, a retry continues where it stopped.
    fake.down = False
    client.post(f"/api/workflows/{done['id']}/retry")
    Worker().run_once()
    again = client.get(f"/api/workflows/{done['id']}").json()
    assert again["status"] == "done", again["error"]


def test_rerun_from_plan_after_connecting_a_model(
    client: TestClient, fake: FakeAi, sample_videos: dict[str, Path]
) -> None:
    done = run_workflow(client, sample_videos)
    assert done["status"] == "done"
    assert {s["name"]: s for s in done["steps"]}["understand"]["status"] == "skipped"

    configure(client, provider="anthropic", api_key="k", base_url=fake.url)
    res = client.post(f"/api/workflows/{done['id']}/rerun", params={"from": "product"})
    assert res.json()["status"] == "queued"
    Worker().run_once()
    again = client.get(f"/api/workflows/{done['id']}").json()
    steps = {s["name"]: s for s in again["steps"]}
    assert steps["understand"]["status"] == "done"
    assert "Claude" in steps["plan"]["result"]["planner"]


def test_openai_client_falls_back_to_json_object(fake: FakeAi) -> None:
    fake.fail_json_schema = True
    client = OpenAICompatibleClient(
        AiSettings(provider="openai", base_url=f"{fake.url}/v1", text_model="m")
    )
    schema = {"type": "object", "properties": {"english": {"type": "string"}}}
    assert client.json(system="s", parts=["x"], schema=schema) == {"english": "hydrating cream"}
    formats = [r["body"]["response_format"]["type"] for r in fake.requests]
    assert formats == ["json_schema", "json_object"]


def test_parse_json_tolerates_chatter() -> None:
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here: {"a": {"b": 2}} done') == {"a": {"b": 2}}
    with pytest.raises(AiError):
        parse_json("no json here")


def test_product_page_parsing(fake: FakeAi) -> None:
    page = parse_page("https://shop/p", PRODUCT_HTML)
    assert page.title == "Cloud Cream 50ml"
    assert page.description == "Weightless hydration for every skin type."
    assert page.structured[0]["name"] == "Cloud Cream"
    assert "Absorbs in seconds." in page.text
    assert "tracking" not in page.text

    fetched = fetch_page(f"{fake.url}/product/1")
    assert fetched.error is None and fetched.title == "Cloud Cream 50ml"
    assert fetch_page(f"{fake.url}/missing").error is not None
