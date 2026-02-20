"""
saints.py - Calendrier des saints pour FidesIA
Charge le fichier saints.json et fournit le saint du jour
selon le calendrier catholique romain.

Rangs liturgiques (par ordre d'importance) :
  Solennité > Fête > Mémoire obligatoire > Mémoire facultative
"""

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}

MONTHS_FR_REV = {v: k for k, v in MONTHS_FR.items()}

# Tri par importance liturgique (plus petit = plus important)
RANG_ORDER = {
    "Solennité": 0,
    "Fête": 1,
    "Mémoire obligatoire": 2,
    "Mémoire facultative": 3,
}

_saints: list[dict] = []
_by_date: dict[tuple[int, int], list[dict]] = {}
_by_id: dict[str, dict] = {}


def _parse_fete(fete_str: str) -> Optional[tuple[int, int]]:
    """Parse '19 mars' ou '1er janvier' → (month, day) ou None."""
    parts = fete_str.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    day_str = parts[0]
    month_str = parts[1].lower()

    # Extraire le jour : "1er" → 1, "25" → 25
    match = re.match(r"(\d+)", day_str)
    if not match:
        return None
    day = int(match.group(1))

    month = MONTHS_FR.get(month_str)
    if not month:
        return None

    return (month, day)


def init_saints(json_path: str = None):
    """Charge le fichier saints.json au démarrage."""
    global _saints, _by_date, _by_id

    if json_path is None:
        json_path = Path(__file__).parent / "data" / "saints.json"

    path = Path(json_path)
    if not path.exists():
        logger.warning(f"Fichier saints introuvable: {path}")
        return

    with open(path, encoding="utf-8") as f:
        _saints = json.load(f)

    _by_date.clear()
    _by_id.clear()

    for s in _saints:
        _by_id[s["id"]] = s
        parsed = _parse_fete(s.get("fete", ""))
        if parsed:
            _by_date.setdefault(parsed, []).append(s)

    # Trier chaque jour par rang liturgique (solennités d'abord)
    for key in _by_date:
        _by_date[key].sort(key=lambda s: RANG_ORDER.get(s.get("rang_liturgique", ""), 99))

    logger.info(f"Saints chargés: {len(_saints)} saints, {len(_by_date)} dates")


def get_saint_today() -> list[dict]:
    """Retourne le(s) saint(s) du jour (compact, pour la sidebar)."""
    today = date.today()
    saints = _by_date.get((today.month, today.day), [])
    return [_compact(s) for s in saints]


def get_saint_by_id(saint_id: str) -> Optional[dict]:
    """Retourne les détails complets d'un saint."""
    return _by_id.get(saint_id)


def _compact(s: dict) -> dict:
    """Version compacte pour l'affichage sidebar."""
    return {
        "id": s["id"],
        "nom": s["nom"],
        "titres": s.get("titres", []),
        "fete": s.get("fete", ""),
        "rang_liturgique": s.get("rang_liturgique", ""),
    }
