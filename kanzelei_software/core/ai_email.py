# ============================================================
# KANZLEI AI — EMAIL GENERATOR v3.0
# Professionelle HTML-Emails + Plain-Text Fallback
# ============================================================

from datetime import datetime
from typing import Optional, Dict, List
import logging

log = logging.getLogger(__name__)


def _ton(umsatz: float, tage: int, ueberfaellig: int, score: float) -> str:
    if umsatz >= 500000:
        return "premium_dringend" if (ueberfaellig > 0 or tage >= 14) else "premium"
    if ueberfaellig > 0 or tage >= 14:
        return "dringend"
    if tage >= 7 or score >= 5000:
        return "nachdrücklich"
    if tage >= 3:
        return "hoeflich"
    return "freundlich"


def _html_email(
    mandant:        str,
    ton:            str,
    aufgaben_text:  str,
    dokumente_text: str,
    tage_text:      str,
    kanzlei_name:   str,
    kanzlei_email:  str,
) -> str:
    """Erstellt professionelle HTML-Email."""

    farben = {
        "freundlich":      {"accent": "#5b8de8", "label": "Information"},
        "hoeflich":        {"accent": "#c8a96e", "label": "Erinnerung"},
        "nachdrücklich":   {"accent": "#e08c45", "label": "Wichtig"},
        "dringend":        {"accent": "#e05555", "label": "Dringend"},
        "premium":         {"accent": "#9b72e8", "label": "Information"},
        "premium_dringend":{"accent": "#e05555", "label": "Dringend"},
    }

    anreden = {
        "freundlich":       f"Sehr geehrte/r {mandant},",
        "hoeflich":         f"Sehr geehrte/r {mandant},",
        "nachdrücklich":    f"Sehr geehrte/r {mandant},",
        "dringend":         f"Sehr geehrte/r {mandant},",
        "premium":          f"Sehr geehrte/r {mandant},",
        "premium_dringend": f"Sehr geehrte/r {mandant},",
    }

    einleitungen = {
        "freundlich":       "wir hoffen, Sie sind wohlauf. Wir möchten Sie kurz über einige offene Punkte informieren.",
        "hoeflich":         "wir erlauben uns, Sie freundlich an folgende offene Punkte zu erinnern.",
        "nachdrücklich":    "wir möchten Sie auf wichtige offene Punkte aufmerksam machen, die Ihrer Aufmerksamkeit bedürfen.",
        "dringend":         "wir kontaktieren Sie wegen dringender offener Punkte, die sofortiges Handeln erfordern.",
        "premium":          "als geschätzten Mandanten möchten wir Sie über aktuelle Punkte informieren.",
        "premium_dringend": "als geschätzten Mandanten bitten wir Sie dringend, die folgenden Punkte zeitnah zu klären.",
    }

    c = farben.get(ton, farben["freundlich"])
    accent = c["accent"]
    label  = c["label"]

    body_parts = []
    if aufgaben_text:
        body_parts.append(f"""
        <div style="background:#f8f9fa;border-left:4px solid {accent};padding:16px;border-radius:0 8px 8px 0;margin:16px 0;">
          <strong style="color:{accent};">⏰ Offene Aufgaben</strong>
          <p style="margin:8px 0 0 0;color:#333;">{aufgaben_text}</p>
        </div>""")

    if dokumente_text:
        body_parts.append(f"""
        <div style="background:#f8f9fa;border-left:4px solid #5b8de8;padding:16px;border-radius:0 8px 8px 0;margin:16px 0;">
          <strong style="color:#5b8de8;">📄 Fehlende Unterlagen</strong>
          <p style="margin:8px 0 0 0;color:#333;">{dokumente_text}</p>
        </div>""")

    if tage_text:
        body_parts.append(f"""
        <div style="background:#fff3cd;border-left:4px solid #e08c45;padding:16px;border-radius:0 8px 8px 0;margin:16px 0;">
          <strong style="color:#e08c45;">📞 Kontakt</strong>
          <p style="margin:8px 0 0 0;color:#333;">{tage_text}</p>
        </div>""")

    body_html = "".join(body_parts) if body_parts else """
        <div style="background:#d4edda;border-left:4px solid #5cb87a;padding:16px;border-radius:0 8px 8px 0;margin:16px 0;">
          <strong style="color:#5cb87a;">✅ Alles in Ordnung</strong>
          <p style="margin:8px 0 0;color:#333;">Aktuell liegen keine offenen Punkte vor.</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nachricht von {kanzlei_name}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1);">

        <!-- Header -->
        <tr>
          <td style="background:{accent};padding:28px 32px;">
            <div style="color:rgba(255,255,255,0.8);font-size:12px;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px;">{label}</div>
            <div style="color:#ffffff;font-size:24px;font-weight:700;">{kanzlei_name}</div>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;">
            <p style="font-size:16px;color:#333;margin:0 0 8px 0;">{anreden.get(ton, anreden["freundlich"])}</p>
            <p style="font-size:14px;color:#666;margin:0 0 20px 0;line-height:1.7;">{einleitungen.get(ton, einleitungen["freundlich"])}</p>

            {body_html}

            <p style="font-size:14px;color:#666;margin:20px 0 0 0;line-height:1.7;">
              Bei Fragen stehen wir Ihnen jederzeit zur Verfügung.
            </p>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:0 32px 24px;">
            <a href="mailto:{kanzlei_email}" style="display:inline-block;background:{accent};color:#ffffff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">
              Direkt antworten →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8f9fa;padding:20px 32px;border-top:1px solid #eee;">
            <p style="font-size:12px;color:#999;margin:0;line-height:1.6;">
              <strong style="color:#666;">Mit freundlichen Grüßen</strong><br>
              {kanzlei_name}<br>
              {kanzlei_email}<br>
              <span style="color:#bbb;font-size:11px;">Diese E-Mail wurde von Kanzlei AI generiert · {datetime.now().strftime("%d.%m.%Y")}</span>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _plain_email(
    mandant:        str,
    ton:            str,
    aufgaben_text:  str,
    dokumente_text: str,
    tage_text:      str,
    kanzlei_name:   str,
    kanzlei_email:  str,
) -> str:
    """Plain-Text Version als Fallback."""
    anreden = {
        "freundlich":       f"Sehr geehrte/r {mandant},\n\nwir hoffen, Sie sind wohlauf.",
        "hoeflich":         f"Sehr geehrte/r {mandant},\n\nwir erlauben uns, Sie zu erinnern.",
        "nachdrücklich":    f"Sehr geehrte/r {mandant},\n\nbitte beachten Sie folgende dringende Punkte.",
        "dringend":         f"Sehr geehrte/r {mandant},\n\nsofortiger Handlungsbedarf:",
        "premium":          f"Sehr geehrte/r {mandant},\n\nals geschätzter Mandant erhalten Sie diese Information.",
        "premium_dringend": f"Sehr geehrte/r {mandant},\n\nbitte klären Sie folgende Punkte dringend.",
    }

    body = anreden.get(ton, anreden["freundlich"]) + "\n\n"
    if aufgaben_text:  body += f"OFFENE AUFGABEN:\n{aufgaben_text}\n\n"
    if dokumente_text: body += f"FEHLENDE UNTERLAGEN:\n{dokumente_text}\n\n"
    if tage_text:      body += f"KONTAKT:\n{tage_text}\n\n"
    body += f"Bei Fragen stehen wir gerne zur Verfügung.\n\nMit freundlichen Grüßen\n{kanzlei_name}\n{kanzlei_email}"
    return body


def generate_ai_email(
    mandant:    str,
    m:          Dict,
    aufgaben:   Dict,
    ds,
) -> str:
    """Generiert professionelle HTML-Email für einen Mandanten."""
    import os

    kanzlei_name  = os.getenv("EMAIL_FROM", "Ihre Steuerkanzlei").split("<")[0].strip()
    kanzlei_email = os.getenv("EMAIL_USER", "kanzlei@kanzlei.de")

    umsatz       = float(m.get("umsatz", 0) or 0)
    fehlende     = m.get("fehlende_dokumente_liste", [])
    fehlende     = fehlende if isinstance(fehlende, list) else []

    try:
        tage = ds.berechne_tage_ohne_antwort(mandant)
    except Exception:
        tage = 0

    # Aufgaben analysieren
    meine = [a for a in aufgaben.values() if a.get("mandant") == mandant and not a.get("erledigt")]
    heute = datetime.now().strftime("%Y-%m-%d")
    ueberfaellig = [a for a in meine if a.get("frist", "9999") < heute]
    score_approx = len(ueberfaellig) * 3000 + tage * 100

    ton = _ton(umsatz, tage, len(ueberfaellig), score_approx)

    # Text-Bausteine
    aufgaben_text  = ""
    if ueberfaellig:
        namen = [a.get("beschreibung", "Aufgabe")[:50] for a in ueberfaellig[:3]]
        aufgaben_text = f"{len(ueberfaellig)} überfällige Aufgabe(n): {', '.join(namen)}"
    bald = [a for a in meine if heute <= a.get("frist","9999") <= (datetime.now().replace(day=datetime.now().day+3) if datetime.now().day <= 28 else datetime.now()).strftime("%Y-%m-%d")]
    if bald and not aufgaben_text:
        aufgaben_text = f"{len(bald)} Aufgabe(n) in den nächsten Tagen fällig."

    dokumente_text = ""
    if fehlende:
        dokumente_text = f"Bitte senden Sie uns: {', '.join(fehlende[:5])}"

    tage_text = ""
    if tage >= 14:
        tage_text = f"Seit {tage} Tagen haben wir keine Rückmeldung erhalten. Bitte melden Sie sich bei uns."
    elif tage >= 7:
        tage_text = f"Seit {tage} Tagen hatten wir keinen Kontakt. Wir freuen uns auf Ihre Nachricht."

    return _html_email(
        mandant, ton, aufgaben_text, dokumente_text, tage_text,
        kanzlei_name, kanzlei_email,
    )


def generiere_email_text(
    mandant:    str,
    grund:      str = "KEINE_ANTWORT",
    details:    Optional[list] = None,
    kanzlei_name: str = "Ihre Steuerkanzlei",
) -> str:
    """Plain-Text Email für einfache Fälle (Workflow-Builder etc.)."""
    import os
    kanzlei_email = os.getenv("EMAIL_USER", "kanzlei@kanzlei.de")

    texte = {
        "KEINE_ANTWORT": (
            f"Sehr geehrte/r {mandant},\n\n"
            f"wir haben versucht Sie zu erreichen, aber bisher keine Rückmeldung erhalten.\n"
            f"Bitte melden Sie sich bei uns, damit wir Ihre Unterlagen weiterbearbeiten können.\n\n"
            f"Mit freundlichen Grüßen\n{kanzlei_name}\n{kanzlei_email}"
        ),
        "FRIST_ERINNERUNG": (
            f"Sehr geehrte/r {mandant},\n\n"
            f"wir möchten Sie auf bevorstehende Fristen aufmerksam machen.\n"
            + (f"Offene Punkte: {', '.join(details)}\n\n" if details else "\n")
            + f"Bitte kontaktieren Sie uns zeitnah.\n\nMit freundlichen Grüßen\n{kanzlei_name}"
        ),
        "DOKUMENTE": (
            f"Sehr geehrte/r {mandant},\n\n"
            f"für die Bearbeitung Ihrer Unterlagen benötigen wir noch fehlende Dokumente.\n"
            + (f"Bitte senden Sie uns: {', '.join(details)}\n\n" if details else "\n")
            + f"Mit freundlichen Grüßen\n{kanzlei_name}"
        ),
    }
    return texte.get(grund, texte["KEINE_ANTWORT"])


def erstelle_email_vorschau(
    mandant: str, m: Dict, aufgaben: Dict, ds
) -> Dict:
    """Gibt Email-Vorschau für Frontend zurück (HTML + Plain-Text + Betreff)."""
    html_body  = generate_ai_email(mandant, m, aufgaben, ds)
    plain_body = html_body  # Frontend kann beides

    umsatz = float(m.get("umsatz", 0) or 0)
    try:
        tage = ds.berechne_tage_ohne_antwort(mandant)
    except Exception:
        tage = 0
    meine = [a for a in aufgaben.values() if a.get("mandant") == mandant and not a.get("erledigt")]
    ueberfaellig = sum(1 for a in meine if a.get("frist","9999") < datetime.now().strftime("%Y-%m-%d"))

    ton = _ton(umsatz, tage, ueberfaellig, ueberfaellig * 3000 + tage * 100)
    betreffs = {
        "freundlich":       f"Information von Ihrer Steuerkanzlei",
        "hoeflich":         f"Erinnerung: Offene Punkte – {mandant}",
        "nachdrücklich":    f"Wichtig: Handlungsbedarf – {mandant}",
        "dringend":         f"DRINGEND: Sofortiger Handlungsbedarf – {mandant}",
        "premium":          f"Persönliche Information – {mandant}",
        "premium_dringend": f"DRINGEND: Bitte sofort melden – {mandant}",
    }

    return {
        "email_text":   plain_body,
        "email_html":   html_body,
        "betreff":      betreffs.get(ton, "Nachricht von Ihrer Steuerkanzlei"),
        "empfaenger":   m.get("email", ""),
        "ton":          ton,
    }