# ============================================================
# KANZLEI AI — EMAIL GENERATOR v3.1
# Professionelle Mandanten-E-Mails (HTML + Plain-Text)
# ============================================================

from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List, Any
import json
import logging
import os
import re

log = logging.getLogger(__name__)


def _kanzlei_meta(ds=None) -> Tuple[str, str, str]:
    from core.email_sender import resolve_email_from

    kid = getattr(ds, "kanzlei_id", None) or "default"
    resolved = resolve_email_from(kid, ds)
    name = resolved["display_name"]
    email = resolved["from_email"]
    telefon = ""

    if ds is not None:
        try:
            telefon = (ds.setting_holen("kanzlei_telefon") or "").strip()
        except Exception as e:
            log.debug(f"Kanzlei-Stammdaten: {e}")

    if not email:
        email = "kanzlei@example.com"

    return name, email, telefon


def _anrede_name(mandant: str, m: Dict) -> str:
    ap = (m.get("ansprechpartner") or m.get("kontakt") or "").strip()
    if ap:
        return ap
    firma = (m.get("firma") or mandant or "").strip()
    if not firma:
        return "Damen und Herren"
    kurz = re.split(
        r"\s+(GmbH|UG|AG|KG|OHG|GbR|e\.K\.|e\.V\.|SE|mbH)\b",
        firma,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    return kurz if kurz and len(kurz) >= 2 else "Damen und Herren"


# Kurzbezeichnungen / Kategorien → verständliche Formulierungen für Mandanten-Mails
_BEGRIFF_MAP = {
    "fristenabgabe":     "Abgabe der gesetzlichen Fristen",
    "frist":             "Erfüllung einer Frist",
    "ust":               "Umsatzsteuer-Voranmeldung",
    "ustva":             "Umsatzsteuer-Voranmeldung",
    "ustva2024":         "Umsatzsteuer-Voranmeldung",
    "lohn":              "Lohnabrechnung",
    "lohnabrechnung":    "Lohnabrechnung",
    "lohnsteuer":        "Lohnsteuer-Anmeldung",
    "einkommensteuer":   "Einkommensteuererklärung",
    "est":               "Einkommensteuererklärung",
    "jahresabschluss":   "Jahresabschluss",
    "bescheid":          "Steuerbescheid",
    "gewerbesteuer":     "Gewerbesteuererklärung",
    "körperschaftsteuer": "Körperschaftsteuererklärung",
    "koerperschaftsteuer": "Körperschaftsteuererklärung",
    "dokumente":         "Einreichung fehlender Unterlagen",
    "unterlagen":        "Einreichung fehlender Unterlagen",
}

_MONATE_DE = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _norm_begriff(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", (s or "").lower())


def _esc_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _lesbare_aufgaben_beschreibung(aufgabe: Dict) -> str:
    """Mandantentaugliche Bezeichnung aus Beschreibung, Titel oder Kategorie."""
    for feld in ("beschreibung", "titel", "name", "kategorie"):
        raw = (aufgabe.get(feld) or "").strip()
        if not raw or raw.lower() in ("?", "aufgabe", "task", "todo"):
            continue
        key = _norm_begriff(raw)
        if key in _BEGRIFF_MAP:
            return _BEGRIFF_MAP[key]
        # Bereits gut lesbarer Text (Satz, mehrere Wörter, Großschreibung)
        if len(raw) > 12 and (" " in raw or any(c.isupper() for c in raw[1:])):
            return raw[0].upper() + raw[1:] if raw else raw
        label = raw.replace("_", " ").replace("-", " ").strip()
        wkey = _norm_begriff(label)
        if wkey in _BEGRIFF_MAP:
            return _BEGRIFF_MAP[wkey]
        if label:
            return " ".join(w.capitalize() for w in label.split())
    return "Offener Mandantenpunkt"


def _format_frist_de(frist_str: Optional[str]) -> str:
    if not frist_str:
        return "ohne Datum"
    try:
        d = datetime.strptime(str(frist_str)[:10], "%Y-%m-%d")
        return f"{d.day}. {_MONATE_DE[d.month - 1]} {d.year}"
    except (ValueError, TypeError):
        return str(frist_str)


def _tage_bis_frist(frist_str: Optional[str]) -> Optional[int]:
    if not frist_str:
        return None
    try:
        frist = datetime.strptime(str(frist_str)[:10], "%Y-%m-%d")
        heute = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (frist - heute).days
    except (ValueError, TypeError):
        return None


def _aufgabe_zeile(aufgabe: Dict, typ: str) -> str:
    titel = _lesbare_aufgaben_beschreibung(aufgabe)
    frist = _format_frist_de(aufgabe.get("frist"))
    tage = _tage_bis_frist(aufgabe.get("frist"))

    if typ == "ueberfaellig":
        if tage is not None and tage < 0:
            t = "Tag" if abs(tage) == 1 else "Tage"
            return f"{titel} — Frist war am {frist} ({abs(tage)} {t} überfällig)"
        return f"{titel} — Frist war am {frist}"

    if tage == 0:
        return f"{titel} — heute fällig ({frist})"
    if tage == 1:
        return f"{titel} — morgen fällig ({frist})"
    if tage is not None and tage > 0:
        t = "Tag" if tage == 1 else "Tage"
        return f"{titel} — fällig am {frist} (noch {tage} {t})"
    return f"{titel} — Frist am {frist}"


def _baue_aufgaben_inhalt(
    ueberfaellig: List[Dict],
    bald: List[Dict],
) -> Tuple[str, str]:
    """Plain-Text und HTML-Liste für den Aufgaben-Block."""
    if not ueberfaellig and not bald:
        return "", ""

    plain: List[str] = [
        "Ihnen liegen folgende offene Fristen und Aufgaben vor:",
        "",
    ]
    html_parts: List[str] = [
        '<p style="margin:0 0 10px;color:#333;line-height:1.65;">'
        "Ihnen liegen folgende offene Fristen und Aufgaben vor:</p>",
    ]
    lis: List[str] = []

    if ueberfaellig:
        plain.append("Überfällig:")
        for a in sorted(ueberfaellig, key=lambda x: x.get("frist", "")):
            z = _aufgabe_zeile(a, "ueberfaellig")
            plain.append(f"  • {z}")
            lis.append(f'<li style="margin-bottom:8px;">{_esc_html(z)}</li>')
        plain.append("")

    if bald:
        plain.append("In den nächsten Tagen anstehend:")
        for a in sorted(bald, key=lambda x: x.get("frist", "")):
            z = _aufgabe_zeile(a, "bald")
            plain.append(f"  • {z}")
            lis.append(f'<li style="margin-bottom:8px;">{_esc_html(z)}</li>')

    if lis:
        html_parts.append(
            '<ul style="margin:4px 0 0;padding-left:20px;color:#333;line-height:1.65;">'
            + "".join(lis)
            + "</ul>"
        )

    return "\n".join(plain).strip(), "".join(html_parts)


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


def _analysiere_inhalt(
    mandant: str, m: Dict, aufgaben: Dict, ds
) -> Tuple[str, str, str, str, str, str]:
    umsatz = float(m.get("umsatz", 0) or 0)
    fehlende = m.get("fehlende_dokumente_liste", [])
    fehlende = fehlende if isinstance(fehlende, list) else []

    try:
        tage = ds.berechne_tage_ohne_antwort(mandant)
    except Exception:
        tage = 0

    meine = [a for a in aufgaben.values() if a.get("mandant") == mandant and not a.get("erledigt")]
    heute = datetime.now().strftime("%Y-%m-%d")
    grenze = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    ueberfaellig = [a for a in meine if a.get("frist", "9999") < heute]
    bald = [a for a in meine if heute <= a.get("frist", "9999") <= grenze]
    ton = _ton(umsatz, tage, len(ueberfaellig), len(ueberfaellig) * 3000 + tage * 100)

    aufgaben_text, aufgaben_html = _baue_aufgaben_inhalt(ueberfaellig, bald)

    dokumente_text = ""
    if fehlende:
        dokumente_text = "Für die weitere Bearbeitung benötigen wir noch: " + ", ".join(fehlende[:5])

    tage_text = ""
    if tage >= 14:
        tage_text = (
            f"Seit {tage} Tagen haben wir keine Rückmeldung von Ihnen erhalten. "
            "Bitte melden Sie sich kurz bei uns."
        )
    elif tage >= 7:
        tage_text = (
            f"Seit {tage} Tagen hatten wir keinen Austausch. "
            "Wir freuen uns auf Ihre Nachricht."
        )

    return ton, aufgaben_text, aufgaben_html, dokumente_text, tage_text, _anrede_name(mandant, m)


EMAIL_KI_SYSTEM = """Du bist erfahrene/r Steuerberater/in und schreibst E-Mails an Mandanten.
Schreibe auf Deutsch, professionell, klar und direkt an den Empfänger (Sie-Form).

WICHTIG:
- Schreibe AN den Mandanten, nicht über ihn in der dritten Person.
- Nutze die exakten Aufgaben-BESCHREIBUNGEN aus den Daten (nicht erfinden, nicht verkürzen).
- Jeder Punkt in "punkte" muss die konkrete Aufgabe und das Fristdatum verständlich nennen.
- Kein Kanzlei-AI-Branding, kein Hinweis auf automatische Generierung.
- Ton passend zu Dringlichkeit (freundlich bis dringend).

Antworte NUR mit gültigem JSON (kein Markdown drumherum):
{
  "betreff": "Betreffzeile für die E-Mail",
  "anrede": "z.B. Sehr geehrte/r Herr Mustermann,",
  "einleitung": "1-2 Sätze Einleitung",
  "aufgaben_einleitung": "z.B. Ihnen liegen folgende offene Fristen und Aufgaben vor:",
  "punkte": ["Formulierter Punkt mit Beschreibung und Frist", "..."],
  "dokumente_hinweis": "optionaler Satz zu fehlenden Unterlagen oder null",
  "kontakt_hinweis": "optionaler Satz wenn lange keine Rückmeldung oder null",
  "schluss": "1 Satz vor der Grußformel, z.B. Bei Rückfragen erreichen Sie uns gerne.",
  "ton": "freundlich|hoeflich|nachdrücklich|dringend|premium|premium_dringend"
}"""


def _ki_email_aktiv(ds) -> bool:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        return False
    try:
        v = ds.setting_holen("ki_email_generierung_aktiv", True)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "ja", "on")
        return bool(v)
    except Exception:
        return True


def _sammle_email_daten(mandant: str, m: Dict, aufgaben: Dict, ds) -> Dict[str, Any]:
    heute = datetime.now().strftime("%Y-%m-%d")
    meine = [
        a for a in aufgaben.values()
        if a.get("mandant") == mandant and not a.get("erledigt")
    ]
    try:
        tage_ohne = ds.berechne_tage_ohne_antwort(mandant)
    except Exception:
        tage_ohne = 0

    punkte = []
    for a in sorted(meine, key=lambda x: (x.get("frist") or "9999")):
        besch = (a.get("beschreibung") or a.get("kategorie") or "").strip()
        punkte.append({
            "beschreibung": besch or "Ohne Beschreibung",
            "frist":        a.get("frist"),
            "frist_de":     _format_frist_de(a.get("frist")),
            "prioritaet":   a.get("prioritaet") or "normal",
            "ueberfaellig": bool((a.get("frist") or "9999") < heute),
            "tage_bis":     _tage_bis_frist(a.get("frist")),
        })

    fehlende = m.get("fehlende_dokumente_liste", [])
    if not isinstance(fehlende, list):
        fehlende = []

    return {
        "mandant_name":     mandant,
        "ansprechpartner":  (m.get("ansprechpartner") or m.get("kontakt") or "").strip(),
        "firma":            (m.get("firma") or mandant or "").strip(),
        "branche":          (m.get("branche") or "").strip(),
        "tage_ohne_antwort": tage_ohne,
        "aufgaben":         punkte,
        "fehlende_dokumente": fehlende[:10],
        "heute":            _format_frist_de(heute),
    }


def _generiere_email_ki(
    mandant: str,
    m: Dict,
    aufgaben: Dict,
    ds,
    anrede_name: str,
    kanzlei_name: str,
) -> Optional[Dict[str, Any]]:
    """Vollständige E-Mail per OpenAI; None = Fallback auf Regeln."""
    import httpx

    daten = _sammle_email_daten(mandant, m, aufgaben, ds)
    user_msg = (
        f"Kanzlei-Absender: {kanzlei_name}\n"
        f"Empfänger-Anrede-Name: {anrede_name}\n"
        f"Mandantendaten (JSON):\n{json.dumps(daten, ensure_ascii=False, indent=2)}"
    )
    model = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")

    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 900,
                    "temperature": 0.35,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": EMAIL_KI_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                },
            )
        if r.status_code != 200:
            log.warning(f"KI-Email OpenAI HTTP {r.status_code}")
            return None
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            m_json = re.search(r"\{.*\}", raw, re.DOTALL)
            raw = m_json.group(0) if m_json else raw
        payload = json.loads(raw)
        if not isinstance(payload.get("punkte"), list):
            payload["punkte"] = []
        return payload
    except Exception as e:
        log.warning(f"KI-Email Generierung fehlgeschlagen: {e}")
        return None


