"""Smoke: automation_router ruft api.bot_analyse mit korrekter Signatur auf."""
from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.routes import automation_router as ar  # noqa: E402


def _api_bot_analyse_param_names() -> list[str]:
    api_py = ROOT / "api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "bot_analyse":
            return [a.arg for a in node.args.args]
    raise AssertionError("bot_analyse in api.py nicht gefunden")


def main() -> int:
    params = _api_bot_analyse_param_names()
    assert params == ["_user"], f"api.bot_analyse Signatur unerwartet: {params}"

    src = inspect.getsource(ar.bot_analyse)
    assert "background_tasks" not in src
    assert re.search(r"bot_analyse\s*\(\s*_user\s*\)", src), "Router muss root.bot_analyse(_user) aufrufen"
    print("ok: bot_analyse router wiring")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
