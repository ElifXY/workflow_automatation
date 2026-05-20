# ============================================================
# KANZLEI AI — MANDANTENPORTAL API v2.0
# Datei: portal_api.py — Router wird in api.app eingebunden (ein Uvicorn, typ. Port 8000).
#
# NEU in v2.0:
#   ✓ Digitale Unterschrift (eIDAS EES — rechtssicher für D/EU)
#   ✓ Kanzlei sendet Dokument → Mandant unterschreibt → zurück
#   ✓ Vollständiger Audit-Trail (wer, wann, IP, Gerät)
#   ✓ Bulk-Upload (mehrere Dateien auf einmal)
#   ✓ Freigabe-Workflow (Jahresabschluss, Steuererklärung)
#   ✓ Ablehnen mit Begründung
# ============================================================

import os, sys, secrets, hashlib, hmac, logging, base64, json, uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends, Header, status, Query, Request, APIRouter
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import AliasChoices, BaseModel, Field
from dotenv import load_dotenv
from core.daten_speicher import DatenSpeicher
from modules.settings_manager import setting_holen
from modules import portal_chat as pc

load_dotenv()
log = logging.getLogger("kanzlei_portal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_plog = (os.getenv("PORTAL_LOG_DIR") or os.getenv("API_LOG_DIR") or "").strip()
if _plog:
    try:
        os.makedirs(_plog, exist_ok=True)
        _pfh = logging.FileHandler(os.path.join(_plog, "portal.log"), encoding="utf-8")
        _pfh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(_pfh)
    except OSError as e:
        log.warning("Portal-Datei-Log nicht nutzbar (%s): nur stdout.", e)

# Router wird in die Haupt-App (api.py / backend.api) eingebunden — CORS dort.
portal_router = APIRouter(tags=["Portal"])

ds = DatenSpeicher()
SECRET_KEY    = os.getenv("PORTAL_SECRET", secrets.token_hex(32))


def _store_for_mandant(mandant: str) -> DatenSpeicher:
    """DatenSpeicher der Kanzlei, zu der der Mandant gehört (Multi-Tenant)."""
    try:
        if mandant in ds.hole_mandanten():
            return ds
        from core.daten_speicher import _pg_mandanten_mode, _pg_conn

        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT kanzlei_id FROM mandanten WHERE name = %s AND aktiv = 1 LIMIT 1",
                    (mandant,),
                )
                row = cur.fetchone()
            if row:
                kid = row["kanzlei_id"] if isinstance(row, dict) else row[0]
                st = DatenSpeicher(kanzlei_id=kid)
                if mandant in st.hole_mandanten():
                    return st
    except Exception as e:
        log.warning("_store_for_mandant(%s): %s", mandant, e)
    return ds
TOKEN_STUNDEN = int(os.getenv("PORTAL_TOKEN_STUNDEN", "168"))
UPLOAD_MAX_MB = int(os.getenv("PORTAL_UPLOAD_MAX_MB", "20"))

_PORTAL_GATEWAY_KEY = (os.getenv("PORTAL_GATEWAY_KEY") or os.getenv("API_GATEWAY_KEY") or "").strip()
_PORTAL_GW_EXEMPT_PREFIXES = ("/portal/docs", "/portal/openapi.json", "/openapi.json")
_PORTAL_GW_EXACT = frozenset({"/portal", "/portal/health", "/portal/login"})
# Kanzlei-Haupt-App (JWT), nicht Mandanten-Portal-Token:
_PORTAL_KANZLEI_PREFIXES = ("/portal/admin/", "/portal/mandant/", "/portal/unterschriften/")


# ── TOKEN ────────────────────────────────────────────────────

def erstelle_token(mandant: str) -> str:
    ablauf  = datetime.now() + timedelta(hours=TOKEN_STUNDEN)
    payload = f"{mandant}|{ablauf.strftime('%Y%m%d%H%M')}"
    hmac    = hashlib.sha256(f"{SECRET_KEY}:{payload}".encode()).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}|{hmac}".encode()).decode()

def verifiziere_token(token: str) -> Optional[str]:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts   = decoded.split("|")
        if len(parts) != 3: return None
        mandant, ablauf_str, hmac_recv = parts
        payload = f"{mandant}|{ablauf_str}"
        hmac_ok = hashlib.sha256(f"{SECRET_KEY}:{payload}".encode()).hexdigest()[:32]
        if not secrets.compare_digest(hmac_recv, hmac_ok): return None
        if datetime.now() > datetime.strptime(ablauf_str, "%Y%m%d%H%M"): return None
        if mandant not in _store_for_mandant(mandant).hole_mandanten():
            return None
        return mandant
    except Exception:
        return None

def hole_mandant(authorization: Optional[str] = Header(None)) -> str:
    if not bool(setting_holen("portal_aktiv")):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Mandantenportal ist deaktiviert")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login erforderlich")
    mandant = verifiziere_token(authorization.replace("Bearer ", ""))
    if not mandant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token abgelaufen")
    return mandant


# ── PORTAL DATEN ─────────────────────────────────────────────

