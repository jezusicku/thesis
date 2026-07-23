"""Metoda 2: ta sama baza kandydatów z Wikidata, inna kolejność — RapidFuzz vs profil tekstowy z CAC."""
from __future__ import annotations

import time
from typing import List, Optional

from rapidfuzz import fuzz

from annotator.features import PersonFeatures
from annotator.wikidata_candidates import (
    rank_candidates,
    sparql_enrich_birth_place,
    sparql_humans_among,
    wb_search_entities,
)

from matchers.cac_profile import build_cac_profile_text

MID = "fuzzy_rerank"
MLABEL = "RapidFuzz (kolejność wyników wg podobieństwa do profilu CAC) + reguły"


def fetch_fuzzy_candidates(
    search_query: str,
    feats: PersonFeatures,
    *,
    cac_birth_year: Optional[int],
    cac_study_year: Optional[int],
    cac_birthplace_raw: Optional[str],
    cac_place_norm: Optional[str],
    cac_activity_fallback_year: Optional[int] = None,
    top_k: int = 3,
    search_limit: int = 12,
    pause_sec: float = 0.35,
) -> List:
    profile = build_cac_profile_text(feats) or (search_query.strip() or feats.label_clean)
    hits = wb_search_entities(search_query, language="pl", limit=search_limit)

    def fuzzy_key(h: dict) -> float:
        blob = f"{h.get('label') or ''} {h.get('description') or ''}"
        return float(fuzz.token_set_ratio(profile, blob))

    hits = sorted(hits, key=lambda h: -fuzzy_key(h))
    time.sleep(pause_sec)
    qids = [h["id"] for h in hits if h.get("id")]
    enrich = sparql_enrich_birth_place(qids) if qids else {}
    time.sleep(pause_sec)
    humans = sparql_humans_among(qids) if qids else set()
    time.sleep(pause_sec)
    return rank_candidates(
        hits,
        enrich,
        humans,
        cac_birth_year=cac_birth_year,
        cac_study_year=cac_study_year,
        cac_birthplace_raw=cac_birthplace_raw,
        cac_place_norm=cac_place_norm,
        cac_activity_fallback_year=cac_activity_fallback_year,
        top_k=top_k,
        matcher_id=MID,
        matcher_label=MLABEL,
    )
