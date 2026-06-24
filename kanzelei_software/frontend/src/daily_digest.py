#!/usr/bin/env python3
# ============================================================
# KANZLEI AI — DAILY DIGEST EMAIL v1.0
# Datei: scripts/daily_digest.py
#
# Sendet jeden Morgen eine Email-Zusammenfassung:
#   - Kritische Mandanten
#   - Heutige Fristen
#   - Überfällige Aufgaben
#   - KI-Empfehlungen
#   - Completion-Rate der Woche
#
# Cron-Job einrichten:
#   0 7 * * 1-5 python3 /pfad/zu/scripts/daily_digest.py
#   (Montag-Freitag, 7:00 Uhr)
# ============================================================

import sys
import os
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.daten_speicher import DatenSpeicher
from core.engine import Engine
from core.decision_engine import analysiere_alle, berechne_score

log = logging.getLogger("daily_digest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

ds     = DatenSpeicher()
engine = Engine(ds)


def erstelle_html_digest() -> str:
    """Erstellt den HTML-Body für den Daily Digest."""
    jetzt     = datetime.now()
    mandanten = ds.hole_mandanten()
    aufgaben  = ds.hole_fristen()
    analyse   = analysiere_alle(ds)

    # ── Kritische & Wichtige Mandanten ────────────────────────
    kritisch = [m for m in analyse["mandanten"] if m["status"] == "KRITISCH"]
    wichtig  = [m for m in analyse["mandanten"] if m["status"] == "WICHTIG"]

    # ── Heutige Fristen ───────────────────────────────────────
    heute        = []
    ueberfaellig = []
    diese_woche  = []

    for a in aufgaben.values():
        if a.get("erledigt"):
            continue
        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            tage  = (frist - jetzt).days
            if tage < 0:
                ueberfaellig.append({**a, "tage": tage})
            elif tage == 0:
                heute.append({**a, "tage": 0})
            elif tage <= 7:
                diese_woche.append({**a, "tage": tage})
        except Exception:
            continue

    # ── Statistiken ───────────────────────────────────────────
    gesamt_aufgaben  = len(aufgaben)
    erledigt_aufgaben = sum(1 for a in aufgaben.values() if a.get("erledigt"))
    completion_rate  = round(erledigt_aufgaben / gesamt_aufgaben * 100, 1) if gesamt_aufgaben else 0
    total_umsatz     = sum(m.get("umsatz", 0) for m in mandanten.values())

    # ── HTML Template ─────────────────────────────────────────
    def status_chip(label, farbe):
        return f'<span style="background:{farbe}20;color:{farbe};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;text-transform:uppercase">{label}</span>'

    def aufgabe_row(a):
        tage = a.get("tage", 0)
        farbe = "#e05555" if tage < 0 else "#e08c45" if tage <= 2 else "#5b8de8"
        label = f"{abs(tage)}d überfällig" if tage < 0 else "Heute" if tage == 0 else f"in {tage}d"
        return f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:13px">{a.get("mandant","?")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:13px">{a.get("beschreibung","?")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:13px">{a.get("frist","?")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{status_chip(label, farbe)}</td>
        </tr>"""

    kritisch_html = ""
    for m in kritisch[:5]:
        empf = m.get("entscheidungen", [{}])[0].get("text", "") if m.get("entscheidungen") else ""
        kritisch_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:13px;font-weight:600">{m["mandant"]}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:13px">€{m.get("umsatz",0):,.0f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:12px;color:#555">{empf[:80]}</td>
        </tr>"""

    html = f"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:640px;margin:0 auto;padding:20px">

  <!-- HEADER -->
  <div style="background:#0b0d11;border-radius:16px 16px 0 0;padding:28px 32px">
    <div style="font-size:22px;color:#c8a96e;font-weight:700">Kanzlei Automation</div>
    <div style="font-size:14px;color:#8b91a0;margin-top:4px">
      Daily Digest — {jetzt.strftime("%A, %d. %B %Y")}
    </div>
  </div>

  <!-- KPI STRIP -->
  <div style="background:#111419;padding:20px 32px;display:flex;gap:0;border-bottom:1px solid #222">
    <table width="100%"><tr>
      <td style="text-align:center;padding:0 8px">
        <div style="font-size:28px;font-weight:700;color:#c8a96e">{len(mandanten)}</div>
        <div style="font-size:11px;color:#555d6e;text-transform:uppercase;letter-spacing:1px">Mandanten</div>
      </td>
      <td style="text-align:center;padding:0 8px">
        <div style="font-size:28px;font-weight:700;color:{"#e05555" if kritisch else "#5cb87a"}">{len(kritisch)}</div>
        <div style="font-size:11px;color:#555d6e;text-transform:uppercase;letter-spacing:1px">Kritisch</div>
      </td>
      <td style="text-align:center;padding:0 8px">
        <div style="font-size:28px;font-weight:700;color:{"#e05555" if ueberfaellig else "#5cb87a"}">{len(ueberfaellig)}</div>
        <div style="font-size:11px;color:#555d6e;text-transform:uppercase;letter-spacing:1px">Überfällig</div>
      </td>
      <td style="text-align:center;padding:0 8px">
        <div style="font-size:28px;font-weight:700;color:#5cb87a">{completion_rate}%</div>
        <div style="font-size:11px;color:#555d6e;text-transform:uppercase;letter-spacing:1px">Completion</div>
      </td>
    </tr></table>
  </div>

  <!-- CONTENT -->
  <div style="background:#fff;border-radius:0 0 16px 16px;overflow:hidden">

    {"" if not (heute or ueberfaellig) else f'''
    <!-- HEUTE & ÜBERFÄLLIG -->
    <div style="padding:24px 32px 0">
      <div style="font-size:16px;font-weight:700;color:#1a1a2e;margin-bottom:14px">
        {"🔥 Heute & Überfällig" if heute or ueberfaellig else ""}
      </div>
      <table width="100%" style="border-collapse:collapse">
        <tr style="background:#f8f9fa">
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Mandant</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Aufgabe</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Frist</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Status</th>
        </tr>
        {"".join(aufgabe_row(a) for a in (ueberfaellig + heute)[:8])}
      </table>
    </div>
    '''}

    {"" if not kritisch else f'''
    <!-- KRITISCHE MANDANTEN -->
    <div style="padding:24px 32px 0">
      <div style="font-size:16px;font-weight:700;color:#1a1a2e;margin-bottom:14px">
        ⚠ Kritische Mandanten ({len(kritisch)})
      </div>
      <table width="100%" style="border-collapse:collapse">
        <tr style="background:#f8f9fa">
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Mandant</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Umsatz</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#888;text-transform:uppercase">Empfehlung</th>
        </tr>
        {kritisch_html}
      </table>
    </div>
    '''}

    {"" if not diese_woche else f'''
    <!-- DIESE WOCHE -->
    <div style="padding:24px 32px 0">
      <div style="font-size:16px;font-weight:700;color:#1a1a2e;margin-bottom:14px">
        📅 Diese Woche fällig ({len(diese_woche)})
      </div>
      <table width="100%" style="border-collapse:collapse">
        {"".join(aufgabe_row(a) for a in diese_woche[:6])}
      </table>
    </div>
    '''}

    <!-- FOOTER -->
    <div style="padding:24px 32px;background:#f8f9fa;margin-top:24px">
      <div style="font-size:12px;color:#888;line-height:1.7">
        Dieser Digest wird automatisch von Kanzlei Automation generiert.<br>
        Gesamtumsatz Kanzlei: <strong>€{total_umsatz:,.0f}</strong> | 
        Aufgaben erledigt: <strong>{erledigt_aufgaben}/{gesamt_aufgaben}</strong> ({completion_rate}%)<br>
        <a href="http://localhost:3000" style="color:#c8a96e">→ Kanzlei Automation öffnen</a>
      </div>
    </div>

  </div>
</div>
</body>
</html>
"""
    return html


def sende_digest(empfaenger: str) -> bool:
    """Digest per Email senden."""
    sender   = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender or not password:
        log.error("EMAIL_USER / EMAIL_PASS fehlen in .env")
        return False

    jetzt = datetime.now()
    html  = erstelle_html_digest()

    msg           = MIMEMultipart("alternative")
    msg["From"]   = sender
    msg["To"]     = empfaenger
    msg["Subject"] = f"Kanzlei Automation — Daily Digest {jetzt.strftime('%d.%m.%Y')}"

    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        log.info(f"Daily Digest gesendet an {empfaenger}")
        ds.log_eintrag(f"DAILY_DIGEST_GESENDET | {empfaenger}")
        return True
    except Exception as e:
        log.error(f"Digest Email Fehler: {e}")
        return False


if __name__ == "__main__":
    # Empfänger aus .env oder Argument
    empfaenger = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DIGEST_EMAIL", "")

    if not empfaenger:
        print("Verwendung: python daily_digest.py empfaenger@kanzlei.de")
        print("Oder DIGEST_EMAIL in .env setzen")
        sys.exit(1)

    print(f"Sende Daily Digest an {empfaenger}...")
    erfolg = sende_digest(empfaenger)
    sys.exit(0 if erfolg else 1)