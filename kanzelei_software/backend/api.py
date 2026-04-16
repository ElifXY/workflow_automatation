import os
import sys

# Ensure project root is importable when running backend.api:app
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import app  # noqa: E402,F401
