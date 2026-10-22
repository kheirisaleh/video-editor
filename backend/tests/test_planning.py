import pytest

from studio.planning.baseline import ProductInfo, plan_variants, product_features
from studio.planning.schema import PlanMusic


def analysis(clips: int = 3, segments: int = 4) -> dict:
    return {
        "clips": [
            {
                "clip_id": f"c{c}",
                "source_width": 1280 if c % 2 else 720,
                "source_height": 720 if c % 2 else 1280,
                "segments": [
                    {
                        "start": s * 3.0,
                        "end": s * 3.0 + 2.4,
                        "score": 0.5 + 0.1 * ((c + s) % 4),
                        "face_ratio": 1.0 if s % 2 else 0.0,
                        "subject_x": 0.62,
                    }
                    for s in range(segments)
                ],
            }
            for c in range(clips)
        ]
    }


def info(text: str, title: str = "", prompt: str = "") -> ProductInfo:
    return ProductInfo(title=title, text=text, url="", prompt=prompt)


def test_features_split_lines_and_drop_name() -> None:
    name, features, notes = product_features(
        info(
            "Hydrating face cream\nLightweight, non-greasy texture\nAbsorbs in seconds",
            title="Hydrating face cream",
        )
    )
    assert name == "Hydrating face cream"
    assert features == ["Lightweight, non-greasy texture", "Absorbs in seconds"]
    assert notes == []


def test_long_lines_are_split_on_commas() -> None:
    _, features, _ = product_features(
        info("Chair. Soft teddy fabric, 135° reclining, built-in footrest, foldable armrests")
    )
    assert features == [
        "Soft teddy fabric",
        "135° reclining",
        "Built-in footrest",
        "Foldable armrests",
    ]


def test_persian_text_is_flagged() -> None:
    name, features, notes = product_features(info("کرم آبرسان صورت", prompt="یه ویدیوی آرام"))
    assert name == "new favorite"
    assert features == []
    assert any("Persian" in n for n in notes)
    assert any("prompt" in n for n in notes)


def test_three_distinct_valid_variants() -> None:
    music = [PlanMusic(path="music/a.mp3", title="a"), PlanMusic(path="music/b.mp3", title="b")]
    plans = plan_variants(analysis(), info("Cream\nNon-greasy\nAbsorbs fast\n72h moisture"), music)
    assert [p.strategy for p in plans] == ["hook", "story", "vibe"]
    assert plans[0].music and plans[1].music and plans[0].music.path != plans[1].music.path
    for plan in plans:
        assert 8 <= plan.duration <= 30
        assert plan.texts[0].start < 1.0
        assert plan.texts[-1].text.startswith("Link below the video")
        assert plan.texts[-1].end == pytest.approx(plan.duration, abs=0.01)
        for a, b in zip(plan.texts, plan.texts[1:], strict=False):
            assert a.end <= b.start + 1e-6, "texts must not overlap"
        consecutive = zip(plan.segments, plan.segments[1:], strict=False)
        assert all(a != b for a, b in consecutive)
        assert "Pr sample, no payment received." in plan.caption
    story = plans[1].segments
    assert [s.clip_id for s in story] == sorted(s.clip_id for s in story)


def test_horizontal_clips_use_subject_crop() -> None:
    plan = plan_variants(analysis(), info("Cream"), [])[0]
    for seg in plan.segments:
        expected = 0.62 if seg.clip_id in ("c1",) else 0.5
        assert seg.crop_x == pytest.approx(expected)
