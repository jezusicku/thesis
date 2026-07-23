"""Rejestr metod — jeden punkt wejścia dla UI i skryptów ewaluacji."""
from __future__ import annotations

from typing import List, Tuple

from annotator.features import PersonFeatures
from annotator.wikidata_candidates import WikidataCandidate, fetch_top_candidates

from matchers.fuzzy_wikidata import fetch_fuzzy_candidates
from matchers.phonetic_wikidata import fetch_phonetic_candidates

MATCHER_CHOICES: List[Tuple[str, str]] = [
    (
        "heuristic_rules",
        "Heurystyka — kolejność z wyszukiwarki Wikidata + reguły (lata, miejsce, Q5)",
    ),
    (
        "fuzzy_rerank",
        "RapidFuzz — najpierw podobieństwo tekstu profilu CAC do etykiety/opisu kandydata, potem te same reguły",
    ),
    (
        "phonetic_rerank",
        "Fonetyka DM na etykiecie CAC↔WD (różne formy nazwiska) + RapidFuzz profil↔opis — potem te same reguły",
    ),
]


def fetch_candidates(
    method_id: str,
    search_query: str,
    feats: PersonFeatures,
    *,
    top_k: int = 3,
    search_limit: int = 12,
) -> List[WikidataCandidate]:
    q = search_query.strip() or feats.label_clean
    common = dict(
        cac_birth_year=feats.birth_year,
        cac_study_year=feats.study_year,
        cac_birthplace_raw=feats.birthplace,
        cac_place_norm=feats.birthplace_normalized or feats.birthplace,
        top_k=top_k,
        search_limit=search_limit,
    )
    if method_id == "heuristic_rules":
        return fetch_top_candidates(
            q,
            cac_activity_fallback_year=feats.life_anchor_year,
            **common,
        )
    if method_id == "fuzzy_rerank":
        return fetch_fuzzy_candidates(
            q, feats, cac_activity_fallback_year=feats.life_anchor_year, **common
        )
    if method_id == "phonetic_rerank":
        return fetch_phonetic_candidates(
            q,
            feats,
            cac_activity_fallback_year=feats.life_anchor_year,
            **common,
        )
    raise ValueError(f"Nieznana metoda: {method_id}")
