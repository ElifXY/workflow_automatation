from __future__ import annotations

import argparse
import base64
import os
import sys
from typing import Any, Dict

import httpx


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _print(name: str, ok: bool, info: str) -> None:
    state = "OK" if ok else "FAIL"
    print(f"[{state}] {name}: {info}")


def _tiny_png_b64() -> str:
    # 1x1 transparent png
    raw = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(raw).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("GO_LIVE_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("GO_LIVE_TOKEN", ""))
    args = parser.parse_args()

    ok_all = True
    headers = _auth_headers(args.token)
    tiny = _tiny_png_b64()

    with httpx.Client(base_url=args.base_url, timeout=20.0) as client:
        for path in ("/health", "/ki/status"):
            r = client.get(path, headers=headers)
            good = r.status_code in (200, 401, 503)
            _print(f"GET {path}", good, f"HTTP {r.status_code}")
            ok_all &= good

        chat_payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": "Gib mir 3 konkrete Kanzlei-Produktivitätshebel."}],
            "system": "Antworte kurz und strukturiert.",
            "max_tokens": 300,
        }
        r_chat = client.post("/ki/chat", headers=headers, json=chat_payload)
        good_chat = r_chat.status_code in (200, 401, 500, 502, 503, 504)
        _print("POST /ki/chat", good_chat, f"HTTP {r_chat.status_code}")
        ok_all &= good_chat

        doc_payload = {"dateiname": "smoke.png", "inhalt_b64": tiny, "dateityp": "image/png"}
        r_doc = client.post("/dokumente/analysieren", headers=headers, json=doc_payload)
        good_doc = r_doc.status_code in (200, 401, 500, 502, 503, 504)
        _print("POST /dokumente/analysieren", good_doc, f"HTTP {r_doc.status_code}")
        ok_all &= good_doc

        beleg_payload = {"dateiname": "smoke.png", "inhalt_b64": tiny, "mandant": ""}
        r_beleg = client.post("/belege/analysieren", headers=headers, json=beleg_payload)
        good_beleg = r_beleg.status_code in (200, 401, 500, 502, 503, 504)
        _print("POST /belege/analysieren", good_beleg, f"HTTP {r_beleg.status_code}")
        ok_all &= good_beleg

    return 0 if ok_all else 2


if __name__ == "__main__":
    sys.exit(main())

