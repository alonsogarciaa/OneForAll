"""Stub for a Cython module OneForAll does not build (not used by the key CNN).

Any attribute resolves to a placeholder that fails loudly if actually used.
"""


def __getattr__(name):
    class _Unavailable:
        def __init__(self, *a, **k):
            raise RuntimeError(f"{__name__}.{name} needs madmom's compiled extensions, which OneForAll does not ship")

    _Unavailable.__name__ = name
    return _Unavailable
