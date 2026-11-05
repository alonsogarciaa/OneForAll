import numpy as np
import pytest

from tests.stems.test_runner import folder, run, song, svc  # noqa: F401  (fixtures)

SR = 44100


def test_runner_karaoke_writes_lead_and_backing(svc, ctx, song):  # noqa: F811
    r = run(svc, ctx, song, ["drums"], karaoke=True)
    assert set(r["stems"]) == {"drums", "vocals", "lead_vocals", "backing_vocals"}
    names = sorted(p.name for p in folder(svc).iterdir())
    assert names == ["backing_vocals.wav", "drums.wav", "lead_vocals.wav", "vocals.wav"]
    assert "karaoke" in [s[0] for s in ctx.reports]


@pytest.mark.slow
def test_real_uvr_karaoke(tmp_path):
    from djengine.stems.karaoke import UvrKaraoke

    t = np.arange(SR * 10) / SR
    voice = (0.3 * np.sin(2 * np.pi * 220 * t) * (1 + 0.3 * np.sin(2 * np.pi * 5 * t))).astype(np.float32)
    lead, backing = UvrKaraoke(tmp_path / "uvr").split(np.stack([voice, voice]), SR, tmp_path / "work")
    for y in (lead, backing):
        assert y.shape[0] == 2 and abs(y.shape[1] - len(voice)) <= len(voice) * 0.01
