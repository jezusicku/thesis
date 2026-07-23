"""Metoda: ta sama pula wbsearchentities, kolejność wg hybrydy RapidFuzz + Dice–Sørensen na tokenach z DM (fonetyka)."""
from __future__ import annotations

import time
from typing import List, Optional

from rapidfuzz import fuzz

from annotator.features import PersonFeatures
from annotator.phonetic_polish import phonetic_dice_between_strings
from annotator.wikidata_candidates import (
    WikidataCandidate,
    rank_candidates,
    sparql_enrich_birth_place,
    sparql_humans_among,
    wb_search_entities,
)

from matchers.cac_profile import build_cac_profile_text

MID = "phonetic_rerank"
MLABEL = (
    "Fonetyka DM na etykiecie (CAC ↔ WD) + RapidFuzz profil↔etykieta/opis + reguły"
)


def fetch_phonetic_candidates(
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
    # Fonetyka liczona na **samych etykietach** (imię/nazwisko — różne zapisy historyczne vs WD).
    phonetic_label_weight: float = 0.55,
    # RapidFuzz na pełnym profilu CAC vs etykieta+opis WD (kontekst: miejsce, zawód w opisie).
    fuzzy_profile_weight: float = 0.45,
) -> List[WikidataCandidate]:
    """
    Kluczowe: **Dice–Sørensen / DM porównuje tekst CAC użyty jako fraza wyszukiwania (etykieta)
    z etykietą kandydata na Wikidata** — tam właśnie widać Nawrocki vs Nawrocky itd.

    Drugi składnik to RapidFuzz między **bogatym profilem CAC** a etykietą+opisem (jak w fuzzy),
    żeby nadal uwzględniać miejsca i kontekst po ułożeniu listy wg nazwiska.
    """
    cac_label = (search_query.strip() or feats.label_clean or "").strip()
    profile = build_cac_profile_text(feats) or cac_label
    hits = wb_search_entities(search_query, language="pl", limit=search_limit)

    def combined_key(h: dict) -> float:
        wd_label = (h.get("label") or "").strip()
        blob = f"{wd_label} {h.get('description') or ''}"
        # 1) Fonetyka wyłącznie na parze etykiet (formy nazwiska / imion).
        dice_on_labels = phonetic_dice_between_strings(cac_label, wd_label)
        # 2) Kontekst z całego profilu vs snippet WD (jak metoda fuzzy).
        fz_profile = float(fuzz.token_set_ratio(profile, blob))
        return phonetic_label_weight * (dice_on_labels * 100.0) + fuzzy_profile_weight * fz_profile

    hits = sorted(hits, key=lambda h: -combined_key(h))
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