def _ki_punkte_nach_html(punkte: List[str], einleitung: str) -> str:
    lis = "".join(
        f'<li style="margin-bottom:8px;">{_esc_html(p)}</li>'
        for p in punkte if (p or "").strip()
    )
    intro = f'<p style="margin:0 0 10px;color:#333;line-height:1.65;">{_esc_html(einleitung)}</p>'
    if not lis:
        return intro + '<p style="margin:0;color:#333;">Derzeit keine offenen Punkte.</p>'
    return intro + (
        '<ul style="margin:4px 0 0;padding-left:20px;color:#333;line-height:1.65;">'
        + lis + "</ul>"
    )


def _ki_punkte_nach_plain(punkte: List[str], einleitung: str) -> str:
    lines = [einleitung, ""]
    for p in punkte:
        if (p or "").strip():
            lines.append(f"  • {p.strip()}")
    return "\n".join(lines).strip()


def _erstelle_aus_ki_payload(
    payload: Dict[str, Any],
    mandant: str,
    m: Dict,
    ds,
) -> Dict[str, Any]:
    kanzlei_name, kanzlei_email, kanzlei_telefon = _kanzlei_meta(ds)
    anrede_name = _anrede_name(mandant, m)
    ton = payload.get("ton") or "hoeflich"
    if ton not in ("freundlich", "hoeflich", "nachdrücklich", "dringend", "premium", "premium_dringend"):
        ton = "hoeflich"

    punkte = [str(p).strip() for p in (payload.get("punkte") or []) if str(p).strip()]
    aufg_einl = (payload.get("aufgaben_einleitung") or "").strip() or (
        "Ihnen liegen folgende offene Fristen und Aufgaben vor:"
    )
    aufgaben_html = _ki_punkte_nach_html(punkte, aufg_einl)
    aufgaben_text = _ki_punkte_nach_plain(punkte, aufg_einl)

    dokumente_text = (payload.get("dokumente_hinweis") or "").strip()
    if not dokumente_text:
        fehlende = m.get("fehlende_dokumente_liste", [])
        if isinstance(fehlende, list) and fehlende:
            dokumente_text = "Für die weitere Bearbeitung benötigen wir noch: " + ", ".join(fehlende[:5])

    tage_text = (payload.get("kontakt_hinweis") or "").strip()

    anrede = (payload.get("anrede") or "").strip()
    if not anrede:
        anrede = (
            f"Sehr geehrte/r {anrede_name},"
            if anrede_name != "Damen und Herren"
            else "Sehr geehrte Damen und Herren,"
        )

    einleitung = (payload.get("einleitung") or "").strip()
    schluss = (payload.get("schluss") or "").strip() or (
        "Bei Rückfragen erreichen Sie uns jederzeit per E-Mail oder telefonisch."
    )

    html_body = _html_email(
        anrede_name, ton, aufgaben_text, aufgaben_html,
        dokumente_text, tage_text,
        kanzlei_name, kanzlei_email, kanzlei_telefon,
        custom_anrede=anrede,
        custom_einleitung=einleitung,
        custom_schluss=schluss,
    )

    plain_lines = [anrede, "", einleitung, "", aufgaben_text]
    if dokumente_text:
        plain_lines.extend(["", "Unterlagen:", dokumente_text])
    if tage_text:
        plain_lines.extend(["", tage_text])
    plain_lines.extend(["", schluss, "", f"Mit freundlichen Grüßen", kanzlei_name, kanzlei_email])
    plain_body = "\n".join(plain_lines).strip()

    betreff = (payload.get("betreff") or "").strip() or _betreff(ton, anrede_name)

    return {
        "email_text":    plain_body,
        "email_html":    html_body,
        "betreff":       betreff,
        "empfaenger":    m.get("email", ""),
        "anrede_name":   anrede_name,
        "ton":           ton,
        "ki_generiert":  True,
    }