def _portal_store(store: DatenSpeicher, mandant: Optional[str] = None) -> Dict:
    return {
        "portal": {
            "uploads": {
                x["id"]: x for x in store.portal_liste("upload", mandant=mandant) if x.get("id")
            },
            "unterschriften": {
                x["id"]: x for x in store.portal_liste("unterschrift", mandant=mandant) if x.get("id")
            },
            "freigaben": {
                x["id"]: x for x in store.portal_liste("freigabe", mandant=mandant) if x.get("id")
            },
        }
    }


def _portal() -> Dict:
    return _portal_store(ds)


def _save_portal(data: Dict, store: Optional[DatenSpeicher] = None):
    st = store or ds
    portal = (data or {}).get("portal", {})
    for x in (portal.get("uploads") or {}).values():
        rid = x.get("id")
        if rid:
            st.portal_speichern("upload", rid, x.get("mandant", ""), x)
    for x in (portal.get("unterschriften") or {}).values():
        rid = x.get("id")
        if rid:
            st.portal_speichern("unterschrift", rid, x.get("mandant", ""), x)
    for x in (portal.get("freigaben") or {}).values():
        rid = x.get("id")
        if rid:
            st.portal_speichern("freigabe", rid, x.get("mandant", ""), x)


# ── MODELS ───────────────────────────────────────────────────

class NachrichtCreate(BaseModel):
    betreff: str = Field(..., min_length=1, max_length=200)
    inhalt:  str = Field(
        ...,
        min_length=1,
        max_length=5000,
        validation_alias=AliasChoices("inhalt", "text", "nachricht"),
    )


def _komm_zeile_normalisieren(k: Dict) -> Dict:
    """DB-Felder (erstellt_am) für Portal-UI vereinheitlichen."""
    row = dict(k)
    row.setdefault("timestamp", row.get("erstellt_am") or row.get("zeit") or "")
    txt = (row.get("text") or "").strip()
    if txt.startswith("Betreff:"):
        parts = txt.split("\n\n", 1)
        if len(parts) == 2:
            row.setdefault("betreff", parts[0].replace("Betreff:", "", 1).strip())
            row["text"] = parts[1].strip()
    return row

class DokumentUpload(BaseModel):
    dateiname:    str
    dateityp:     str = "application/pdf"
    inhalt_b64:   str
    beschreibung: Optional[str] = ""
    kategorie:    Optional[str] = "Sonstiges"
    projektnummer: Optional[str] = ""

class MultiUpload(BaseModel):
    dateien: List[DokumentUpload]

class UnterschriftLeisten(BaseModel):
    unterschrift_b64: str   # Canvas-PNG als Base64
    bestaetigung:     bool = True
    ip_adresse:       Optional[str] = None

class UnterschriftAnfragen(BaseModel):
    mandant:       str
    dokumentname:  str
    dokument_b64:  str
    dokumenttyp:   str = "pdf"
    betreff:       str = "Bitte unterzeichnen"
    hinweis:       str = ""
    gueltig_tage:  int = 30
    admin_key:     str = ""

class FreigabeAnfragen(BaseModel):
    mandant:      str
    titel:        str
    beschreibung: str
    dokument_b64: Optional[str] = None
    admin_key:    str = ""

class SimulationRequest(BaseModel):
    investition:      float = 0.0
    zusatz_einnahmen: float = 0.0
    abschreibungen:   float = 0.0
    sonderausgaben:   float = 0.0


# ============================================================
# ÖFFENTLICHE ENDPUNKTE
# ============================================================

