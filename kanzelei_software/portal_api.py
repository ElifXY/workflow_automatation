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
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from core.daten_speicher import DatenSpeicher
from modules.settings_manager import setting_holen

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
TOKEN_STUNDEN = int(os.getenv("PORTAL_TOKEN_STUNDEN", "168"))
UPLOAD_MAX_MB = int(os.getenv("PORTAL_UPLOAD_MAX_MB", "20"))

_PORTAL_GATEWAY_KEY = (os.getenv("PORTAL_GATEWAY_KEY") or os.getenv("API_GATEWAY_KEY") or "").strip()
_PORTAL_GW_EXEMPT_PREFIXES = ("/portal/docs", "/portal/openapi.json", "/openapi.json")
_PORTAL_GW_EXACT = frozenset({"/portal/health"})


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
        if mandant not in ds.hole_mandanten(): return None
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

def _portal() -> Dict:
    return {
        "portal": {
            "uploads": {
                x["id"]: x for x in ds.portal_liste("upload") if x.get("id")
            },
            "unterschriften": {
                x["id"]: x for x in ds.portal_liste("unterschrift") if x.get("id")
            },
            "freigaben": {
                x["id"]: x for x in ds.portal_liste("freigabe") if x.get("id")
            },
        }
    }

def _save_portal(data: Dict):
    portal = (data or {}).get("portal", {})
    for x in (portal.get("uploads") or {}).values():
        rid = x.get("id")
        if rid:
            ds.portal_speichern("upload", rid, x.get("mandant", ""), x)
    for x in (portal.get("unterschriften") or {}).values():
        rid = x.get("id")
        if rid:
            ds.portal_speichern("unterschrift", rid, x.get("mandant", ""), x)
    for x in (portal.get("freigaben") or {}).values():
        rid = x.get("id")
        if rid:
            ds.portal_speichern("freigabe", rid, x.get("mandant", ""), x)


# ── MODELS ───────────────────────────────────────────────────

class NachrichtCreate(BaseModel):
    betreff: str = Field(..., min_length=2, max_length=200)
    inhalt:  str = Field(..., min_length=5, max_length=5000)

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
def portal_login(token: str = Query(...)):
    mandant = verifiziere_token(token)
    if not mandant:
        raise HTTPException(401, "Ungültiger oder abgelaufener Zugangslink")
    m = ds.hole_mandanten().get(mandant, {})

    p = _portal()
    offen_unterschriften = sum(
        1 for u in p["portal"]["unterschriften"].values()
        if u.get("mandant") == mandant and u.get("status") == "ausstehend"
    )
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
    aufgaben = [a for a in ds.hole_fristen().values() if a.get("mandant")==mandant]
    jetzt    = datetime.now()
    result   = []
    for a in aufgaben:
        try:    tage = (datetime.strptime(a["frist"],"%Y-%m-%d")-jetzt).days; dringend = not a.get("erledigt") and tage<=3
        except: tage = None; dringend = False
        result.append({"beschreibung":a.get("beschreibung",""),"frist":a.get("frist",""),
                        "erledigt":a.get("erledigt",False),"prioritaet":a.get("prioritaet","normal"),
                        "tage":tage,"dringend":dringend})
    result.sort(key=lambda x:(x["erledigt"],x["tage"] or 9999))
    return {"aufgaben":result,"offen":sum(1 for a in result if not a["erledigt"])}

@portal_router.get("/portal/dokumente", tags=["Portal"])
def fehlende_dokumente(mandant: str = Depends(hole_mandant)):
    m = ds.hole_mandanten().get(mandant,{})
    fehlende = m.get("fehlende_dokumente_liste",[])
    return {"fehlende_dokumente":fehlende,"anzahl":len(fehlende),
            "hinweis":"Bitte hochladen." if fehlende else "Alle vollständig ✓"}


# ============================================================
# DOKUMENT-UPLOAD
# ============================================================

def _verarbeite_upload(mandant: str, data: DokumentUpload) -> Dict:
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

    p = _portal()
    uid = str(uuid.uuid4())
    p["portal"]["uploads"][uid] = {
        "id":uid,"mandant":mandant,"dateiname":dateiname,
        "original":data.dateiname,"dateipfad":dateipfad,
        "groesse_kb":round(len(inhalt)/1024,1),
        "kategorie":data.kategorie or "Sonstiges",
        "projektnummer": str(data.projektnummer or "").strip(),
        "beschreibung":data.beschreibung or "",
        "hochgeladen_am":datetime.now().isoformat(),
    }
    _save_portal(p)

    # Fehlende Docs abgleichen
    m = ds.hole_mandanten().get(mandant,{})
    fehlende = m.get("fehlende_dokumente_liste",[])
    gefunden = next((d for d in fehlende if d.lower() in data.dateiname.lower() or data.dateiname.lower() in d.lower()),None)
    if gefunden:
        fehlende.remove(gefunden)
        m["fehlende_dokumente_liste"] = fehlende
        m["letzte_antwort"] = datetime.now().isoformat()
        ds.mandant_speichern(mandant, m)

    ds.kommunikation_hinzufuegen(mandant,{
        "typ":"portal_upload","text":f"Hochgeladen: {data.dateiname} ({round(len(inhalt)/1024,1)} KB)",
        "kategorie":data.kategorie,"timestamp":datetime.now().isoformat()})
    ds.log_eintrag(f"PORTAL_UPLOAD | {mandant} | {data.dateiname} | {len(inhalt)} bytes")

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
    p = _portal()
    uploads = sorted(
        [u for u in p["portal"]["uploads"].values() if u.get("mandant")==mandant],
        key=lambda x: x.get("hochgeladen_am",""), reverse=True)
    return {"uploads":uploads,"anzahl":len(uploads)}