def _erstelle_email_regelbasiert(
    mandant: str, m: Dict, aufgaben: Dict, ds
) -> Dict[str, Any]:
    kanzlei_name, kanzlei_email, kanzlei_telefon = _kanzlei_meta(ds)
    ton, aufgaben_text, aufgaben_html, dokumente_text, tage_text, anrede_name = _analysiere_inhalt(
        mandant, m, aufgaben, ds
    )
    html_body = _html_email(
        anrede_name, ton, aufgaben_text, aufgaben_html, dokumente_text, tage_text,
        kanzlei_name, kanzlei_email, kanzlei_telefon,
    )
    plain_body = _plain_email(
        anrede_name, ton, aufgaben_text, dokumente_text, tage_text,
        kanzlei_name, kanzlei_email,
    )
    return {
        "email_text":   plain_body,
        "email_html":   html_body,
        "betreff":      _betreff(ton, anrede_name),
        "empfaenger":   m.get("email", ""),
        "anrede_name":  anrede_name,
        "ton":          ton,
        "ki_generiert": False,
    }


def _html_email(
    anrede_name: str,
    ton: str,
    aufgaben_text: str,
    aufgaben_html: str,
    dokumente_text: str,
    tage_text: str,
    kanzlei_name: str,
    kanzlei_email: str,
    kanzlei_telefon: str = "",
    custom_anrede: Optional[str] = None,
    custom_einleitung: Optional[str] = None,
    custom_schluss: Optional[str] = None,
) -> str:
    farben = {
        "freundlich":       {"accent": "#5b8de8", "label": "Mitteilung"},
        "hoeflich":         {"accent": "#c8a96e", "label": "Erinnerung"},
        "nachdrücklich":    {"accent": "#e08c45", "label": "Wichtige Mitteilung"},
        "dringend":         {"accent": "#e05555", "label": "Dringend"},
        "premium":          {"accent": "#9b72e8", "label": "Mitteilung"},
        "premium_dringend": {"accent": "#e05555", "label": "Dringend"},
    }
    einleitungen = {
        "freundlich":       "wir möchten Sie kurz über den aktuellen Stand Ihrer Unterlagen informieren.",
        "hoeflich":         "wir erlauben uns, Sie freundlich an noch offene Punkte in Ihrer Mandatsbetreuung zu erinnern.",
        "nachdrücklich":    "wir möchten Sie auf folgende Punkte aufmerksam machen, die zeitnah Ihrer Bearbeitung bedürfen.",
        "dringend":         "wir bitten Sie um zeitnahe Klärung folgender dringender Punkte.",
        "premium":          "als geschätzten Mandanten informieren wir Sie über folgende Punkte.",
        "premium_dringend": "wir bitten Sie als geschätzten Mandanten, die folgenden Punkte umgehend zu bearbeiten.",
    }

    c = farben.get(ton, farben["freundlich"])
    accent, label = c["accent"], c["label"]
    anrede = custom_anrede or (
        f"Sehr geehrte/r {anrede_name},"
        if anrede_name != "Damen und Herren"
        else "Sehr geehrte Damen und Herren,"
    )
    einleitung_text = custom_einleitung or einleitungen.get(ton, einleitungen["freundlich"])
    schluss_text = custom_schluss or (
        "Bei Rückfragen erreichen Sie uns jederzeit per E-Mail oder telefonisch."
    )

    blocks = []
    if aufgaben_html or aufgaben_text:
        inner = aufgaben_html if aufgaben_html else (
            f'<p style="margin:8px 0 0;color:#333;line-height:1.6;">{aufgaben_text}</p>'
        )
        blocks.append(
            f'<div style="background:#f8f9fa;border-left:4px solid {accent};padding:16px;'
            f'border-radius:0 8px 8px 0;margin:16px 0;">'
            f'<strong style="color:{accent};">Offene Fristen &amp; Aufgaben</strong>'
            f'<div style="margin-top:8px;">{inner}</div></div>'
        )
    if dokumente_text:
        blocks.append(
            '<div style="background:#f8f9fa;border-left:4px solid #5b8de8;padding:16px;'
            'border-radius:0 8px 8px 0;margin:16px 0;">'
            '<strong style="color:#5b8de8;">Fehlende Unterlagen</strong>'
            f'<p style="margin:8px 0 0;color:#333;line-height:1.6;">{dokumente_text}</p></div>'
        )
    if tage_text:
        blocks.append(
            '<div style="background:#fff8e6;border-left:4px solid #e08c45;padding:16px;'
            'border-radius:0 8px 8px 0;margin:16px 0;">'
            '<strong style="color:#e08c45;">Rückmeldung erwünscht</strong>'
            f'<p style="margin:8px 0 0;color:#333;line-height:1.6;">{tage_text}</p></div>'
        )

    body_html = "".join(blocks)
    if not body_html:
        body_html = (
            '<div style="background:#eef8f0;border-left:4px solid #5cb87a;padding:16px;'
            'border-radius:0 8px 8px 0;margin:16px 0;">'
            '<strong style="color:#5cb87a;">Aktueller Stand</strong>'
            '<p style="margin:8px 0 0;color:#333;line-height:1.6;">'
            "Derzeit liegen keine offenen Punkte vor, die Ihre Aufmerksamkeit erfordern."
            "</p></div>"
        )

    body_html = body_html.replace("<motion.div", "<div")
    tel_line = f"<br>{kanzlei_telefon}" if kanzlei_telefon else ""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{label} — {kanzlei_name}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 12px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.08);max-width:600px;width:100%;">
        <tr>
          <td style="background:{accent};padding:26px 32px;">
            <div style="color:rgba(255,255,255,0.85);font-size:11px;text-transform:uppercase;letter-spacing:2px;margin-bottom:6px;">{label}</div>
            <div style="color:#fff;font-size:22px;font-weight:700;line-height:1.3;">{kanzlei_name}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:32px;">
            <p style="font-size:16px;color:#222;margin:0 0 10px;">{anrede}</p>
            <p style="font-size:14px;color:#555;margin:0 0 20px;line-height:1.75;">{einleitung_text}</p>
            {body_html}
            <p style="font-size:14px;color:#555;margin:24px 0 0;line-height:1.75;">{schluss_text}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 28px;">
            <a href="mailto:{kanzlei_email}" style="display:inline-block;background:{accent};color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">
              Antwort an {kanzlei_name}
            </a>
          </td>
        </tr>
        <tr>
          <td style="background:#f8f9fa;padding:20px 32px;border-top:1px solid #eee;">
            <p style="font-size:12px;color:#888;margin:0;line-height:1.65;">
              <strong style="color:#555;">Mit freundlichen Grüßen</strong><br>
              {kanzlei_name}<br>
              {kanzlei_email}{tel_line}<br>
              <span style="color:#aaa;font-size:11px;">{datetime.now().strftime("%d.%m.%Y")}</span>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _plain_email(
    anrede_name: str,
    ton: str,
    aufgaben_text: str,
    dokumente_text: str,
    tage_text: str,
    kanzlei_name: str,
    kanzlei_email: str,
) -> str:
    anrede = (
        f"Sehr geehrte/r {anrede_name},\n\n"
        if anrede_name != "Damen und Herren"
        else "Sehr geehrte Damen und Herren,\n\n"
    )
    einleitungen = {
        "freundlich":       "wir informieren Sie über den aktuellen Stand Ihrer Unterlagen.",
        "hoeflich":         "wir erlauben uns, Sie freundlich an noch offene Punkte in Ihrer Mandatsbetreuung zu erinnern.",
        "nachdrücklich":    "folgende Punkte erfordern zeitnahe Bearbeitung:",
        "dringend":         "folgende Punkte sind dringend:",
        "premium":          "als geschätzter Mandant erhalten Sie folgende Information:",
        "premium_dringend": "bitte klären Sie folgende Punkte umgehend:",
    }
    body = anrede + einleitungen.get(ton, einleitungen["freundlich"]) + "\n\n"
    if aufgaben_text:
        body += aufgaben_text + "\n\n"
    if dokumente_text:
        body += f"UNTERLAGEN:\n{dokumente_text}\n\n"
    if tage_text:
        body += f"RÜCKMELDUNG:\n{tage_text}\n\n"
    if not (aufgaben_text or dokumente_text or tage_text):
        body += "Aktuell liegen keine offenen Punkte vor.\n\n"
    body += (
        f"Bei Rückfragen erreichen Sie uns unter {kanzlei_email}.\n\n"
        f"Mit freundlichen Grüßen\n{kanzlei_name}\n{kanzlei_email}"
    )
    return body