@portal_router.get("/portal", response_class=HTMLResponse, tags=["Portal"])
def portal_startseite():
    try:
        with open("portal.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse("""<html><body style="background:#0b0d11;color:#e8eaf0;
            font-family:sans-serif;padding:40px;text-align:center">
            <h2 style="color:#c8a96e">Kanzlei AI — Mandantenportal</h2>
            <p>portal.html nicht gefunden.</p></body></html>""")

@portal_router.get("/portal/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

@portal_router.post("/portal/login", tags=["Portal"])
@portal_router.get("/portal/login", tags=["Portal"])
def portal_login(token: str = Query(...)):
    mandant = verifiziere_token(token)
    if not mandant:
        raise HTTPException(401, "Ungültiger oder abgelaufener Zugangslink")
    store = _store_for_mandant(mandant)
    m = store.hole_mandanten().get(mandant, {})

    offen_unterschriften = sum(
        1 for u in store.portal_liste("unterschrift", mandant=mandant)
        if u.get("status") == "ausstehend"
    )
    p = _portal_store(store, mandant)
    offen_freigaben = sum(
        1 for f in p["portal"]["freigaben"].values()
        if f.get("mandant") == mandant and f.get("status") == "ausstehend"
    )

    ds.log_eintrag(f"PORTAL_LOGIN | {mandant}")
    return {
        "mandant":               mandant,
        "token":                 token,
        "email":                 m.get("email", ""),
        "willkommen":            f"Willkommen, {mandant}!",
        "offene_unterschriften": offen_unterschriften,
        "offene_freigaben":      offen_freigaben,
    }

# POST /portal/admin/token/{mandant} — nur in api.py (JWT), nicht hier (vermeidet Admin-Key in der UI)


# ── MANDANTEN-DATEN ──────────────────────────────────────────

@portal_router.get("/portal/meine-daten", tags=["Portal"])
def meine_daten(mandant: str = Depends(hole_mandant)):
    m = ds.hole_mandanten().get(mandant, {})
    return {"name":mandant,"email":m.get("email",""),"telefon":m.get("telefon",""),
            "branche":m.get("branche",""),"umsatz":m.get("umsatz",0)}

@portal_router.get("/portal/aufgaben", tags=["Portal"])
def meine_aufgaben(mandant: str = Depends(hole_mandant)):
    """Nur Aufgaben, die die Kanzlei explizit im Portal-Chat zugewiesen hat."""
    from core.aufgabe_erledigt import aufgabe_ist_erledigt, aufgabe_ist_offen

    store = _store_for_mandant(mandant)
    jetzt = datetime.now()
    result = []
    for a in store.hole_aufgaben_fuer_mandant(mandant):
        if not a.get("portal_sichtbar"):
            continue
        erledigt = aufgabe_ist_erledigt(a)
        try:
            tage = (datetime.strptime(a["frist"], "%Y-%m-%d") - jetzt).days
            dringend = aufgabe_ist_offen(a) and tage <= 3
        except Exception:
            tage = None
            dringend = False
        result.append({
            "id": a.get("id"),
            "beschreibung": a.get("beschreibung", ""),
            "frist": a.get("frist", ""),
            "erledigt": erledigt,
            "prioritaet": a.get("prioritaet", "normal"),
            "tage": tage,
            "dringend": dringend,
        })
    result.sort(key=lambda x: (x["erledigt"], x["tage"] or 9999))
    return {"aufgaben": result, "offen": sum(1 for a in result if not a["erledigt"])}


@portal_router.post("/portal/aufgaben/{aufgabe_id}/erledigen", tags=["Portal"])
def portal_aufgabe_erledigen(aufgabe_id: str, mandant: str = Depends(hole_mandant)):
    from core.aufgabe_erledigt import aufgabe_ist_erledigt

    store = _store_for_mandant(mandant)
    alle = store.hole_fristen()
    if aufgabe_id not in alle:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    a = dict(alle[aufgabe_id])
    if a.get("mandant") != mandant:
        raise HTTPException(403, "Kein Zugriff")
    if not a.get("portal_sichtbar"):
        raise HTTPException(403, "Diese Aufgabe ist nicht im Portal sichtbar")
    war_erledigt = aufgabe_ist_erledigt(a)
    a["erledigt"] = 0 if war_erledigt else 1
    if a["erledigt"]:
        a["erledigt_am"] = datetime.now().isoformat()
        a["erledigt_von"] = "mandant_portal"
    else:
        a.pop("erledigt_am", None)
        a.pop("erledigt_von", None)
    if not store.aufgabe_speichern(aufgabe_id, a):
        raise HTTPException(500, "Aufgabe konnte nicht gespeichert werden")
    try:
        pc.chat_aufgabe_erledigt(store, mandant, aufgabe_id, a.get("beschreibung", ""), bool(a["erledigt"]))
        for row in store.portal_liste("chat", mandant=mandant):
            if row.get("typ") == "aufgabe" and (row.get("refs") or {}).get("aufgabe_id") == aufgabe_id:
                pc.update_chat_meta(store, mandant, row["id"], {"aufgabe_erledigt": bool(a["erledigt"])})
    except Exception as e:
        log.warning("chat nach aufgabe: %s", e)
    store.log_eintrag(f"PORTAL_AUFGABE_TOGGLE | {mandant} | {aufgabe_id[:8]} | erledigt={a['erledigt']}")
    return {"status": "erledigt" if a["erledigt"] else "offen", "id": aufgabe_id}

@portal_router.get("/portal/dokumente", tags=["Portal"])
def fehlende_dokumente(mandant: str = Depends(hole_mandant)):
    store = _store_for_mandant(mandant)
    m = store.hole_mandanten().get(mandant, {})
    fehlende = m.get("fehlende_dokumente_liste",[])
    return {"fehlende_dokumente":fehlende,"anzahl":len(fehlende),
            "hinweis":"Bitte hochladen." if fehlende else "Alle vollständig ✓"}


# ============================================================
# DOKUMENT-UPLOAD
# ============================================================

def _verarbeite_upload(mandant: str, data: DokumentUpload, *, upload_von: str = "mandant") -> Dict:
    store = _store_for_mandant(mandant)
    max_mb = int(setting_holen("portal_upload_max_mb") or UPLOAD_MAX_MB or 20)
    if bool(setting_holen("portal_projektnummer_pflicht")) and not str(data.projektnummer or "").strip():
        raise HTTPException(400, "Projektnummer ist als Pflichtfeld aktiviert")
    try:
        inhalt = base64.b64decode(data.inhalt_b64)
        if len(inhalt) > max_mb * 1024 * 1024:
            raise HTTPException(413, f"Datei zu groß (max. {max_mb} MB)")
        from core.upload_security import validate_binary_upload, sanitize_filename

        validate_binary_upload(inhalt, max_bytes=max_mb * 1024 * 1024)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, "Ungültiger Dateiinhalt") from e

    safe_name = sanitize_filename(data.dateiname)
    upload_dir = os.path.join("data","uploads",mandant.replace(" ","_"))
    os.makedirs(upload_dir, exist_ok=True)
    dateiname  = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    dateipfad  = os.path.join(upload_dir, dateiname)
    with open(dateipfad,"wb") as f: f.write(inhalt)

    uid = str(uuid.uuid4())
    upload_rec = {
        "id": uid, "mandant": mandant, "dateiname": dateiname,
        "original": data.dateiname, "dateipfad": dateipfad,
        "groesse_kb": round(len(inhalt) / 1024, 1),
        "kategorie": data.kategorie or "Sonstiges",
        "projektnummer": str(data.projektnummer or "").strip(),
        "beschreibung": data.beschreibung or "",
        "hochgeladen_am": datetime.now().isoformat(),
        "status": "hochgeladen",
    }
    if not store.portal_speichern("upload", uid, mandant, upload_rec):
        raise HTTPException(500, "Upload konnte nicht gespeichert werden")

    m = store.hole_mandanten().get(mandant, {})
    fehlende = list(m.get("fehlende_dokumente_liste") or [])
    gefunden = next(
        (d for d in fehlende if d.lower() in data.dateiname.lower() or data.dateiname.lower() in d.lower()),
        None,
    )
    if gefunden:
        fehlende.remove(gefunden)
        m["fehlende_dokumente_liste"] = fehlende
        m["letzte_antwort"] = datetime.now().isoformat()
        store.mandant_speichern(mandant, m)

    richtung = "ausgehend" if upload_von == "kanzlei" else "eingehend"
    store.kommunikation_hinzufuegen(mandant, {
        "typ": "portal_upload",
        "text": f"Hochgeladen: {data.dateiname} ({round(len(inhalt) / 1024, 1)} KB)",
        "kategorie": data.kategorie,
        "timestamp": datetime.now().isoformat(),
        "richtung": richtung,
    })
    store.log_eintrag(f"PORTAL_UPLOAD | {mandant} | {data.dateiname} | {len(inhalt)} bytes | von={upload_von}")
    try:
        pc.chat_upload(
            store, mandant, uid, data.dateiname, round(len(inhalt) / 1024, 1), sender=upload_von
        )
        if gefunden:
            for row in store.portal_liste("chat", mandant=mandant):
                if row.get("typ") != "dokument_anfrage":
                    continue
                doc = (row.get("refs") or {}).get("dokument_name") or (row.get("meta") or {}).get("dokument_name", "")
                if doc and (doc.lower() in gefunden.lower() or gefunden.lower() in doc.lower()):
                    pc.update_chat_meta(store, mandant, row["id"], {"dokument_offen": False})
    except Exception as e:
        log.warning("chat_upload: %s", e)

    return {"status":"ok","upload_id":uid,"dateiname":dateiname,
            "groesse_kb":round(len(inhalt)/1024,1),
            "automatisch_zugeordnet":gefunden,"verbleibende_docs":len(fehlende)}

@portal_router.post("/portal/dokumente/hochladen", tags=["Portal"])
def dokument_hochladen(data: DokumentUpload, mandant: str = Depends(hole_mandant)):
    return _verarbeite_upload(mandant, data)

@portal_router.post("/portal/dokumente/bulk-upload", tags=["Portal"])
def bulk_upload(data: MultiUpload, mandant: str = Depends(hole_mandant)):
    """Mehrere Dokumente auf einmal hochladen."""
    ergebnisse = []
    for datei in data.dateien:
        try:    ergebnisse.append({"dateiname":datei.dateiname,"status":"ok",**_verarbeite_upload(mandant,datei)})
        except Exception as e: ergebnisse.append({"dateiname":datei.dateiname,"status":"fehler","fehler":str(e)})
    erfolgreich = sum(1 for r in ergebnisse if r["status"]=="ok")
    ds.log_eintrag(f"PORTAL_BULK_UPLOAD | {mandant} | {erfolgreich}/{len(data.dateien)}")
    return {"ergebnisse":ergebnisse,"erfolgreich":erfolgreich,"gesamt":len(data.dateien)}

@portal_router.get("/portal/dokumente/meine-uploads", tags=["Portal"])
def meine_uploads(mandant: str = Depends(hole_mandant)):
    store = _store_for_mandant(mandant)
    uploads = sorted(
        store.portal_liste("upload", mandant=mandant),
        key=lambda x: x.get("hochgeladen_am", ""),
        reverse=True,
    )
    return {"uploads": uploads, "anzahl": len(uploads)}


# ============================================================
# ✍ DIGITALE UNTERSCHRIFT
# ============================================================

def erstelle_unterschrift_anfrage(
    store: DatenSpeicher,
    mandant: str,
    dokumentname: str,
    dokument_b64: str,
    dokumenttyp: str = "application/pdf",
    betreff: str = "Bitte unterzeichnen",
    hinweis: str = "",
    gueltig_tage: int = 30,
) -> Dict:
    """Kanzlei fordert Unterschrift beim Mandanten an (JWT oder Legacy Admin-Key-Route)."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    if mandant not in store.hole_mandanten():
        raise HTTPException(404, f"Mandant '{mandant}' nicht gefunden")
    if not (dokumentname or "").strip() or not (dokument_b64 or "").strip():
        raise HTTPException(400, "Dokumentname und Datei sind erforderlich")

    uid = str(uuid.uuid4())
    gueltig_bis = (datetime.now() + timedelta(days=gueltig_tage)).isoformat()
    payload = {
        "id": uid,
        "mandant": mandant,
        "dokumentname": dokumentname.strip(),
        "dokument_b64": dokument_b64,
        "dokumenttyp": dokumenttyp or "application/pdf",
        "betreff": betreff or "Bitte unterzeichnen",
        "hinweis": hinweis or "",
        "status": "ausstehend",
        "erstellt_am": datetime.now().isoformat(),
        "gueltig_bis": gueltig_bis,
        "audit_trail": [{"aktion": "anfrage_erstellt", "zeitpunkt": datetime.now().isoformat()}],
        "unterschrift_b64": None,
        "unterschrieben_am": None,
        "unterzeichner_info": None,
    }
    if not store.portal_speichern("unterschrift", uid, mandant, payload):
        raise HTTPException(500, "Unterschrift konnte nicht angelegt werden")
    store.kommunikation_hinzufuegen(mandant, {
        "typ": "unterschrift_anfrage",
        "text": f"Unterschrift angefordert: {dokumentname} — {betreff}",
        "timestamp": datetime.now().isoformat(),
        "richtung": "ausgehend",
    })
    store.log_eintrag(f"UNTERSCHRIFT_ANFRAGE | {mandant} | {dokumentname} | ID:{uid[:8]}")
    try:
        pc.chat_unterschrift_anfrage(store, mandant, uid, dokumentname, betreff, hinweis)
    except Exception as e:
        log.warning("chat_unterschrift_anfrage: %s", e)
    return {
        "unterschrift_id": uid,
        "mandant": mandant,
        "dokument": dokumentname,
        "gueltig_bis": gueltig_bis,
        "status": "ausstehend",
    }


@portal_router.post("/portal/unterschrift/anfragen", tags=["Unterschrift"])
def unterschrift_anfragen(data: UnterschriftAnfragen):
    """Legacy: Admin-Key in .env (optional). Kanzlei-UI nutzt POST /portal/mandant/{name}/unterschrift-anfragen."""
    expected = (os.getenv("PORTAL_ADMIN_KEY") or "").strip()
    if expected and not secrets.compare_digest((data.admin_key or "").strip(), expected):
        raise HTTPException(403, "Ungültiger Admin-Key")
    store = _store_for_mandant(data.mandant)
    return erstelle_unterschrift_anfrage(
        store,
        data.mandant,
        data.dokumentname,
        data.dokument_b64,
        data.dokumenttyp,
        data.betreff,
        data.hinweis,
        data.gueltig_tage,
    )

@portal_router.get("/portal/unterschrift/offen", tags=["Unterschrift"])
def offene_unterschriften(mandant: str = Depends(hole_mandant)):
    """Mandant sieht alle offenen Unterschriftsanfragen."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    store = _store_for_mandant(mandant)
    p = _portal_store(store, mandant)
    jetzt = datetime.now()
    offene = []
    for uid, u in p["portal"]["unterschriften"].items():
        if u.get("mandant") != mandant: continue
        try:
            if jetzt > datetime.fromisoformat(u["gueltig_bis"]) and u["status"] == "ausstehend":
                u["status"] = "abgelaufen"
        except (TypeError, ValueError) as exc:
            log.warning("offene_unterschriften: gueltig_bis ungueltig id=%s: %s", uid[:12], exc)
        if u["status"] in ["ausstehend","abgelaufen"]:
            offene.append({"id":uid,"dokumentname":u["dokumentname"],"betreff":u["betreff"],
                           "hinweis":u["hinweis"],"status":u["status"],
                           "erstellt_am":u["erstellt_am"],"gueltig_bis":u["gueltig_bis"],
                           "hat_dokument":bool(u.get("dokument_b64"))})
    if offene:
        _save_portal(p, store)
    return {"unterschriften": sorted(offene, key=lambda x: x["erstellt_am"], reverse=True),
            "anzahl": len(offene)}

@portal_router.get("/portal/unterschrift/{uid}/dokument", tags=["Unterschrift"])
def dokument_herunterladen(uid: str, mandant: str = Depends(hole_mandant)):
    """Zu unterzeichnendes Dokument abrufen."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    store = _store_for_mandant(mandant)
    u = store.portal_holen("unterschrift", uid) or {}
    if not u: raise HTTPException(404, "Nicht gefunden")
    if u.get("mandant") != mandant: raise HTTPException(403, "Kein Zugriff")
    if u.get("status") == "abgelaufen": raise HTTPException(410, "Frist abgelaufen")
    return {"dokument_b64":u.get("dokument_b64",""),"dokumenttyp":u.get("dokumenttyp","pdf"),
            "dokumentname":u.get("dokumentname","")}

@portal_router.post("/portal/unterschrift/{uid}/leisten", tags=["Unterschrift"])
def unterschrift_leisten(uid: str, data: UnterschriftLeisten,
                          request: Request, mandant: str = Depends(hole_mandant)):
    """
    Mandant unterschreibt digital.
    Audit-Trail: IP, Zeitpunkt, User-Agent, Browser-Infos werden erfasst.
    Das Ergebnis ist rechtsgültig nach eIDAS EES.
    """
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    store = _store_for_mandant(mandant)
    u = store.portal_holen("unterschrift", uid) or {}
    if not u:
        raise HTTPException(404, "Nicht gefunden")
    if u.get("mandant") != mandant:
        raise HTTPException(403, "Kein Zugriff")
    if u.get("status") != "ausstehend":
        raise HTTPException(400, f"Status: {u.get('status')}")
    if not data.bestaetigung:
        raise HTTPException(400, "Bitte Kenntnisnahme bestätigen")
    try:
        deadline = datetime.fromisoformat(u["gueltig_bis"])
    except (TypeError, ValueError) as exc:
        log.warning("unterschrift_leisten: gueltig_bis ungueltig uid=%s: %s", uid[:12], exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Interne Fristangabe ungültig — bitte neue Unterschriftsanfrage anfordern.",
        ) from exc
    if datetime.now() > deadline:
        raise HTTPException(410, "Unterschriftsfrist abgelaufen")

    client_ip  = request.client.host if request.client else "unbekannt"
    user_agent = request.headers.get("user-agent","")[:200]
    jetzt      = datetime.now()

    u.update({
        "unterschrift_b64":  data.unterschrift_b64,
        "unterschrieben_am": jetzt.isoformat(),
        "status":            "unterschrieben",
        "unterzeichner_info": {
            "mandant":   mandant,
            "ip":        data.ip_adresse or client_ip,
            "user_agent":user_agent,
            "zeitpunkt": jetzt.isoformat(),
            "zeitzone":  "Europe/Berlin",
            "eidas_typ": "EES",  # Einfache Elektronische Signatur
        }
    })
    trail = list(u.get("audit_trail") or [])
    trail.append({
        "aktion": "unterschrieben",
        "zeitpunkt": jetzt.isoformat(),
        "ip": data.ip_adresse or client_ip,
        "user_agent": user_agent[:100],
        "details": f"Digital unterzeichnet von {mandant} — eIDAS EES",
    })
    u["audit_trail"] = trail
    if not store.portal_speichern("unterschrift", uid, mandant, u):
        raise HTTPException(500, "Unterschrift konnte nicht gespeichert werden")

    store.kommunikation_hinzufuegen(mandant, {
        "typ": "dokument_unterschrieben",
        "text": f"Dokument unterzeichnet: {u['dokumentname']}",
        "unterschrift_id": uid,
        "timestamp": jetzt.isoformat(),
        "richtung": "eingehend",
    })
    store.log_eintrag(f"UNTERSCHRIEBEN | {mandant} | {u['dokumentname']} | IP:{client_ip}")
    try:
        pc.chat_unterschrift_status(store, mandant, uid, u["dokumentname"], "unterschrieben")
        for row in store.portal_liste("chat", mandant=mandant):
            if row.get("typ") == "unterschrift_anfrage" and (row.get("refs") or {}).get("unterschrift_id") == uid:
                pc.update_chat_meta(store, mandant, row["id"], {"unterschrift_status": "unterschrieben"})
    except Exception as e:
        log.warning("chat nach unterschrift: %s", e)

    return {"status":"unterschrieben","dokumentname":u["dokumentname"],
            "zeitpunkt":jetzt.isoformat(),
            "hinweis":"Ihre Unterschrift wurde erfasst und an die Kanzlei übermittelt.",
            "audit_id":uid}

@portal_router.post("/portal/unterschrift/{uid}/ablehnen", tags=["Unterschrift"])
def unterschrift_ablehnen(uid: str, grund: str = Query(""),
                           mandant: str = Depends(hole_mandant)):
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    p = _portal()
    u = p["portal"]["unterschriften"].get(uid)
    if not u or u.get("mandant") != mandant: raise HTTPException(404, "Nicht gefunden")
    u["status"] = "abgelehnt"
    u["audit_trail"].append({"aktion":"abgelehnt","zeitpunkt":datetime.now().isoformat(),"grund":grund})
    _save_portal(p)
    ds.kommunikation_hinzufuegen(mandant,{"typ":"unterschrift_abgelehnt",
        "text":f"Abgelehnt: {u['dokumentname']} — {grund or 'kein Grund'}",
        "timestamp":datetime.now().isoformat()})
    ds.log_eintrag(f"UNTERSCHRIFT_ABGELEHNT | {mandant} | {u['dokumentname']}")
    return {"status":"abgelehnt"}

@portal_router.get("/portal/unterschrift/{uid}/status", tags=["Unterschrift"])
def unterschrift_status(uid: str, admin_key: str = Query(...)):
    """KANZLEI: Status + Audit-Trail einer Unterschriftsanfrage."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    if not secrets.compare_digest(admin_key, os.getenv("PORTAL_ADMIN_KEY","kanzlei-admin-2024")):
        raise HTTPException(403, "Ungültiger Admin-Key")
    p = _portal()
    u = p["portal"]["unterschriften"].get(uid)
    if not u: raise HTTPException(404, "Nicht gefunden")
    result = {k:v for k,v in u.items() if k != "dokument_b64"}
    if u["status"] == "unterschrieben":
        result["unterschrift_b64"] = u.get("unterschrift_b64")
    return result

@portal_router.get("/portal/unterschrift/alle", tags=["Unterschrift"])
def alle_unterschriften(admin_key: str = Query(...), mandant: Optional[str] = Query(None)):
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    if not secrets.compare_digest(admin_key, os.getenv("PORTAL_ADMIN_KEY","kanzlei-admin-2024")):
        raise HTTPException(403, "Ungültiger Admin-Key")
    p    = _portal()
    alle = list(p["portal"]["unterschriften"].values())
    if mandant: alle = [u for u in alle if u.get("mandant")==mandant]
    result = [{"id":u["id"],"mandant":u["mandant"],"dokumentname":u["dokumentname"],
               "betreff":u["betreff"],"status":u["status"],"erstellt_am":u["erstellt_am"],
               "unterschrieben_am":u.get("unterschrieben_am"),"gueltig_bis":u["gueltig_bis"]}
              for u in sorted(alle, key=lambda x:x["erstellt_am"], reverse=True)]
    return {"unterschriften":result,"gesamt":len(result),
            "ausstehend":sum(1 for u in result if u["status"]=="ausstehend"),
            "unterschrieben":sum(1 for u in result if u["status"]=="unterschrieben"),
            "abgelehnt":sum(1 for u in result if u["status"]=="abgelehnt")}


# ============================================================
# FREIGABEN
# ============================================================

@portal_router.post("/portal/freigabe/anfragen", tags=["Freigaben"])
def freigabe_anfragen(data: FreigabeAnfragen):
    if not secrets.compare_digest(data.admin_key, os.getenv("PORTAL_ADMIN_KEY","kanzlei-admin-2024")):
        raise HTTPException(403, "Ungültiger Admin-Key")
    fid = str(uuid.uuid4())
    p   = _portal()
    p["portal"]["freigaben"][fid] = {"id":fid,"mandant":data.mandant,"titel":data.titel,
        "beschreibung":data.beschreibung,"dokument_b64":data.dokument_b64,
        "status":"ausstehend","erstellt_am":datetime.now().isoformat(),
        "freigegeben_am":None,"kommentar":None}
    _save_portal(p)
    ds.log_eintrag(f"FREIGABE_ANGEFRAGT | {data.mandant} | {data.titel}")
    return {"freigabe_id":fid,"status":"ausstehend"}

@portal_router.get("/portal/freigaben", tags=["Freigaben"])
def meine_freigaben(mandant: str = Depends(hole_mandant)):
    p = _portal()
    freigaben = [f for f in p["portal"]["freigaben"].values()
                 if f.get("mandant")==mandant and f.get("status")=="ausstehend"]
    # Dokument-Daten entfernen für Übersicht
    result = [{k:v for k,v in f.items() if k!="dokument_b64"} for f in freigaben]
    return {"freigaben":result,"anzahl":len(result)}

@portal_router.post("/portal/freigaben/{fid}/freigeben", tags=["Freigaben"])
def freigabe_erteilen(fid: str, kommentar: str = Query(""),
                       mandant: str = Depends(hole_mandant)):
    p = _portal()
    f = p["portal"]["freigaben"].get(fid)
    if not f or f.get("mandant")!=mandant: raise HTTPException(404, "Nicht gefunden")
    f.update({"status":"freigegeben","freigegeben_am":datetime.now().isoformat(),"kommentar":kommentar})
    _save_portal(p)
    ds.kommunikation_hinzufuegen(mandant,{"typ":"freigabe_erteilt",
        "text":f"Freigabe: {f['titel']}","timestamp":datetime.now().isoformat()})
    ds.log_eintrag(f"FREIGABE_ERTEILT | {mandant} | {f['titel']}")
    return {"status":"freigegeben","hinweis":"Kanzlei wurde informiert"}


# ============================================================
# PORTAL-CHAT
# ============================================================

class ChatTextBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@portal_router.get("/portal/chat", tags=["Portal-Chat"])
def portal_chat_verlauf(
    mandant: str = Depends(hole_mandant),
    limit: int = Query(200, ge=1, le=500),
    seit: Optional[str] = Query(None, description="Nachrichten nach dieser Chat-ID"),
):
    store = _store_for_mandant(mandant)
    nachrichten = pc.list_chat(store, mandant, limit=limit, seit_id=seit)
    return {"nachrichten": nachrichten, "anzahl": len(nachrichten)}


@portal_router.post("/portal/chat", tags=["Portal-Chat"])
def portal_chat_senden(data: ChatTextBody, mandant: str = Depends(hole_mandant)):
    if not bool(setting_holen("portal_nachrichten_aktiv")):
        raise HTTPException(503, "Chat im Mandantenportal ist deaktiviert")
    store = _store_for_mandant(mandant)
    text = data.text.strip()
    msg = pc.chat_text_nachricht(store, mandant, text, "mandant")
    store.kommunikation_hinzufuegen(mandant, {
        "typ": "portal_nachricht",
        "text": text,
        "richtung": "eingehend",
        "timestamp": msg["zeit"],
    })
    m = dict(store.hole_mandanten().get(mandant) or {})
    if m:
        m["letzte_antwort"] = datetime.now().isoformat()
        store.mandant_speichern(mandant, m)
    store.log_eintrag(f"PORTAL_CHAT | {mandant} | mandant")
    return {"status": "gesendet", "nachricht": msg}


# ============================================================
# NACHRICHTEN & SIMULATION (Legacy — Chat bevorzugt)
# ============================================================

@portal_router.post("/portal/nachricht", tags=["Portal"])
def nachricht_senden(data: NachrichtCreate, mandant: str = Depends(hole_mandant)):
    try:
        store = _store_for_mandant(mandant)
        if not bool(setting_holen("portal_nachrichten_aktiv")):
            raise HTTPException(503, "Nachrichten im Mandantenportal sind deaktiviert")
        betreff = (data.betreff or "").strip()
        inhalt = (data.inhalt or "").strip()
        text_voll = f"Betreff: {betreff}\n\n{inhalt}" if betreff else inhalt
        ts = datetime.now().isoformat()
        if not store.kommunikation_hinzufuegen(mandant, {
            "typ": "portal_nachricht",
            "text": text_voll,
            "richtung": "eingehend",
            "timestamp": ts,
        }):
            raise HTTPException(500, "Nachricht konnte nicht gespeichert werden")
        try:
            pc.chat_text_nachricht(store, mandant, text_voll, "mandant")
        except Exception as e:
            log.warning("chat legacy nachricht: %s", e)
        m = dict(store.hole_mandanten().get(mandant) or {})
        if m:
            m["letzte_antwort"] = datetime.now().isoformat()
            store.mandant_speichern(mandant, m)
        store.log_eintrag(f"PORTAL_NACHRICHT | {mandant} | {betreff[:50]}")
        return {"status": "gesendet"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("portal/nachricht fehlgeschlagen (%s): %s", mandant, e)
        raise HTTPException(500, "Nachricht konnte nicht gesendet werden") from e

@portal_router.get("/portal/nachrichten", tags=["Portal"])
def meine_nachrichten(mandant: str = Depends(hole_mandant)):
    store = _store_for_mandant(mandant)
    komm = store.hole_kommunikation(mandant)
    sichtbar = sorted(
        [_komm_zeile_normalisieren(k) for k in komm if k.get("typ") in [
            "portal_nachricht", "kanzlei_antwort", "auto_email", "dokument_unterschrieben",
            "portal_upload", "freigabe_erteilt", "unterschrift_abgelehnt", "unterschrift_anfrage",
        ]],
        key=lambda x: x.get("timestamp", ""),
        reverse=True,
    )
    return {"nachrichten": sichtbar[:20]}

@portal_router.post("/portal/simulation", tags=["Portal"])
def simulation(data: SimulationRequest, mandant: str = Depends(hole_mandant)):
    m         = ds.hole_mandanten().get(mandant,{})
    basis     = m.get("umsatz",0) - m.get("betriebsausgaben",0)
    simuliert = basis + data.zusatz_einnahmen - data.investition - data.abschreibungen - data.sonderausgaben
    st_alt    = round(max(0,basis*0.30),2)
    st_neu    = round(max(0,simuliert*0.30),2)
    ersparnis = round(st_alt-st_neu,2)
    return {"basis_gewinn":round(basis,2),"simulierter_gewinn":round(simuliert,2),
            "steuerlast_aktuell":st_alt,"steuerlast_simuliert":st_neu,
            "steuerersparnis":ersparnis,"monatliche_ersparnis":round(ersparnis/12,2),
            "hinweis":"Schätzung (30% Ø-Steuersatz). Individuelle Beratung empfohlen."}


def register_portal_with_app(main_app: FastAPI) -> None:
    """Portal-Routen, Gateway und Production-Checks an die zentrale FastAPI-App hängen."""
    if getattr(main_app.state, "_portal_merged", False):
        return
    setattr(main_app.state, "_portal_merged", True)
    main_app.include_router(portal_router)

    @main_app.middleware("http")
    async def optional_portal_gateway(request: Request, call_next):
        path = request.url.path
        # Nur echte Mandanten-Routen — /ready, /mandanten, /portal/admin/… nicht blockieren
        if not path.startswith("/portal"):
            return await call_next(request)
        if path.startswith(_PORTAL_KANZLEI_PREFIXES):
            return await call_next(request)
        if not _PORTAL_GATEWAY_KEY:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if path in _PORTAL_GW_EXACT:
            return await call_next(request)
        if any(path.startswith(p) for p in _PORTAL_GW_EXEMPT_PREFIXES):
            return await call_next(request)
        hdr = request.headers.get("X-Api-Gateway-Key") or ""
        if len(hdr) == len(_PORTAL_GATEWAY_KEY) and hmac.compare_digest(
            hdr.encode("utf-8"), _PORTAL_GATEWAY_KEY.encode("utf-8")
        ):
            return await call_next(request)
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            tok = auth.removeprefix("Bearer ").strip()
            if tok and verifiziere_token(tok):
                return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "Zugriff verweigert", "code": 403},
        )

    @main_app.on_event("startup")
    async def portal_production_checks():
        environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
        if environment != "production":
            return
        sec = (os.getenv("PORTAL_SECRET") or "").strip()
        sl = sec.lower()
        if len(sec) < 32 or any(x in sl for x in ("dev-portal", "placeholder", "change-in-prod")):
            raise RuntimeError(
                "Production: PORTAL_SECRET muss mindestens 32 Zeichen haben und keine Dev-Platzhalter enthalten."
            )
        gw = (os.getenv("PORTAL_GATEWAY_KEY") or os.getenv("API_GATEWAY_KEY") or "").strip()
        if gw and len(gw) < 32:
            raise RuntimeError(
                "Production: API_GATEWAY_KEY/PORTAL_GATEWAY_KEY ist gesetzt, aber kürzer als 32 Zeichen."
            )
        if not gw:
            log.warning(
                "Production: kein API_GATEWAY_KEY — Portal/API ohne Gateway-Header-Schutz "
                "(JWT-Login der Kanzlei bleibt aktiv)."
            )