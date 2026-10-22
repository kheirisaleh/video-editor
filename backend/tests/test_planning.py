import re

import pytest

from studio.analysis.beats import BeatInfo
from studio.options import RenderOptions
from studio.planning.baseline import (
    MusicChoice,
    ProductInfo,
    exposure_gammas,
    plan_variants,
    product_features,
)
from studio.planning.schema import PlanMusic

EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿]")


def analysis(clips: int = 4, segments: int = 4, face_y: float | None = None) -> dict:
    return {
        "clips": [
            {
                "clip_id": f"c{c}",
                "source_width": 1280 if c % 2 else 720,
                "source_height": 720 if c % 2 else 1280,
                "segments": [
                    {
                        "start": s * 3.5,
                        "end": s * 3.5 + 3.0,
                        "score": 0.5 + 0.1 * ((c + s) % 4),
                        "face_ratio": 1.0 if s % 2 else 0.0,
                        "subject_x": 0.62,
                        "brightness": 90.0 + 20 * c,
                        "face_y": face_y,
                    }
                    for s in range(segments)
                ],
            }
            for c in range(clips)
        ]
    }


def info(
    text: str = "Cream\nNon-greasy\nAbsorbs fast\n72h moisture\nWith ceramides",
    title: str = "",
    prompt: str = "",
) -> ProductInfo:
    return ProductInfo(title=title, text=text, url="", prompt=prompt)


def music(bpm: float = 100.0, name: str = "a") -> MusicChoice:
    period = 60.0 / bpm
    beats = [round(0.4 + i * period, 3) for i in range(200)]
    return MusicChoice(
        PlanMusic(path=f"music/{name}.mp3", title=name),
        BeatInfo(tempo=bpm, beats=beats, duration=120.0, intro_end=0.0, downbeats=beats[::4]),
    )


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


@pytest.mark.parametrize(("lo", "hi"), [(10, 15), (12, 30), (20, 40), (25, 25)])
def test_every_variant_respects_the_length_range(lo: float, hi: float) -> None:
    options = RenderOptions(min_duration=lo, max_duration=hi)
    plans = plan_variants(analysis(clips=6), info(), options, [music()])
    assert len(plans) == 3
    for plan in plans:
        assert lo - 0.05 <= plan.duration <= hi + 0.05, (plan.strategy, plan.duration)
    hook, story, vibe = plans
    if hi - lo >= 5:
        assert hook.duration < vibe.duration < story.duration


def test_cuts_land_on_beats() -> None:
    choice = music(bpm=96)
    plan = plan_variants(analysis(), info(), RenderOptions(), [choice])[0]
    assert plan.music is not None
    start = plan.music.start
    beats = [b - start for b in choice.beats.beats if b > start]  # type: ignore[union-attr]
    t = 0.0
    for seg in plan.segments:
        t += seg.duration
        assert min(abs(t - b) for b in beats) < 0.01, f"cut at {t:.3f} is off beat"


def test_without_music_or_beat_sync() -> None:
    no_music = plan_variants(analysis(), info(), RenderOptions(music=False), [])
    assert all(p.music is None for p in no_music)
    free = plan_variants(analysis(), info(), RenderOptions(beat_sync=False), [music()])
    assert free[0].music is not None


def test_text_switches() -> None:
    plans = plan_variants(analysis(), info(), RenderOptions(texts=False), [])
    assert all(p.texts == [] for p in plans)

    plans = plan_variants(analysis(), info(), RenderOptions(emoji=False), [])
    for plan in plans:
        assert plan.texts
        assert not any(EMOJI.search(t.text) for t in plan.texts)

    plans = plan_variants(analysis(), info(), RenderOptions(call_to_action=False), [])
    for plan in plans:
        assert not any("Link below" in t.text for t in plan.texts)
        assert "Link below" not in plan.caption


def test_texts_are_readable_and_do_not_overlap() -> None:
    for plan in plan_variants(analysis(), info(), RenderOptions(), [music()]):
        assert plan.texts[0].start < 0.5
        assert plan.texts[-1].text.startswith("Link below the video")
        assert plan.texts[-1].end == pytest.approx(plan.duration, abs=0.01)
        for a, b in zip(plan.texts, plan.texts[1:], strict=False):
            assert a.end <= b.start + 1e-6
        for text in plan.texts:
            assert text.end - text.start >= 1.0


def test_text_moves_away_from_faces() -> None:
    plans = plan_variants(analysis(face_y=0.55), info(), RenderOptions(), [])
    for plan in plans:
        for text in plan.texts:
            assert abs(text.y - 0.55) >= 0.17


def test_style_variants_and_overrides() -> None:
    plans = plan_variants(analysis(), info(), RenderOptions(), [])
    assert [p.style for p in plans] == ["sans", "sans", "serif"]
    assert plans[2].texts[0].animation == "typewriter"
    plans = plan_variants(analysis(), info(), RenderOptions(text_style="serif", variants=2), [])
    assert [p.style for p in plans] == ["serif", "serif"]


def test_short_footage_is_reported() -> None:
    plans = plan_variants(
        analysis(clips=1, segments=2), info(), RenderOptions(min_duration=20, max_duration=30), []
    )
    assert plans[0].duration < 20
    assert any("Not enough usable footage" in n for n in plans[0].notes)


def test_caption_uses_options() -> None:
    options = RenderOptions(hashtags=["skincare", "#glow"], disclosure="Ad")
    plan = plan_variants(analysis(), info(title="Face cream"), options, [])[0]
    assert "#facecream #skincare #glow" in plan.caption
    assert plan.caption.endswith("\n\nAd")


def test_exposure_matching_brightens_dark_and_darkens_bright() -> None:
    plans = plan_variants(analysis(), info(), RenderOptions(), [])
    gammas = [s.gamma for p in plans for s in p.segments]
    assert min(gammas) < 1.0 < max(gammas)


def test_exposure_gammas_are_neutral_for_equal_shots() -> None:
    class C:
        brightness = 128.0

    class S:
        cand = C()

    assert exposure_gammas([S(), S()]) == [1.0, 1.0]  # type: ignore[list-item]


def test_options_validation() -> None:
    with pytest.raises(ValueError):
        RenderOptions(min_duration=40, max_duration=20)
    assert RenderOptions(hashtags=[" glow ", ""]).hashtags == ["#glow"]
