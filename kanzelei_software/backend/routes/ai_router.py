"""
AI router extracted from ``api.py``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.deps import get_current_user
from core.ai_guardrails import guard_input_text
from core.ai_service import assistant_chat

router = APIRouter(tags=["KI-Assistent"])


def _root():
    import api as root

    return root


class KIChatRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    system: Optional[str] = None
    max_tokens: int = 1200
    mandant: Optional[str] = None


class ChatThreadItem(BaseModel):
    id: str
    title: str = "Gespräch"
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    createdAt: int = 0
    updatedAt: int = 0
    pinned: bool = False


class ChatThreadsPayload(BaseModel):
    active_id: Optional[str] = ""
    threads: List[ChatThreadItem] = Field(default_factory=list)


def _chat_store_key(user: dict) -> str:
    kid = user.get("tenant_id") or user.get("kanzlei_id") or "default"
    uid = user.get("id") or user.get("user_id") or user.get("benutzername") or "anon"
    return f"__ki_chat_threads_v1::{kid}::{uid}"


def _sanitize_threads(raw_threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in raw_threads[:120]:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        msgs = []
        for m in (t.get("messages") or [])[:80]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(m.get("content") or "")[:4000]
            display = str(m.get("display") or "")[:4000]
            item = {"role": role, "content": content}
            if display:
                item["display"] = display
            if m.get("error") is True:
                item["error"] = True
            msgs.append(item)
        out.append(
            {
                "id": tid[:80],
                "title": str(t.get("title") or "Gespräch")[:120],
                "messages": msgs,
                "createdAt": int(t.get("createdAt") or 0),
                "updatedAt": int(t.get("updatedAt") or 0),
                "pinned": bool(t.get("pinned") or False),
            }
        )
    return out


def _is_weak_ai_answer(text: str) -> bool:
    t = str(text or "").strip().lower()
    if not t:
        return True
    return (
        "nicht genug daten" in t
        or "keine mandanten" in t
        or "insufficient data" in t
        or "not enough data" in t
    )


def _build_kanzlei_fallback_answer(store, user_prompt: str, selected_mandant: Optional[str]) -> str:
    mandanten = store.hole_mandanten() or {}
    fristen = list((store.hole_fristen() or {}).values())
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = str(user_prompt or "").lower()

    by_mandant: Dict[str, Dict[str, int]] = {}
    for f in fristen:
        m = str(f.get("mandant") or "").strip()
        if not m:
            continue
        status = by_mandant.setdefault(m, {"offen": 0, "ueberfaellig": 0, "erledigt": 0})
        if f.get("erledigt"):
            status["erledigt"] += 1
        else:
            status["offen"] += 1
            if str(f.get("frist") or "9999-12-31") < today:
                status["ueberfaellig"] += 1

    rows: List[Dict[str, Any]] = []
    for name, m in (mandanten or {}).items():
        s = by_mandant.get(name, {"offen": 0, "ueberfaellig": 0, "erledigt": 0})
        rows.append(
            {
                "name": name,
                "umsatz": float(m.get("umsatz") or 0),
                "offen": int(s["offen"]),
                "ueberfaellig": int(s["ueberfaellig"]),
            }
        )

    rows.sort(key=lambda x: (x["ueberfaellig"], x["offen"], x["umsatz"]), reverse=True)
    kritisch = sum(1 for r in rows if r["ueberfaellig"] > 0)
    top = rows[:5]

    if selected_mandant and selected_mandant in mandanten:
        mm = mandanten.get(selected_mandant, {})
        ss = by_mandant.get(selected_mandant, {"offen": 0, "ueberfaellig": 0, "erledigt": 0})
        return (
            f"**Einschätzung**\nFür **{selected_mandant}** sind verwertbare Kanzleidaten vorhanden.\n\n"
            f"**Aktuelle Daten**\n"
            f"- Umsatz: €{float(mm.get('umsatz') or 0):,.0f}\n"
            f"- Offene Aufgaben: {ss['offen']}\n"
            f"- Überfällige Aufgaben: {ss['ueberfaellig']}\n\n"
            f"**Nächste Schritte**\n"
            f"- Überfällige Punkte zuerst priorisieren\n"
            f"- Fristen dieser Woche aktiv absichern\n"
            f"- Bei Bedarf erstelle ich direkt einen 7-Tage-Maßnahmenplan"
        )

    if "compliance" in prompt or "risiko" in prompt or "frist" in prompt:
        if not rows:
            return (
                "**Einschätzung**\nAktuell sind noch keine Mandanten-/Fristendaten verfügbar.\n\n"
                "**Nächste Schritte**\n"
                "- Mandanten und Fristen laden\n"
                "- Danach Compliance-Risikoanalyse erneut ausführen"
            )
        lines = [
            f"{idx}. **{r['name']}** - Überfällige Aufgaben: {r['ueberfaellig']}, Offene Aufgaben: {r['offen']}"
            for idx, r in enumerate(top, start=1)
        ]
        return (
            "**Einschätzung**\nDie größten Compliance-Risiken entstehen aktuell aus überfälligen Fristen und offenen Aufgaben.\n\n"
            "**Top-Risiko-Mandanten**\n"
            + "\n".join(lines)
            + "\n\n**Risiko**\n"
            + f"- Mandanten mit überfälligen Aufgaben: {kritisch}\n"
            + f"- Gesamt-Mandanten: {len(rows)}\n\n"
            + "**Nächste Schritte**\n"
            + "- Top 3 Risikofälle heute bearbeiten\n"
            + "- Fristenkontrolle für diese Woche verbindlich einplanen\n"
            + "- Für kritische Fälle Rückruf-/Dokumentationspflicht sofort auslösen"
        )

    return (
        "Ich habe Zugriff auf deine Kanzleidaten und kann direkt mit Priorisierung, Fristen-Check "
        "und konkreten Handlungsempfehlungen helfen. Wenn du willst, starte ich mit den "
        "dringendsten Fällen für heute."
    )


@router.post("/ki/chat", summary="KI-Chat — Backend Proxy für OpenAI GPT-4o mini")
async def ki_chat(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = KIChatRequest(**data)
    system_text = guard_input_text(payload.system or "")
    store = root.get_ds(_user)
    if payload.mandant:
        try:
            m = store.hole_mandanten().get(payload.mandant, {})
            aufgaben = [a for a in store.hole_fristen().values() if a.get("mandant") == payload.mandant]
            offen = sum(1 for a in aufgaben if not a.get("erledigt"))
            ueberfaellig = sum(
                1
                for a in aufgaben
                if not a.get("erledigt") and a.get("frist", "9999") < datetime.now().strftime("%Y-%m-%d")
            )
            system_text += (
                f"\n\nAKTUELLER MANDANT-KONTEXT:\n"
                f"- Name: {payload.mandant}\n"
                f"- Jahresumsatz: €{m.get('umsatz', 0):,.0f}\n"
                f"- Branche: {m.get('branche', '—')}\n"
                f"- Aufgaben offen: {offen}\n"
                f"- Aufgaben überfällig: {ueberfaellig}\n"
                f"- Tage ohne Antwort: {store.berechne_tage_ohne_antwort(payload.mandant)}"
            )
        except Exception:
            pass

    try:
        result = await assistant_chat(
            history=payload.messages[-20:],
            system_text=system_text,
            max_tokens=payload.max_tokens,
            mandant=payload.mandant,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc or "").lower()
        if "exceeded your current quota" in msg or "insufficient_quota" in msg:
            raise HTTPException(
                status_code=402,
                detail=(
                    "OpenAI-Quota erreicht. Bitte im OpenAI-Dashboard das Projekt-Budget/Limit "
                    "erhoehen oder einen API-Key aus dem korrekten Projekt verwenden."
                ),
            ) from exc
        if "api key" in msg or "invalid_api_key" in msg:
            raise HTTPException(
                status_code=401,
                detail="OpenAI API-Key ungueltig oder nicht fuer dieses Projekt freigeschaltet.",
            ) from exc
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {str(exc)[:220]}") from exc
    return {
        "content": _build_kanzlei_fallback_answer(store, payload.messages[-1].get("content", ""), payload.mandant)
        if _is_weak_ai_answer(result.content)
        else result.content,
        "tokens_used": result.tokens_used,
        "modell": result.modell,
    }


@router.get("/ki/status", summary="KI-Verfügbarkeit prüfen")
def ki_status(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.ki_status(_user)


@router.get("/ki/chats", summary="Gespeicherte KI-Chatverläufe laden")
def ki_chats_get(_user: dict = Depends(get_current_user)):
    root = _root()
    store = root.get_ds(_user)
    key = _chat_store_key(_user)
    raw = store.setting_holen(key, {}) or {}
    threads = _sanitize_threads(raw.get("threads") or [])
    active_id = str(raw.get("active_id") or "")
    return {
        "threads": threads,
        "active_id": active_id,
        "scope": {
            "tenant_id": str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default"),
            "user_id": str(_user.get("id") or _user.get("user_id") or _user.get("benutzername") or "anon"),
            "role": str(_user.get("rolle") or _user.get("role") or ""),
            "email": str(_user.get("email") or ""),
        },
    }


@router.put("/ki/chats", summary="Gespeicherte KI-Chatverläufe speichern")
def ki_chats_put(payload: ChatThreadsPayload, _user: dict = Depends(get_current_user)):
    root = _root()
    store = root.get_ds(_user)
    key = _chat_store_key(_user)
    data = {
        "threads": _sanitize_threads([t.model_dump() for t in payload.threads]),
        "active_id": str(payload.active_id or ""),
    }
    ok = store.setting_setzen(key, data)
    if not ok:
        raise HTTPException(status_code=500, detail="Chatverlauf konnte nicht gespeichert werden")
    return {"ok": True}


@router.get("/ki/mandant-analyse/{name}", summary="Tiefe AI-Analyse eines Mandanten via OpenAI")
async def ki_mandant_analyse(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return await root.ki_mandant_analyse(name, _user)


@router.get("/ki/kanzlei-zusammenfassung", summary="AI-Zusammenfassung der gesamten Kanzlei")
async def ki_kanzlei_zusammenfassung(_user: dict = Depends(get_current_user)):
    root = _root()
    return await root.ki_kanzlei_zusammenfassung(_user)

