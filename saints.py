"""
saints.py - Calendrier des saints pour FidesIA
Charge le fichier saints.json et fournit le saint du jour
selon le calendrier catholique romain.
"""

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}

MONTHS_FR_REV = {v: k for k, v in MONTHS_FR.items()}

_saints: list[dict] = []
_by_date: dict[tuple[int, int], list[dict]] = {}
_by_id: dict[str, dict] = {}


def _parse_fete(fete_str: str):
    """Parse '19 mars' → (3, 19) ou None."""
    parts = fete_str.strip().split(" ", 1)
    if len(parts) == 2:
        try:
            day = int(parts[0])
            month = MONTHS_FR.get(parts[1].lower())
            if month:
                return (month, day)
        except ValueError:
            pass
    return None


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

    logger.info(f"Saints chargés: {len(_saints)} saints, {len(_by_date)} dates")


def get_saint_today() -> list[dict]:
    """Retourne le(s) saint(s) du jour (compact, pour la sidebar)."""
    today = date.today()
    saints = _by_date.get((today.month, today.day), [])
    return [_compact(s) for s in saints]


def get_saint_by_id(saint_id: str) -> dict | None:
    """Retourne les détails complets d'un saint."""
    return _by_id.get(saint_id)


def _compact(s: dict) -> dict:
    """Version compacte pour l'affichage sidebar."""
    return {
        "id": s["id"],
        "nom": s["nom"],
        "titres": s.get("titres", []),
        "fete": s.get("fete", ""),
    }
