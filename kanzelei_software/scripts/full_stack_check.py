#!/usr/bin/env python3
"""
Vollständige GO/NO-GO-Prüfung (soweit ohne laufenden Docker möglich).

Statisch:
  - genau ein Uvicorn-Ziel backend.application:app in docker-compose + dockerfile
  - nginx: worker_processes nur in nginx.conf (nicht in conf.d server-Dateien)
  - Pflicht-Dateien Nginx/TLS/Cloudflare

Optional (--docker):
  - docker compose config
  - docker compose build nginx
  - docker compose up -d, Warte auf /health, curl http(s), nginx -t, down

Nutzen:
  python scripts/full_stack_check.py
  python scripts/full_stack_check.py --docker
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"OK:   {msg}")


def check_compose_uvicorn() -> bool:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8", errors="replace")
    hits = list(re.finditer(r"uvicorn\s+backend\.application:app", text))
    if len(hits) != 1:
        _fail(f"docker-compose.yml: erwarte genau 1× 'uvicorn backend.application:app', gefunden {len(hits)}")
        return False
    _ok("docker-compose.yml: genau ein uvicorn backend.application:app")
    return True


def check_dockerfile_cmd() -> bool:
    text = (ROOT / "dockerfile").read_text(encoding="utf-8", errors="replace")
    if "backend.application:app" not in text:
        _fail("dockerfile: backend.application:app fehlt in CMD")
        return False
    _ok("dockerfile: CMD enthält backend.application:app")
    return True


def check_nginx_worker_processes() -> bool:
    main = (ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8", errors="replace")
    if "worker_processes" not in main:
        _fail("nginx.conf: worker_processes fehlt")
        return False
    bad = []
    for p in (ROOT / "nginx" / "conf.d").glob("*.conf"):
        if p.name.startswith("00-"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(t.splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if re.match(r"worker_processes\b", s):
                bad.append(f"{p.name}:{i}")
    if bad:
        _fail(f"worker_processes in conf.d (verboten): {', '.join(bad)}")
        return False
    _ok("nginx: worker_processes nur in nginx.conf, nicht in conf.d server-*.conf")
    return True


def check_nginx_tls_and_maps() -> bool:
    need = [
        ROOT / "nginx" / "conf.d" / "10-localhost-https.conf",
        ROOT / "nginx" / "docker-entrypoint.sh",
        ROOT / "Dockerfile.nginx",
        ROOT / "nginx" / "snippets" / "proxy_params.conf",
    ]
    for p in need:
        if not p.is_file():
            _fail(f"fehlt: {p.relative_to(ROOT)}")
            return False
    prod = (ROOT / "nginx" / "conf.d" / "00-http-globals.prod.conf").read_text(encoding="utf-8")
    dev = (ROOT / "nginx" / "conf.d" / "00-http-globals.dev.conf").read_text(encoding="utf-8")
    if "map $http_x_forwarded_proto $forwarded_proto" not in prod or "map $http_x_forwarded_proto $forwarded_proto" not in dev:
        _fail("http-globals: map forwarded_proto fehlt")
        return False
    if "$forwarded_proto" not in (ROOT / "nginx" / "snippets" / "proxy_params.conf").read_text(encoding="utf-8"):
        _fail("proxy_params: $forwarded_proto fehlt")
        return False
    _ok("nginx: TLS-localhost-Dateien, Entrypoint, Dockerfile, forwarded_proto Map/Snippets")
    return True


def check_python_imports() -> bool:
    try:
        from backend.application import app  # noqa: F401

        assert app.title
    except Exception as e:
        _fail(f"Import backend.application:app: {e}")
        return False
    _ok(f"Python: backend.application:app importiert ({app.title!r})")
    return True


def _which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def run_docker_checks() -> bool:
    if not _which("docker"):
        _fail("docker nicht im PATH — statische Prüfungen ok; für Stack: Docker installieren")
        return False
    env = dict(**__import__("os").environ)
    env.setdefault("COMPOSE_HTTP_TIMEOUT", "300")
    steps = [
        (["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "config", "-q"], "compose config -q"),
        (["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "build", "nginx"], "compose build nginx"),
    ]
    for cmd, label in steps:
        print(f"\n--- {label} ---")
        r = subprocess.run(cmd, cwd=ROOT, env=env)
        if r.returncode != 0:
            _fail(f"{label} exit {r.returncode}")
            return False
        _ok(label)

    # docker-compose.yml: kanzlei_network ist external — auf frischer CI-Maschine anlegen.
    subprocess.run(
        ["docker", "network", "create", "kanzlei_network"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    up = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "up", "-d"],
        cwd=ROOT,
        env=env,
    )
    if up.returncode != 0:
        _fail(f"compose up exit {up.returncode}")
        return False
    _ok("compose up -d")

    import time
    import urllib.error
    import urllib.request

    health_url = "http://127.0.0.1:8000/health"
    for i in range(90):
        try:
            with urllib.request.urlopen(health_url, timeout=3) as r:
                if r.status == 200:
                    break
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    else:
        _fail("API /health nicht erreichbar nach Wartezeit")
        subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "ps"], cwd=ROOT)
        subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "logs", "--tail=80", "api"], cwd=ROOT)
        subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "down", "--remove-orphans"], cwd=ROOT)
        return False
    _ok("API GET /health")

    for label, url in (
        ("nginx HTTP /", "http://127.0.0.1:80/"),
        ("nginx HTTPS localhost (insecure)", "https://127.0.0.1:443/"),
    ):
        try:
            import ssl

            ctx = ssl.create_default_context()
            if url.startswith("https"):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, timeout=10, context=ctx if url.startswith("https") else None) as r:
                body = r.read(8000).decode("utf-8", errors="ignore").lower()
        except Exception as e:
            _fail(f"{label} {url}: {e}")
            subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "logs", "--tail=80", "nginx"], cwd=ROOT)
            subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "down", "--remove-orphans"], cwd=ROOT)
            return False
        if "html" not in body and "react" not in body and "<!doctype" not in body:
            _fail(f"{label}: Antwort sieht nicht nach SPA aus (first bytes)")
            subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "down", "--remove-orphans"], cwd=ROOT)
            return False
        _ok(f"{label} SPA-ähnliche Antwort")

    nt = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "exec", "-T", "nginx", "nginx", "-t"],
        cwd=ROOT,
        env=env,
    )
    down = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "down", "--remove-orphans"],
        cwd=ROOT,
        env=env,
    )
    if nt.returncode != 0:
        _fail(f"nginx -t exit {nt.returncode}")
        return False
    _ok("nginx -t im Container")
    if down.returncode != 0:
        _fail(f"compose down exit {down.returncode}")
        return False
    _ok("compose down -v")
    return True


def main() -> int:
    import os

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    p = argparse.ArgumentParser()
    p.add_argument("--docker", action="store_true", help="Docker Compose Build/Up/Curl (braucht Docker)")
    args = p.parse_args()
    ok = True
    ok &= check_compose_uvicorn()
    ok &= check_dockerfile_cmd()
    ok &= check_nginx_worker_processes()
    ok &= check_nginx_tls_and_maps()
    ok &= check_python_imports()
    if args.docker:
        ok &= run_docker_checks()
    else:
        print("\nHinweis: ohne --docker keine Container-Tests. CI: .github/workflows/docker-stack-verify.yml")
    print("\n" + ("ALLE STATISCHEN PRÜFUNGEN BESTANDEN" if ok else "MINdestens eine Prüfung fehlgeschlagen"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
