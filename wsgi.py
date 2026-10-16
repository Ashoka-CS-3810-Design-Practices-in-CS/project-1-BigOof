"""Vercel entrypoint: Vercel auto-detects ``wsgi.py`` and serves its ``app``.

The package lives under ``src/``, so put that on the path rather than relying on
the project itself being installed in the deployment.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from big_o.app import app  # noqa: E402

__all__ = ["app"]
