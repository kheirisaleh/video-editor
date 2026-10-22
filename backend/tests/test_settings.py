import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio.worker.main import Worker


@pytest.fixture(scope="session")
def track(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Twelve seconds of clicks at 120 BPM."""
    path = tmp_path_factory.mktemp("audio") / "Soft Beat.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "aevalsrc='sin(2*PI*880*t)*exp(-60*mod(t,0.5))':s=22050:d=12", str(path)],
        check=True,
    )  # fmt: skip
    return path


def test_defaults_roundtrip(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body["defaults"]["variants"] == 3
    assert body["fonts"] == {"sans": "TikTokSans", "serif": "SourceSerif4"}
    assert body["emoji"]

    defaults = {**body["defaults"], "min_duration": 15, "max_duration": 20, "music": False}
    assert client.put("/api/settings/defaults", json=defaults).status_code == 200
    assert client.get("/api/settings").json()["defaults"]["max_duration"] == 20

    bad = {**defaults, "min_duration": 30}
    assert client.put("/api/settings/defaults", json=bad).status_code == 422


def test_workflow_options_snapshot_defaults_with_overrides(client: TestClient) -> None:
    defaults = client.get("/api/settings").json()["defaults"]
    client.put("/api/settings/defaults", json={**defaults, "max_duration": 22})
    wf = client.post(
        "/api/workflows", json={"product_text": "Cream", "options": {"texts": False}}
    ).json()
    assert wf["options"]["texts"] is False
    assert wf["options"]["max_duration"] == 22

    # Later changes to the defaults do not change an existing workflow.
    client.put("/api/settings/defaults", json={**defaults, "max_duration": 40})
    assert client.get(f"/api/workflows/{wf['id']}").json()["options"]["max_duration"] == 22

    res = client.patch(f"/api/workflows/{wf['id']}", json={"options": {"variants": 1}})
    assert res.json()["options"]["variants"] == 1
    assert res.json()["options"]["texts"] is False

    res = client.post("/api/workflows", json={"options": {"min_duration": 50, "max_duration": 9}})
    assert res.status_code == 422


def test_music_library(client: TestClient, track: Path) -> None:
    assert client.get("/api/music").json() == []
    res = client.put("/api/music", params={"filename": track.name}, content=track.read_bytes())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "Soft Beat.wav"
    assert body["duration"] == pytest.approx(12, abs=0.1)
    assert body["tempo"] == pytest.approx(120, abs=1)
    assert client.get(body["url"]).status_code == 200

    res = client.put("/api/music", params={"filename": "x.wav"}, content=b"not audio")
    assert res.status_code == 422
    res = client.put("/api/music", params={"filename": "x.txt"}, content=b"a")
    assert res.status_code == 415
    assert [t["name"] for t in client.get("/api/music").json()] == ["Soft Beat.wav"]

    assert client.delete(f"/api/music/{body['name']}").status_code == 204
    assert client.get("/api/music").json() == []


def test_render_respects_options(
    client: TestClient, sample_videos: dict[str, Path], track: Path
) -> None:
    client.put("/api/music", params={"filename": track.name}, content=track.read_bytes())
    wf = client.post(
        "/api/workflows",
        json={
            "product_text": "Cream\nSoft texture\nAbsorbs fast",
            "options": {
                "variants": 1,
                "min_duration": 5,
                "max_duration": 6,
                "silent_copy": False,
                "quality": "standard",
            },
        },
    ).json()
    for path in sample_videos.values():
        client.put(
            f"/api/workflows/{wf['id']}/clips",
            params={"filename": path.name},
            content=path.read_bytes(),
        )
    client.post(f"/api/workflows/{wf['id']}/submit")
    Worker().run_once()

    done = client.get(f"/api/workflows/{wf['id']}").json()
    assert done["status"] == "done", done["error"]
    assert len(done["outputs"]) == 1
    out = done["outputs"][0]
    assert out["music"] == "Soft Beat"
    assert out["silent_url"] is None
    assert out["duration"] <= 6.1
