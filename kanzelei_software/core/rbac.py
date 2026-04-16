from typing import Dict, Set


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        "*",
    },
    "steuerberater": {
        "mandanten:read", "mandanten:write",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "settings:read",
        "reports:read",
        "engine:run", "engine:read",
        "email:send",
        "export:read",
    },
    "assistent": {
        "mandanten:read",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "settings:read",
        "reports:read",
        "email:send",
    },
    "mitarbeiter": {
        "mandanten:read",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "settings:read",
        "reports:read",
        "email:send",
    },
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get((role or "").strip().lower(), set())
    return "*" in perms or permission in perms
