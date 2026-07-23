#!/usr/bin/env python3
"""
Automatyczne dopasowanie osób z RDF (CAC) do Wikidata (wszystkie metody z MATCHER_CHOICES).

Dla każdej osoby i każdej wybranej metody pobiera kandydatów (jak w aplikacji),
bierze najlepszego (najwyższy score). Domyślnie do CSV trafiają **tylko wiersze z realnym
QID** (było co zweryfikować na Wikidata) + kolumna ``wikidata_url``. Brak kandydata = brak
wiersza (czytelny plik). Opcja ``--include-misses`` przywraca pełny log w CSV.

Równoległość (--workers N > 1): kilka osób naraz (sieć/API). Wiersze dopisywane na bieżąco
(przyrostowo); kolejność w pliku = kolejność ukończenia zadań (do statystyk metoda_id nie ma znaczenia).

Uruchomienie z katalogu głównego projektu:
  python scripts/batch_auto_match.py --rdf data/output_cidoc_cac_1000.rdf --limit 200 --workers 6
  python scripts/batch_auto_match.py --limit 200 --search-limit 30 --workers 4

Przerwanie po czasie (np. godzina), sensowny zapis do osobnego CSV:
  python scripts/batch_auto_match.py --workers 1 --max-seconds 3600 \\
    --out annotations/auto_match_run_YYYYMMDD_HHMM.csv

Wymaga sieci (Wikidata API + SPARQL).
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rdflib import Graph, URIRef

from annotator.features import PersonFeatures, extract_person_features
from matchers.registry import MATCHER_CHOICES, fetch_candidates

PERSON_CLASS = URIRef("http://www.cidoc-crm.org/cidoc-crm/E21_Person")
RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

METHOD_IDS = [m[0] for m in MATCHER_CHOICES]

# Wikidata wbsearchentities: typowo max ~50 na zapytanie (bezpieczny sufit).
MAX_SEARCH_LIMIT = 50

WD_ITEM_URL = "https://www.wikidata.org/wiki/{qid}"


def list_person_uris(g: Graph) -> list:
    return sorted({str(s) for s in g.subjects(RDF_TYPE, PERSON_CLASS)}, key=str)


def parse_methods_arg(s: str) -> list[str]:
    if s.strip().lower() in ("all", "*"):
        return METHOD_IDS
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for p in parts:
        if p not in METHOD_IDS:
            raise ValueError(f"Nieznana metoda: {p}. Dozwolone: {', '.join(METHOD_IDS)}")
    return parts


def _rows_for_person(
    order_idx: int,
    feats: PersonFeatures,
    methods: list[str],
    threshold: float,
    top_k: int,
    search_limit: int,
) -> Tuple[int, List[dict[str, Any]]]:
    """Zwraca (indeks kolejności, wiersze CSV dla jednej osoby × metody)."""
    q = feats.label_clean
    rows_out: List[dict[str, Any]] = []
    for mid in methods:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "person_uri": feats.uri,
            "label_clean": feats.label_clean,
            "search_query": q,
            "method_id": mid,
            "threshold": threshold,
            "accepted": False,
            "chosen_qid": "",
            "chosen_label": "",
            "chosen_description": "",
            "score": "",
            "score_reasons": "",
            "error": "",
        }
        try:
            cands = fetch_candidates(
                mid,
                q,
                feats,
                top_k=top_k,
                search_limit=search_limit,
            )
            if not cands:
                row["score_reasons"] = "brak_kandydatow_po_filtrowaniu"
            else:
                c = cands[0]
                row["chosen_qid"] = c.qid
                row["chosen_label"] = c.label
                row["chosen_description"] = (c.description or "").replace("\n", " ")[:500]
                row["score"] = c.score
                row["score_reasons"] = " | ".join(c.score_reasons)
                row["accepted"] = bool(c.score >= threshold)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        rows_out.append(row)
    return order_idx, rows_out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Automatyczne dopasowanie CAC → Wikidata (równoległe przetwarzanie osób, opcjonalnie)."
    )
    ap.add_argument(
        "--rdf",
        type=Path,
        default=ROOT / "data" / "output_cidoc_cac_1000.rdf",
        help="Ścieżka do pliku RDF",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "annotations" / "auto_match_results.csv",
        help="Plik CSV z wynikami",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="Minimalny score najlepszego kandydata, żeby uznać auto-dopasowanie (domyślnie 50)",
    )
    ap.add_argument(
        "--methods",
        type=str,
        default="all",
        help=f"Metody: all albo lista po przecinku: {','.join(METHOD_IDS)}",
    )
    ap.add_argument("--limit", type=int, default=None, help="Przetwórz tylko pierwsze N osób (test)")
    ap.add_argument("--top-k", type=int, default=1, help="Ilu kandydatów brać z każdej metody (decyzja po 1.)")
    ap.add_argument(
        "--search-limit",
        type=int,
        default=12,
        help=f"Ile trafień z API wyszukiwania na osobę (wbsearchentities / list=search), max {MAX_SEARCH_LIMIT}",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Liczba równoległych wątków (osób naraz). 1 = sekwencyjnie jak dawniej.",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.4,
        help="Pauza w sekundach po każdej osobie (tylko gdy --workers 1; oszczędzanie API)",
    )
    ap.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Zatrzymaj po tylu sekundach (zapis dotychczasowych wierszy). Przydatne gdy nie ma GNU timeout.",
    )
    ap.add_argument(
        "--include-misses",
        action="store_true",
        help="Zapisuj też wiersze bez QID (brak kandydata / błąd) — pełny CSV do diagnostyki.",
    )
    ap.add_argument(
        "--progress",
        action="store_true",
        help="Wypisuj postęp po każdej osobie (głośno); domyślnie tylko start i podsumowanie.",
    )
    args = ap.parse_args()

    if args.search_limit < 1 or args.search_limit > MAX_SEARCH_LIMIT:
        print(f"--search-limit musi być 1..{MAX_SEARCH_LIMIT}", file=sys.stderr)
        sys.exit(1)
    if args.workers < 1:
        print("--workers musi być >= 1", file=sys.stderr)
        sys.exit(1)
    if args.max_seconds is not None and args.workers != 1:
        print(
            "Uwaga: --max-seconds przerywa tylko kolejkę przy --workers 1. "
            "Przy workers>1 wszystkie zadania i tak się dokończą po starcie.",
            file=sys.stderr,
        )

    methods = parse_methods_arg(args.methods)

    if not args.rdf.is_file():
        print(f"Brak pliku RDF: {args.rdf}", file=sys.stderr)
        sys.exit(1)

    g = Graph()
    g.parse(str(args.rdf), format="xml")
    people = list_person_uris(g)
    if args.limit is not None:
        people = people[: args.limit]

    # Cechy w głównym wątku (bezpieczny odczyt grafu rdflib).
    indexed: List[Tuple[int, PersonFeatures]] = []
    skipped = 0
    for i, person_uri in enumerate(people):
        feats = extract_person_features(g, URIRef(person_uri))
        if feats is None:
            skipped += 1
            continue
        indexed.append((i, feats))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.include_misses:
        fieldnames = [
            "timestamp",
            "person_uri",
            "label_clean",
            "search_query",
            "method_id",
            "threshold",
            "accepted",
            "chosen_qid",
            "wikidata_url",
            "chosen_label",
            "chosen_description",
            "score",
            "score_reasons",
            "error",
        ]
    else:
        fieldnames = [
            "label_clean",
            "wikidata_url",
            "chosen_qid",
            "chosen_label",
            "method_id",
            "score",
            "accepted",
            "person_uri",
            "timestamp",
        ]

    new_file = not args.out.exists()
    total = len(indexed)
    print(
        f"Osoby z cechami: {total} (pominięto bez etykiety: {skipped}), "
        f"próg: {args.threshold}, metody: {methods}, search_limit: {args.search_limit}, "
        f"workers: {args.workers}",
        flush=True,
    )

    row_count = 0
    accepted_count = 0
    write_lock = threading.Lock()
    t0 = time.monotonic()

    def time_exceeded() -> bool:
        if args.max_seconds is None:
            return False
        return (time.monotonic() - t0) >= float(args.max_seconds)

    with args.out.open("a", newline="", encoding="utf-8") as out_f:
        w = csv.DictWriter(out_f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
            out_f.flush()

        def write_rows(rows: List[dict[str, Any]]) -> None:
            nonlocal row_count, accepted_count
            with write_lock:
                for row in rows:
                    qid = (row.get("chosen_qid") or "").strip()
                    if not args.include_misses:
                        if not qid:
                            continue
                        out_row = {
                            "label_clean": row.get("label_clean", ""),
                            "wikidata_url": WD_ITEM_URL.format(qid=qid),
                            "chosen_qid": qid,
                            "chosen_label": row.get("chosen_label", ""),
                            "method_id": row.get("method_id", ""),
                            "score": row.get("score", ""),
                            "accepted": row.get("accepted", False),
                            "person_uri": row.get("person_uri", ""),
                            "timestamp": row.get("timestamp", ""),
                        }
                        w.writerow(out_row)
                        row_count += 1
                        if out_row.get("accepted"):
                            accepted_count += 1
                    else:
                        row = dict(row)
                        row["wikidata_url"] = (
                            WD_ITEM_URL.format(qid=qid) if qid else ""
                        )
                        w.writerow({k: row.get(k, "") for k in fieldnames})
                        row_count += 1
                        if row.get("accepted"):
                            accepted_count += 1
                out_f.flush()

        if args.workers == 1:
            for j, (_order_idx, feats) in enumerate(indexed, 1):
                if time_exceeded():
                    print(f"  Przerwano po --max-seconds ({args.max_seconds}s).", flush=True)
                    break
                _, rows = _rows_for_person(
                    _order_idx,
                    feats,
                    methods,
                    args.threshold,
                    args.top_k,
                    args.search_limit,
                )
                write_rows(rows)
                if args.progress:
                    print(f"  [{j}/{total}] {feats.label_clean[:50]}…", flush=True)
                if args.sleep > 0:
                    time.sleep(args.sleep)
        else:
            # Uwaga: --max-seconds nie przerywa „w locie” pracy wątków — przy limicie czasu
            # użyj --workers 1, żeby po godzinie skrypt po prostu przestał brać kolejne osoby.
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {}
                for order_idx, feats in indexed:
                    fut = ex.submit(
                        _rows_for_person,
                        order_idx,
                        feats,
                        methods,
                        args.threshold,
                        args.top_k,
                        args.search_limit,
                    )
                    futs[fut] = (order_idx, feats.label_clean)
                done = 0
                for fut in as_completed(futs):
                    order_idx, label = futs[fut]
                    try:
                        _oi, rows = fut.result()
                        write_rows(rows)
                    except Exception as e:
                        if args.progress:
                            print(f"Błąd wątku ({label[:40]}…): {e}", flush=True)
                    done += 1
                    if args.progress and (
                        done % max(1, len(futs) // 10) == 0 or done == len(futs)
                    ):
                        print(f"  Ukończono {done}/{len(futs)} zleceń…", flush=True)

    elapsed = time.monotonic() - t0
    mode = "pełny CSV (--include-misses)" if args.include_misses else "tylko trafienia z QID"
    print(
        f"Koniec ({mode}): {args.out} — zapisanych wierszy: {row_count}, "
        f"accepted=True: {accepted_count}, czas: {elapsed:.0f}s.",
        flush=True,
    )


if __name__ == "__main__":
    main()