def _betreff(ton: str, anrede_name: str) -> str:
    betreffs = {
        "freundlich":       "Mitteilung Ihrer Steuerkanzlei",
        "hoeflich":         "Erinnerung: offene Unterlagen",
        "nachdrücklich":    "Wichtig: offene Punkte in Ihrer Betreuung",
        "dringend":         "Dringend: Rückmeldung erforderlich",
        "premium":          "Information zu Ihrem Mandat",
        "premium_dringend": "Dringend: Bitte um Rückmeldung",
    }
    base = betreffs.get(ton, "Mitteilung Ihrer Steuerkanzlei")
    if anrede_name and anrede_name != "Damen und Herren":
        return f"{base} — {anrede_name}"
    return base


def generate_ai_email(mandant: str, m: Dict, aufgaben: Dict, ds) -> str:
    """HTML-E-Mail für einen Mandanten (KI wenn aktiv, sonst Regeln)."""
    vorschau = erstelle_email_vorschau(mandant, m, aufgaben, ds)
    return vorschau.get("email_html") or ""


def generiere_email_text(
    mandant: str,
    grund: str = "KEINE_ANTWORT",
    details: Optional[list] = None,
    kanzlei_name: str = "Ihre Steuerkanzlei",
) -> str:
    kanzlei_email = os.getenv("EMAIL_USER", "kanzlei@kanzlei.de")
    texte = {
        "KEINE_ANTWORT": (
            f"Sehr geehrte/r {mandant},\n\n"
            f"wir haben bisher keine Rückmeldung von Ihnen erhalten. "
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
            f"für die Bearbeitung benötigen wir noch fehlende Unterlagen.\n"
            + (f"Bitte senden Sie uns: {', '.join(details)}\n\n" if details else "\n")
            + f"Mit freundlichen Grüßen\n{kanzlei_name}"
        ),
    }
    return texte.get(grund, texte["KEINE_ANTWORT"])


def erstelle_email_vorschau(mandant: str, m: Dict, aufgaben: Dict, ds) -> Dict:
    anrede_name = _anrede_name(mandant, m)
    kanzlei_name, _, _ = _kanzlei_meta(ds)

    if _ki_email_aktiv(ds):
        ki_payload = _generiere_email_ki(mandant, m, aufgaben, ds, anrede_name, kanzlei_name)
        if ki_payload:
            return _erstelle_aus_ki_payload(ki_payload, mandant, m, ds)

    return _erstelle_email_regelbasiert(mandant, m, aufgaben, ds)
