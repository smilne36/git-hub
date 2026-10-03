import numpy as np
import pytest
import soundfile as sf

from tests.synth import make_track
from transitions.analyze import analyze_file
from transitions.keys import camelot, camelot_compat
from transitions.match import plan_transition, rank, tempo_relation
from transitions.render import render


def test_camelot_codes():
    assert camelot(0, False) == "8B"   # C major
    assert camelot(9, True) == "8A"    # A minor
    assert camelot(4, True) == "9A"    # E minor
    assert camelot(11, False) == "1B"  # B major
    assert camelot_compat("8A", "9A")[0] > camelot_compat("8A", "3B")[0]
    assert camelot_compat("12A", "1A")[1] == "adjacent on Camelot wheel"


def test_tempo_relation_half_time():
    pct, m, rate = tempo_relation(140, 70)
    assert pct < 1e-9 and m == 2.0 and rate == pytest.approx(1.0)


@pytest.fixture(scope="module")
def tracks(tmp_path_factory):
    d = tmp_path_factory.mktemp("lib")
    specs = {
        "mine_124_Am": dict(bpm=124, root="A"),
        "house_125_Em": dict(bpm=125, root="E"),
        "house_124_Am": dict(bpm=124, root="A"),
        "techno_138_Fm": dict(bpm=138, root="F", seconds=80),
        "dancehall_95_Gm": dict(bpm=95, root="G", fade_out=10, ambient_intro=8),
    }
    out = {}
    for name, kw in specs.items():
        p = d / f"{name}.wav"
        make_track(p, **kw)
        out[name] = analyze_file(p)
    return out


def test_analysis(tracks):
    assert tracks["mine_124_Am"].bpm == pytest.approx(124, abs=1.0)
    assert tracks["dancehall_95_Gm"].bpm == pytest.approx(95, abs=1.5)
    assert tracks["mine_124_Am"].key == "Am"
    assert tracks["house_125_Em"].key == "Em"
    assert tracks["dancehall_95_Gm"].outro_type == "fade"
    assert tracks["mine_124_Am"].outro_type == "beat"


def test_ranking_prefers_compatible(tracks):
    song = tracks["mine_124_Am"]
    before, after = rank(song, list(tracks.values()))
    assert after[0].incoming.title in ("house_124_Am", "house_125_Em")
    assert after[-1].incoming.title in ("dancehall_95_Gm", "techno_138_Fm")
    assert after[0].plan.style == "blend"


def test_plan_styles(tracks):
    mine = tracks["mine_124_Am"]
    p = plan_transition(mine, tracks["house_125_Em"])
    assert p.style == "blend" and p.out_start + p.overlap <= mine.end + 1e-6
    # Downbeat-aligned mix-out point.
    assert min(abs(p.out_start - d) for d in mine.downbeats) < 1e-6
    assert plan_transition(mine, tracks["dancehall_95_Gm"]).style == "echo_out"
    assert plan_transition(tracks["dancehall_95_Gm"], mine).style == "fade"


@pytest.mark.parametrize("a,b", [("mine_124_Am", "house_125_Em"),
                                 ("mine_124_Am", "dancehall_95_Gm"),
                                 ("dancehall_95_Gm", "mine_124_Am")])
def test_render(tracks, tmp_path, a, b):
    from transitions.match import score_pair

    m = score_pair(tracks[a], tracks[b])
    out = render(m, tmp_path / "preview", lead=5, tail=5)
    y, sr = sf.read(out)
    assert len(y) / sr >= 10
    assert np.max(np.abs(y)) <= 1.0
    assert np.isfinite(y).all()
