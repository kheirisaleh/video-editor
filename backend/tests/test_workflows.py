from pathlib import Path

from fastapi.testclient import TestClient

from studio.config import get_settings
from studio.db import session_scope
from studio.models import Workflow, WorkflowStatus
from studio.worker.main import Worker
from studio.worker.pipeline import recover_interrupted


def create(client: TestClient, **body: object) -> dict:
    res = client.post("/api/workflows", json={"product_text": "Teddy office chair", **body})
    assert res.status_code == 201, res.text
    return res.json()


def upload(client: TestClient, workflow_id: str, path: Path, name: str | None = None) -> dict:
    res = client.put(
        f"/api/workflows/{workflow_id}/clips",
        params={"filename": name or path.name},
        content=path.read_bytes(),
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_full_ingest_flow(client: TestClient, sample_videos: dict[str, Path]) -> None:
    wf = create(client, prompt="یه ویدیوی آرام و دنج")
    assert wf["status"] == "draft"
    assert [s["name"] for s in wf["steps"]] == [
        "ingest",
        "product",
        "analyze",
        "understand",
        "plan",
        "render",
    ]

    upload(client, wf["id"], sample_videos["vertical"], "IMG_0001.MOV")
    upload(client, wf["id"], sample_videos["horizontal"])

    res = client.post(f"/api/workflows/{wf['id']}/submit")
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert res.json()["queue_position"] == 1

    assert Worker().run_once() is True

    done = client.get(f"/api/workflows/{wf['id']}").json()
    assert done["status"] == "done", done["error"]
    assert done["progress"] == 1.0
    assert done["steps"][0]["result"]["clips"] == 2
    first, second = done["clips"]
    assert first["original_name"] == "IMG_0001.MOV"
    assert first["probe"]["orientation"] == "vertical"
    assert (first["probe"]["width"], first["probe"]["height"]) == (360, 640)
    assert second["probe"]["orientation"] == "horizontal"

    thumb = client.get(first["thumbnail_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    proxy = client.get(second["proxy_url"])
    assert proxy.status_code == 200
    assert len(proxy.content) > 1000

    # Without a model the vision step is skipped and the rule based planner is used.
    assert [s["status"] for s in done["steps"]] == [
        "done",
        "done",
        "done",
        "skipped",
        "done",
        "done",
    ]
    assert len(done["outputs"]) == 3
    output = done["outputs"][0]
    video = client.get(output["video_url"])
    assert video.status_code == 200
    assert len(video.content) > 10_000
    assert output["silent_url"] is None
    assert "Pr sample, no payment received." in output["caption"]
    assert client.get(output["cover_url"]).headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/workflows/{wf['id']}/files/..%2Fstudio.db").status_code == 404

    listed = client.get("/api/workflows").json()
    assert listed[0]["id"] == wf["id"]
    assert listed[0]["thumbnail_url"] == first["thumbnail_url"]


def test_submit_requires_clips_and_product(
    client: TestClient, sample_videos: dict[str, Path]
) -> None:
    wf = client.post("/api/workflows", json={}).json()
    assert client.post(f"/api/workflows/{wf['id']}/submit").status_code == 422
    upload(client, wf["id"], sample_videos["vertical"])
    res = client.post(f"/api/workflows/{wf['id']}/submit")
    assert res.status_code == 422
    assert "product" in res.json()["detail"]


def test_upload_rejects_other_files(client: TestClient) -> None:
    wf = create(client)
    res = client.put(
        f"/api/workflows/{wf['id']}/clips", params={"filename": "notes.txt"}, content=b"x"
    )
    assert res.status_code == 415
    res = client.put(f"/api/workflows/{wf['id']}/clips", params={"filename": "a.mp4"}, content=b"")
    assert res.status_code == 400


def test_upload_only_in_draft(client: TestClient, sample_videos: dict[str, Path]) -> None:
    wf = create(client)
    upload(client, wf["id"], sample_videos["vertical"])
    client.post(f"/api/workflows/{wf['id']}/submit")
    res = client.put(
        f"/api/workflows/{wf['id']}/clips",
        params={"filename": "late.mp4"},
        content=sample_videos["vertical"].read_bytes(),
    )
    assert res.status_code == 409
    upload_dir = get_settings().uploads_dir / wf["id"]
    assert len(list(upload_dir.iterdir())) == 1


def test_broken_video_fails_with_message_and_can_retry(
    client: TestClient, sample_videos: dict[str, Path], tmp_path: Path
) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"this is not a video" * 100)
    wf = create(client)
    upload(client, wf["id"], broken)
    client.post(f"/api/workflows/{wf['id']}/submit")
    Worker().run_once()

    failed = client.get(f"/api/workflows/{wf['id']}").json()
    assert failed["status"] == "failed"
    assert "broken.mp4" in failed["error"]
    assert failed["steps"][0]["status"] == "failed"

    retried = client.post(f"/api/workflows/{wf['id']}/retry").json()
    assert retried["status"] == "queued"
    assert retried["steps"][0]["status"] == "pending"


def test_queue_runs_one_at_a_time_in_order(
    client: TestClient, sample_videos: dict[str, Path]
) -> None:
    ids = []
    for _ in range(2):
        wf = create(client)
        upload(client, wf["id"], sample_videos["horizontal"])
        client.post(f"/api/workflows/{wf['id']}/submit")
        ids.append(wf["id"])

    assert client.get(f"/api/workflows/{ids[1]}").json()["queue_position"] == 2
    Worker().run_once()
    assert client.get(f"/api/workflows/{ids[0]}").json()["status"] == "done"
    second = client.get(f"/api/workflows/{ids[1]}").json()
    assert second["status"] == "queued"
    assert second["queue_position"] == 1


def test_cancel_queued_and_running(client: TestClient, sample_videos: dict[str, Path]) -> None:
    wf = create(client)
    upload(client, wf["id"], sample_videos["vertical"])
    client.post(f"/api/workflows/{wf['id']}/submit")
    assert client.post(f"/api/workflows/{wf['id']}/cancel").json()["status"] == "cancelled"
    assert Worker().run_once() is False

    client.post(f"/api/workflows/{wf['id']}/retry")
    with session_scope() as s:
        row = s.get(Workflow, wf["id"])
        assert row is not None
        row.status = WorkflowStatus.RUNNING
    res = client.post(f"/api/workflows/{wf['id']}/cancel").json()
    assert res["status"] == "running"
    with session_scope() as s:
        row = s.get(Workflow, wf["id"])
        assert row is not None and row.cancel_requested


def test_worker_restart_requeues_running(
    client: TestClient, sample_videos: dict[str, Path]
) -> None:
    wf = create(client)
    upload(client, wf["id"], sample_videos["vertical"])
    client.post(f"/api/workflows/{wf['id']}/submit")
    with session_scope() as s:
        row = s.get(Workflow, wf["id"])
        assert row is not None
        row.status = WorkflowStatus.RUNNING
    assert recover_interrupted() == 1
    assert client.get(f"/api/workflows/{wf['id']}").json()["status"] == "queued"


def test_delete_removes_files(client: TestClient, sample_videos: dict[str, Path]) -> None:
    wf = create(client)
    upload(client, wf["id"], sample_videos["vertical"])
    assert client.delete(f"/api/workflows/{wf['id']}").status_code == 204
    assert client.get(f"/api/workflows/{wf['id']}").status_code == 404
    assert not (get_settings().uploads_dir / wf["id"]).exists()


def test_live_events_stream(client: TestClient) -> None:
    with client.websocket_connect("/api/live?after=0") as ws:
        assert ws.receive_json() == {"type": "hello", "id": 0}
        wf = create(client)
        event = ws.receive_json()
        assert event["type"] == "workflow"
        assert event["workflow_id"] == wf["id"]
        assert event["payload"]["status"] == "draft"


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["ffmpeg"] is True


def test_iphone_hdr_clip_is_edited(client: TestClient, hlg_video: Path) -> None:
    wf = create(client, options={"variants": 1, "min_duration": 5, "max_duration": 8})
    upload(client, wf["id"], hlg_video)
    client.post(f"/api/workflows/{wf['id']}/submit")
    with client.websocket_connect("/api/live?after=0") as ws:
        Worker().run_once()
        messages = []
        while True:
            event = ws.receive_json()
            if event.get("type") == "log":
                messages.append(event["payload"]["message"])
            if event.get("type") == "workflow" and event["payload"].get("status") == "done":
                break
    done = client.get(f"/api/workflows/{wf['id']}").json()
    assert done["status"] == "done", done["error"]
    assert done["clips"][0]["probe"]["hdr"] == "hlg"
    assert any("HDR HLG converted to SDR" in m for m in messages)
    assert len(done["outputs"]) == 1
