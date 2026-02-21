"""
analytics.py - Agrégation des métriques admin pour FidesIA
Dashboard data: KPIs, questions/jour, keywords, géoloc IP, reconnexion.
"""

import json
import logging
import re
import urllib.request
from collections import Counter
from typing import Dict, Any, List

from database import (
    get_events_summary, get_all_questions, get_unresolved_ips,
    save_ip_geo, get_ip_geo_map, get_reconnection_stats,
)

logger = logging.getLogger(__name__)

# Stop words français (mots trop courants à ignorer)
_STOP_WORDS = {
    "avec", "dans", "pour", "plus", "tout", "bien", "comme", "mais", "nous",
    "vous", "quel", "quoi", "sont", "peut", "fait", "elle", "sera", "très",
    "aussi", "même", "sans", "autre", "cette", "être", "avoir", "faire",
    "dire", "aller", "voir", "dont", "encore", "entre", "après", "avant",
    "leur", "leurs", "notre", "votre", "tous", "toute", "toutes", "rien",
    "quand", "comment", "pourquoi", "quel", "quelle", "quels", "quelles",
    "elles", "ceux", "celles", "chaque", "depuis", "selon", "sous",
    "vers", "chez", "aucun", "aucune", "moins", "alors", "donc",
    "parce", "lorsque", "tandis", "pendant", "cela", "ceci", "celui",
    "celle", "mieux", "peux", "veut", "dois", "doit", "faut",
    "dit", "est", "une", "des", "les", "par", "sur", "que",
    "qui", "pas", "aux", "ces", "son", "ses", "mes", "tes",
    "église", "saint", "dieu",
}


def _extract_keywords(questions: List[str], top_n: int = 10) -> List[Dict[str, Any]]:
    """Extrait les top N mots-clés des questions utilisateurs."""
    counter = Counter()
    for q in questions:
        words = re.findall(r"[a-zA-Zéèêëàâäùûüôöîïçœ]+", q.lower())
        for w in words:
            if len(w) >= 4 and w not in _STOP_WORDS:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]


def _resolve_ips(ips: List[str]):
    """Résout les IPs via ip-api.com batch API (stdlib) et cache les résultats."""
    if not ips:
        return
    for i in range(0, len(ips), 100):
        batch = ips[i:i + 100]
        try:
            payload = json.dumps([{"query": ip} for ip in batch]).encode()
            req = urllib.request.Request(
                "http://ip-api.com/batch?fields=query,country,city,regionName",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                results = json.loads(resp.read().decode())
                for r in results:
                    if isinstance(r, dict) and r.get("query"):
                        save_ip_geo(
                            r["query"],
                            r.get("country", ""),
                            r.get("city", ""),
                            r.get("regionName", ""),
                        )
        except Exception as e:
            logger.warning(f"IP geoloc batch failed: {e}")


def get_dashboard_data(days: int = 30) -> Dict[str, Any]:
    """Assemble toutes les métriques du dashboard admin."""
    summary = get_events_summary(days)

    # Résoudre les IPs non encore géolocalisées
    unresolved = get_unresolved_ips(days)
    if unresolved:
        _resolve_ips(unresolved)

    # Enrichir les IPs avec les données géo
    geo_map = get_ip_geo_map()
    ip_connections = []
    for ip_row in summary["ip_connections"]:
        ip = ip_row["ip"]
        geo = geo_map.get(ip, {})
        ip_connections.append({
            "ip": ip,
            "city": geo.get("city", ""),
            "country": geo.get("country", ""),
            "region": geo.get("region", ""),
            "visits": ip_row["visits"],
            "sessions": ip_row["sessions"],
            "last_seen": ip_row["last_seen"],
        })

    # Mots-clés des questions
    questions = get_all_questions(days)
    keywords = _extract_keywords(questions)

    # Reconnexion
    reconnection = get_reconnection_stats(days)

    # KPIs
    total_questions = summary["guest_questions"] + summary["auth_questions"]

    return {
        "kpis": {
            "total_questions": total_questions,
            "guest_questions": summary["guest_questions"],
            "auth_questions": summary["auth_questions"],
            "total_views": summary["total_views"],
            "logins": summary["logins"],
            "registers": summary["registers"],
        },
        "questions_per_day": summary["questions_per_day"],
        "ip_connections": ip_connections,
        "click_stats": summary["click_stats"],
        "top_examples": summary["top_examples"],
        "top_keywords": keywords,
        "reconnection": reconnection,
    }
