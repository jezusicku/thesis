"""Pobieranie i punktacja kandydatów z Wikidata (API + SPARQL)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from extract_data.matching_birth_places import place_matching_strings

WD_API = "https://www.wikidata.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JU_heritage/1.0 (educational; Python requests)"})
# Wikidata często zwraca 429 przy zbyt gwałtownym ruchu — ponawianie z backoff.
_retry = Retry(
    total=8,
    connect=5,
    read=5,
    backoff_factor=1.2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET", "POST"),
)
SESSION.mount("https://", HTTPAdapter(max_retries=_retry))


@dataclass
class WikidataCandidate:
    qid: str
    label: str
    description: str
    uri: str
    birth_year_wd: Optional[int]
    death_year_wd: Optional[int]
    birth_place_labels: str
    occupation_labels: str
    is_human: bool
    score: float
    score_reasons: List[str]
    matcher_id: str = "heuristic_rules"
    matcher_label: str = "Heurystyka (reguły + SPARQL)"


def _year_from_wd_literal(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    s = str(val).strip()
    m = re.search(r"([+-]?\d{3,4})", s)
    if not m:
        return None
    y = int(m.group(1))
    if -4000 <= y <= 2100:
        return y
    return None


def _year_span_from_description(text: str) -> Optional[tuple[int, int]]:
    """
    Wyciąga przedział lat z opisu API / etykiety (gdy brak P569 w SPARQL).
    Obsługuje m.in. [dates:1875-1879] z Polskiego Archiwum Biograficznego na Wikidata.
    """
    if not (text or "").strip():
        return None
    s = text
    # [dates:1875-1879] lub [dates: 1875 – 1879]
    m = re.search(
        r"\[dates:\s*(\d{3,4})\s*[-–—]\s*(\d{3,4})\s*\]",
        s,
        re.I,
    )
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1000 <= a <= 2100 and 1000 <= b <= 2100:
            return (min(a, b), max(a, b))
    # (1875-1879) lub 1875–1879 jako zakres życia / działalności
    m = re.search(r"\((\d{3,4})\s*[-–—]\s*(\d{3,4})\)", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1000 <= a <= 2100 and 1000 <= b <= 2100:
            return (min(a, b), max(a, b))
    m = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\s*[-–—]\s*(1[0-9]{3}|20[0-2][0-9])\b", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if abs(a - b) <= 120:  # odrzuć „77468–123” itp.
            return (min(a, b), max(a, b))
    return None


def _wd_year_window_from_structured_and_desc(
    birth_year: Optional[int],
    death_year: Optional[int],
    desc_bounds: Optional[tuple[int, int]],
) -> tuple[Optional[int], Optional[int]]:
    """Priorytet: P569/P570 ze SPARQL; jeśli brak — przedział z opisu."""
    if birth_year is not None:
        lo, hi = birth_year, death_year if death_year is not None else birth_year + 90
        return lo, hi
    if death_year is not None:
        return death_year - 95, death_year
    if desc_bounds:
        return desc_bounds[0], desc_bounds[1]
    return None, None


def _anchor_year_cac(
    cac_birth_year: Optional[int],
    cac_study_year: Optional[int],
    cac_activity_fallback_year: Optional[int],
) -> Optional[int]:
    if cac_birth_year is not None:
        return cac_birth_year
    if cac_study_year is not None:
        return cac_study_year
    return cac_activity_fallback_year


def _year_ranges_disjoint(
    anchor: int,
    wd_lo: int,
    wd_hi: int,
    *,
    margin: int = 45,
) -> bool:
    """True = kandydat WD na pewno w innym wieku niż punkt CAC (brak sensownego pokrycia)."""
    c_lo, c_hi = anchor - margin, anchor + margin
    return c_hi < wd_lo or c_lo > wd_hi


MAX_BIRTH_YEAR_GAP = 95  # gdy mamy P569 i rok CAC — odrzuć oczywiste homonimy

# Korpus CAC: elektroniczna baza studentów i profesorów UJ staropolskiego (zakres lat zbioru).
# Kandydaci Wikidata z udokumentowanym początkiem życia/działalności **po** tej epoce (np. ur. 1989)
# nie mogą być tą samą osobą — odrzucamy niezależnie od punktacji tekstowej.
CAC_CORPUS_YEAR_MIN = 1344
CAC_CORPUS_YEAR_MAX = 1800


def wb_search_entities(search: str, language: str = "pl", limit: int = 12) -> List[dict]:
    r = SESSION.get(
        WD_API,
        params={
            "action": "wbsearchentities",
            "format": "json",
            "language": language,
            "search": search,
            "limit": limit,
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    out: List[dict] = []
    for it in data.get("search", []) or []:
        qid = it.get("id")
        if not qid:
            continue
        out.append(
            {
                "id": qid,
                "label": it.get("label") or "",
                "description": it.get("description") or "",
            }
        )
    return out


def sparql_enrich_birth_place(qids: List[str]) -> dict[str, dict[str, Any]]:
    if not qids:
        return {}
    chunks = [qids[i : i + 40] for i in range(0, len(qids), 40)]
    merged: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        values = " ".join(f"wd:{q}" for q in chunk)
        query = f"""
