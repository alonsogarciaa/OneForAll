import numpy as np


def test_blocks_and_crossfades_reconstruct_the_signal(monkeypatch):
    """With an identity 'model', block processing + cross-fades must give back the input exactly."""
    import demucs.apply

    from djengine.stems import demucs_sep as m
    from djengine.stems.names import STEMS

    class Fake:
        sources = ["drums", "bass", "other", "vocals", "guitar", "piano"]

    def identity(model, seg, **k):
        return seg[:, None].repeat(1, len(Fake.sources), 1, 1)

    monkeypatch.setattr(demucs.apply, "apply_model", identity)
    sep = m.DemucsSeparator()
    sep._model = Fake()
    sr = 1000  # small rate keeps the test fast; block/fade scale with sr
    rng = np.random.default_rng(0)
    audio = rng.normal(0, 0.3, (2, 130 * sr)).astype(np.float32)
    steps = []
    out = sep.separate(audio, sr, steps.append, lambda: False)
    assert len(steps) == 3 and steps[-1] == 1.0
    for s in STEMS:
        assert np.allclose(out[s], audio, atol=1e-5)