# ============================================================
# ✍ DIGITALE UNTERSCHRIFT
# ============================================================

@portal_router.post("/portal/unterschrift/anfragen", tags=["Unterschrift"])
def unterschrift_anfragen(data: UnterschriftAnfragen):
    """
    KANZLEI sendet Dokument zur Unterzeichnung.
    Rechtsbasis: Einfache Elektronische Signatur (EES) nach eIDAS Art. 3 Nr. 10.
    Gültig für: Vollmachten, Mandatsverträge, Jahresabschluss-Freigaben.
    """
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    if not secrets.compare_digest(data.admin_key, os.getenv("PORTAL_ADMIN_KEY","kanzlei-admin-2024")):
        raise HTTPException(403, "Ungültiger Admin-Key")
    if data.mandant not in ds.hole_mandanten():
        raise HTTPException(404, f"Mandant '{data.mandant}' nicht gefunden")

    uid = str(uuid.uuid4())
    p   = _portal()
    p["portal"]["unterschriften"][uid] = {
        "id":            uid,
        "mandant":       data.mandant,
        "dokumentname":  data.dokumentname,
        "dokument_b64":  data.dokument_b64,
        "dokumenttyp":   data.dokumenttyp,
        "betreff":       data.betreff,
        "hinweis":       data.hinweis,
        "status":        "ausstehend",
        "erstellt_am":   datetime.now().isoformat(),
        "gueltig_bis":   (datetime.now()+timedelta(days=data.gueltig_tage)).isoformat(),
        "audit_trail":   [{"aktion":"anfrage_erstellt","zeitpunkt":datetime.now().isoformat()}],
        "unterschrift_b64":  None,
        "unterschrieben_am": None,
        "unterzeichner_info":None,
    }
    _save_portal(p)
    ds.log_eintrag(f"UNTERSCHRIFT_ANFRAGE | {data.mandant} | {data.dokumentname} | ID:{uid[:8]}")
    return {"unterschrift_id":uid,"mandant":data.mandant,"dokument":data.dokumentname,
            "gueltig_bis":p["portal"]["unterschriften"][uid]["gueltig_bis"],"status":"ausstehend"}

@portal_router.get("/portal/unterschrift/offen", tags=["Unterschrift"])
def offene_unterschriften(mandant: str = Depends(hole_mandant)):
    """Mandant sieht alle offenen Unterschriftsanfragen."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    p     = _portal()
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
    return {"unterschriften":sorted(offene,key=lambda x:x["erstellt_am"],reverse=True),
            "anzahl":len(offene)}

@portal_router.get("/portal/unterschrift/{uid}/dokument", tags=["Unterschrift"])
def dokument_herunterladen(uid: str, mandant: str = Depends(hole_mandant)):
    """Zu unterzeichnendes Dokument abrufen."""
    if not bool(setting_holen("portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    p = _portal()
    u = p["portal"]["unterschriften"].get(uid)
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
    p = _portal()
    u = p["portal"]["unterschriften"].get(uid)
    if not u: raise HTTPException(404, "Nicht gefunden")
    if u.get("mandant") != mandant: raise HTTPException(403, "Kein Zugriff")
    if u.get("status") != "ausstehend": raise HTTPException(400, f"Status: {u.get('status')}")
    if not data.bestaetigung: raise HTTPException(400, "Bitte Kenntnisnahme bestätigen")
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
    u["audit_trail"].append({
        "aktion":    "unterschrieben",
        "zeitpunkt": jetzt.isoformat(),
        "ip":        data.ip_adresse or client_ip,
        "user_agent":user_agent[:100],
        "details":   f"Digital unterzeichnet von {mandant} — eIDAS EES",
    })
    _save_portal(p)

    ds.kommunikation_hinzufuegen(mandant,{
        "typ":"dokument_unterschrieben",
        "text":f"Dokument unterzeichnet: {u['dokumentname']}",
        "unterschrift_id":uid,"timestamp":jetzt.isoformat()})
    ds.log_eintrag(f"UNTERSCHRIEBEN | {mandant} | {u['dokumentname']} | IP:{client_ip}")

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
# NACHRICHTEN & SIMULATION
# ============================================================

@portal_router.post("/portal/nachricht", tags=["Portal"])
def nachricht_senden(data: NachrichtCreate, mandant: str = Depends(hole_mandant)):
    ds.kommunikation_hinzufuegen(mandant,{"typ":"portal_nachricht","betreff":data.betreff,
        "text":data.inhalt,"timestamp":datetime.now().isoformat(),"gelesen":False})
    m = ds.hole_mandanten().get(mandant,{})
    m["letzte_antwort"] = datetime.now().isoformat()
    ds.mandant_speichern(mandant, m)
    ds.log_eintrag(f"PORTAL_NACHRICHT | {mandant} | {data.betreff[:50]}")
    return {"status":"gesendet"}

@portal_router.get("/portal/nachrichten", tags=["Portal"])
def meine_nachrichten(mandant: str = Depends(hole_mandant)):
    komm = ds.hole_kommunikation(mandant)
    sichtbar = sorted(
        [k for k in komm if k.get("typ") in ["portal_nachricht","auto_email",
         "dokument_unterschrieben","portal_upload","freigabe_erteilt","unterschrift_abgelehnt"]],
        key=lambda x: x.get("timestamp",""), reverse=True)
    return {"nachrichten":sichtbar[:20]}

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
        if not _PORTAL_GATEWAY_KEY:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
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