SELECT ?item ?bd ?dd ?p19l ?occl WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P569 ?bd }}
  OPTIONAL {{ ?item wdt:P570 ?dd }}
  OPTIONAL {{
    ?item wdt:P19 ?p19 .
    ?p19 rdfs:label ?p19l .
    FILTER((LANG(?p19l)) = "pl" || (LANG(?p19l)) = "en")
  }}
  OPTIONAL {{
    ?item wdt:P106 ?occ .
    ?occ rdfs:label ?occl .
    FILTER((LANG(?occl)) = "pl" || (LANG(?occl)) = "en")
  }}
}}
"""
        r = SESSION.get(
            WD_SPARQL,
            params={"format": "json", "query": query},
            timeout=90,
        )
        if r.status_code != 200:
            continue
        rows = r.json().get("results", {}).get("bindings") or []
        for row in rows:
            uri = row.get("item", {}).get("value", "")
            q = uri.rsplit("/", 1)[-1] if uri else ""
            if not q:
                continue
            if q not in merged:
                merged[q] = {
                    "birth_year": None,
                    "death_year": None,
                    "place_labels": set(),
                    "occ_labels": set(),
                }
            m = merged[q]
            m["birth_year"] = m["birth_year"] or _year_from_wd_literal(row.get("bd", {}).get("value"))
            m["death_year"] = m["death_year"] or _year_from_wd_literal(row.get("dd", {}).get("value"))
            pl = row.get("p19l", {}).get("value")
            if pl:
                m["place_labels"].add(pl)
            oc = row.get("occl", {}).get("value")
            if oc:
                m["occ_labels"].add(oc)
    out: dict[str, dict[str, Any]] = {}
    for q, v in merged.items():
        out[q] = {
            "birth_year": v["birth_year"],
            "death_year": v["death_year"],
            "birth_place_labels": " | ".join(sorted(v["place_labels"])) if v["place_labels"] else "",
            "occupation_labels": " | ".join(sorted(v["occ_labels"])) if v["occ_labels"] else "",
        }
    return out


def sparql_humans_among(qids: List[str]) -> Set[str]:
    if not qids:
        return set()
    values = " ".join(f"wd:{q}" for q in qids[:50])
    query = f"""
