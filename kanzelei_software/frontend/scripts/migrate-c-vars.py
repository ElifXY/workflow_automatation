# -*- coding: utf-8 -*-
"""Replace legacy C.* palette tokens with CSS variables in page components."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "pages"
FILES = [
    "WorkflowBaukasten.js",
    "KIAssistent.js",
    "SteuerAutopilot.js",
    "BelegScanner.js",
    "MandantDetail.js",
    "DokumentScanner.js",
]

C_BLOCK = re.compile(
    r"const C = \{[\s\S]*?\};\n\n",
    re.MULTILINE,
)


def strip_c_block(text: str) -> str:
    return C_BLOCK.sub("", text, count=1)


def main():
    for name in FILES:
        path = ROOT / name
        if not path.exists():
            print("skip missing", path)
            continue
        s = path.read_text(encoding="utf-8")
        if "const C = {" not in s:
            print("skip no C", name)
            continue
        s = strip_c_block(s)
        # template literals
        s = s.replace("${C.border2}", "var(--border2)")
        s = s.replace("${C.border}", "var(--border)")
        # longest keys first
        for a, b in [
            ("C.text3", '"var(--text3)"'),
            ("C.text2", '"var(--text2)"'),
            ("C.text", '"var(--text)"'),
            ("C.bg3", '"var(--bg3)"'),
            ("C.bg2", '"var(--bg2)"'),
            ("C.bg", '"var(--bg)"'),
            ("C.accent", '"var(--accent)"'),
            ("C.purple", '"var(--purple)"'),
            ("C.orange", '"var(--orange)"'),
            ("C.green", '"var(--green)"'),
            ("C.red", '"var(--red)"'),
            ("C.blue", '"var(--blue)"'),
        ]:
            s = s.replace(a, b)
        path.write_text(s, encoding="utf-8")
        print("ok", name)


if __name__ == "__main__":
    main()
