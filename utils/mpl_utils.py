"""
Matplotlib helper utilities to ensure non-interactive backend in worker threads.
"""

from __future__ import annotations


def import_pyplot_non_interactive():
    """Import matplotlib.pyplot with a non-interactive backend (Agg).

    Safe to call from worker threads. Returns the pyplot module or raises ImportError
    if matplotlib is unavailable.
    """
    import matplotlib as mpl
    try:
        backend = mpl.get_backend().lower()  # type: ignore[attr-defined]
    except Exception:
        backend = ""
    if "agg" not in backend:
        try:
            mpl.use("Agg", force=True)  # type: ignore[attr-defined]
        except Exception:
            # If switching backend fails, proceed; pyplot import may still work
            pass
    import matplotlib.pyplot as plt  # type: ignore
    return plt