SELECT ?item WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P31 wd:Q5 .
}}
"""
    r = SESSION.get(WD_SPARQL, params={"format": "json", "query": query}, timeout=60)
    if r.status_code != 200:
        return set()
    humans: Set[str] = set()
    for row in r.json().get("results", {}).get("bindings") or []:
        uri = row.get("item", {}).get("value", "")
        q = uri.rsplit("/", 1)[-1]
        if q:
            humans.add(q)
    return humans


def _norm(s: str) -> str:
    t = s.lower().strip()
    return "".join(c for c in t if c.isalnum() or c.isspace())


def _place_overlap(cac_raw: Optional[str], cac_norm: Optional[str], wd_places: str) -> bool:
    cac_strings = set()
    for s in place_matching_strings(cac_raw):
        cac_strings.add(_norm(s))
    for s in place_matching_strings(cac_norm):
        cac_strings.add(_norm(s))
    cac_strings.discard("")
    if not cac_strings:
        return False
    wd_blob = _norm(wd_places)
    for cs in cac_strings:
        if len(cs) >= 3 and cs in wd_blob:
            return True
        for part in cs.split():
            if len(part) >= 3 and part in wd_blob:
                return True
    return False


def rank_candidates(
    search_hits: List[dict],
    enrich: dict[str, dict[str, Any]],
    humans: Set[str],
    *,
    cac_birth_year: Optional[int],
    cac_study_year: Optional[int],
    cac_birthplace_raw: Optional[str],
    cac_place_norm: Optional[str],
    cac_activity_fallback_year: Optional[int] = None,
    top_k: int = 3,
    matcher_id: str = "heuristic_rules",
    matcher_label: str = "Heurystyka (reguły + SPARQL)",
) -> List[WikidataCandidate]:
    effective_birth = cac_birth_year
    if effective_birth is None and cac_activity_fallback_year is not None:
        effective_birth = cac_activity_fallback_year

    ranked: List[WikidataCandidate] = []
    for i, hit in enumerate(search_hits):
        qid = hit.get("id") or ""
        if not qid:
            continue
        label = hit.get("label") or ""
        desc = hit.get("description") or ""
        ex = enrich.get(qid) or {}
        bwd = ex.get("birth_year")
        dwd = ex.get("death_year")
        p19 = ex.get("birth_place_labels") or ""
        occ = ex.get("occupation_labels") or ""
        is_h = qid in humans

        desc_bounds = _year_span_from_description(f"{desc} {label}")
        wd_lo, wd_hi = _wd_year_window_from_structured_and_desc(bwd, dwd, desc_bounds)
        # Twardy filtr korpusu: zero dopasowań do ludzi z XIX–XXI w. przy zbiorze 1364–1780.
        if wd_lo is not None and wd_lo > CAC_CORPUS_YEAR_MAX:
            continue
        if wd_hi is not None and wd_hi < CAC_CORPUS_YEAR_MIN:
            continue

        anchor = _anchor_year_cac(
            cac_birth_year, cac_study_year, cac_activity_fallback_year
        )
        if anchor is not None and wd_lo is not None and wd_hi is not None:
            if _year_ranges_disjoint(anchor, wd_lo, wd_hi, margin=45):
                continue
        if (
            anchor is not None
            and bwd is not None
            and abs(anchor - bwd) > MAX_BIRTH_YEAR_GAP
        ):
            continue

        score = 0.0
        reasons: List[str] = []

        pos_bonus = max(0.0, 14.0 - i * 1.2)
        score += pos_bonus
        reasons.append(f"Pozycja w wynikach wyszukiwania: {i + 1}")

        if is_h:
            score += 10
            reasons.append("P31: człowiek (Q5)")
        else:
            reasons.append("P31: nie stwierdzono Q5 (może być inna klasa)")

        if cac_study_year is not None and bwd is not None:
            age = cac_study_year - bwd
            if age < 10 or age > 90:
                continue
        if cac_study_year is not None and dwd is not None and cac_study_year > dwd:
            continue

        if effective_birth is not None and bwd is not None:
            diff = abs(effective_birth - bwd)
            if diff == 0:
                score += 35
                reasons.append(f"Zgodny rok urodzenia ({bwd})")
            elif diff <= 3:
                score += 28
                reasons.append(f"Bliski rok urodzenia (Δ {diff} lat)")
            elif diff <= 15:
                score += 15
                reasons.append(f"Rok urodzenia w pobliżu (Δ {diff} lat)")
            elif diff <= 40:
                score += 5
                reasons.append(f"Rok urodzenia odległy (Δ {diff} lat)")

        if (cac_birthplace_raw or cac_place_norm) and p19:
            if _place_overlap(cac_birthplace_raw, cac_place_norm, p19):
                score += 22
                reasons.append("Miejsce (P19) pokrywa się z CAC")

        ranked.append(
            WikidataCandidate(
                qid=qid,
                label=label,
                description=desc,
                uri=f"https://www.wikidata.org/wiki/{qid}",
                birth_year_wd=bwd,
                death_year_wd=dwd,
                birth_place_labels=p19,
                occupation_labels=occ,
                is_human=is_h,
                score=round(score, 1),
                score_reasons=reasons,
                matcher_id=matcher_id,
                matcher_label=matcher_label,
            )
        )

    ranked.sort(key=lambda c: (-c.score, c.qid))
    return ranked[:top_k]


def fetch_top_candidates(
    search_query: str,
    *,
    cac_birth_year: Optional[int],
    cac_study_year: Optional[int],
    cac_birthplace_raw: Optional[str],
    cac_place_norm: Optional[str],
    cac_activity_fallback_year: Optional[int] = None,
    top_k: int = 3,
    search_limit: int = 12,
    pause_sec: float = 0.35,
) -> List[WikidataCandidate]:
    hits = wb_search_entities(search_query, language="pl", limit=search_limit)
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
        matcher_id="heuristic_rules",
        matcher_label="Heurystyka — kolejność z wyszukiwarki Wikidata + reguły (lata, miejsce, Q5)",
    )
