"""
Interfejs do ręcznej weryfikacji dopasowań CAC → Wikidata.
Uruchom z katalogu głównego projektu:
  streamlit run streamlit_app/app.py

Starsza ścieżka: streamlit run annotation_app.py (wrapper w korzeniu repozytorium).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Optional, Set

import streamlit as st
from rdflib import Graph, URIRef

from annotator.features import extract_person_features
from annotator.wikidata_candidates import wikipedia_pl_search_url
from matchers.registry import MATCHER_CHOICES, fetch_candidates
from project_paths import PROJECT_ROOT

PERSON_CLASS = URIRef("http://www.cidoc-crm.org/cidoc-crm/E21_Person")
RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

DEFAULT_RDF_PATH = PROJECT_ROOT / "data" / "output_cidoc_cac_1000.rdf"
DEFAULT_RDF = str(DEFAULT_RDF_PATH)
OUT_DIR = PROJECT_ROOT / "annotations"
OUT_CSV = OUT_DIR / "gold_labels.csv"
NAV_STATE_PATH = OUT_DIR / "nav_state.json"


def load_graph(path: str) -> Graph:
    g = Graph()
    g.parse(path, format="xml")
    return g


def list_person_uris(g: Graph) -> list:
    return sorted({str(s) for s in g.subjects(RDF_TYPE, PERSON_CLASS)}, key=str)


def person_uris_in_csv(csv_path: Path) -> Set[str]:
    if not csv_path.is_file():
        return set()
    out: Set[str] = set()
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                u = (row.get("person_uri") or "").strip()
                if u:
                    out.add(u)
    except OSError:
        pass
    return out


def persist_navigation_idx(idx: int, n_people: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"idx": idx, "n_people": n_people}
    NAV_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_saved_navigation_idx(n_people: int) -> Optional[int]:
    if not NAV_STATE_PATH.is_file():
        return None
    try:
        data = json.loads(NAV_STATE_PATH.read_text(encoding="utf-8"))
        if int(data.get("n_people", -1)) != n_people:
            return None
        idx = int(data.get("idx", 0))
        return max(0, min(idx, n_people - 1))
    except (OSError, ValueError, json.JSONDecodeError, TypeError, KeyError):
        return None


def first_unannotated_index(people: list, annotated: Set[str]) -> Optional[int]:
    for i, uri in enumerate(people):
        if uri not in annotated:
            return i
    return None


def next_unannotated_index(people: list, annotated: Set[str], after_idx: int) -> Optional[int]:
    for i in range(after_idx + 1, len(people)):
        if people[i] not in annotated:
            return i
    for i in range(0, after_idx + 1):
        if people[i] not in annotated:
            return i
    return None


def append_row(row: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = OUT_CSV.exists()
    fieldnames = [
        "timestamp",
        "person_uri",
        "label_clean",
        "birth_year_cac",
        "study_year_cac",
        "birthplace_cac",
        "search_query_used",
        "chosen_qid",
        "chosen_uri",
        "decision",
        "notes",
        "matcher_id",
        "matcher_label",
    ]
    with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    st.set_page_config(page_title="CAC → Wikidata — adnotacja", layout="wide")
    st.title("Dopasowanie rekordów CAC do Wikidata")
    st.caption(
        "Propozycje z Wikidata (API + SPARQL). Wybierz **metodę dopasowania** w panelu — możesz porównywać wyniki; zapis CSV zawiera identyfikator metody."
    )

    if "graph" not in st.session_state:
        st.session_state.graph = None
    if "people" not in st.session_state:
        st.session_state.people = []
    if "idx" not in st.session_state:
        st.session_state.idx = 0
    if "candidates" not in st.session_state:
        st.session_state.candidates = []
    if "last_features_uri" not in st.session_state:
        st.session_state.last_features_uri = None

    if st.session_state.graph is None and DEFAULT_RDF_PATH.is_file():
        try:
            g0 = load_graph(DEFAULT_RDF)
            st.session_state.graph = g0
            st.session_state.people = list_person_uris(g0)
            n0 = len(st.session_state.people)
            saved = load_saved_navigation_idx(n0) if n0 else None
            st.session_state.idx = saved if saved is not None else 0
            st.session_state.candidates = []
            st.session_state.last_features_uri = None
            st.session_state.load_msg = f"Wczytano automatycznie: {DEFAULT_RDF_PATH}"
        except Exception as e:
            st.session_state.load_msg = f"Nie udało się wczytać {DEFAULT_RDF_PATH.name}: {e}"

    matcher_labels = dict(MATCHER_CHOICES)

    with st.sidebar:
        st.subheader("Plik RDF (CAC / CIDOC)")
        st.caption(
            f"Domyślnie: **`data/output_cidoc_cac_1000.rdf`** (ścieżka względem folderu projektu)."
        )
        uploaded = st.file_uploader("Wgraj inny plik .rdf (opcjonalnie)", type=["rdf", "xml"])
        default_path = st.text_input("Albo inna ścieżka do pliku", value=DEFAULT_RDF)
        if st.button("Załaduj graf"):
            try:
                if uploaded is not None:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".rdf") as tmp:
                        tmp.write(uploaded.getvalue())
                        tmp_path = tmp.name
                    g = load_graph(tmp_path)
                    st.session_state.load_msg = "Wczytano plik z uploadu."
                else:
                    g = load_graph(default_path)
                    st.session_state.load_msg = f"Wczytano: {default_path}"
                st.session_state.graph = g
                st.session_state.people = list_person_uris(g)
                n0 = len(st.session_state.people)
                saved = load_saved_navigation_idx(n0) if n0 else None
                st.session_state.idx = saved if saved is not None else 0
                st.session_state.candidates = []
                st.session_state.last_features_uri = None
            except Exception as e:
                st.error(f"Nie udało się wczytać RDF: {e}")
        if st.session_state.get("load_msg"):
            st.success(st.session_state.load_msg)

        st.divider()
        st.subheader("Metoda dopasowania")
        method_id = st.selectbox(
            "Którą strategię porównać",
            options=[m[0] for m in MATCHER_CHOICES],
            format_func=lambda x: matcher_labels[x],
            key="matcher_select",
        )
        st.caption(
            "**Heurystyka** — oryginalna kolejność wyszukiwarki. **RapidFuzz** — kolejność wg podobieństwa profilu CAC do etykiety/opisu. "
            "**Fonetyka** — najpierw zgodność DM na **etykietach** CAC↔WD, potem RapidFuzz na profilu."
        )
        top_k = st.slider("Liczba kandydatów z Wikidata", 2, 6, 3)
        st.session_state.top_k = top_k
        st.session_state.matcher_id = method_id
        st.caption(f"Zapis adnotacji: `{OUT_CSV}`")

    g = st.session_state.graph
    if g is None:
        st.info(
            f"Brak grafu. Umieść plik RDF w **`data/output_cidoc_cac_1000.rdf`** albo wskaż ścieżkę w panelu i kliknij **Załaduj graf**."
        )
        return

    people = st.session_state.people
    if not people:
        st.warning("Brak osób typu E21_Person w grafie.")
        return

    n = len(people)
    idx = st.session_state.idx
    idx = max(0, min(idx, n - 1))
    st.session_state.idx = idx

    annotated = person_uris_in_csv(OUT_CSV)
    n_done = sum(1 for u in people if u in annotated)

    st.subheader(f"Osoba {idx + 1} z {n}")
    st.caption(f"Z wpisem w `{OUT_CSV.name}`: **{n_done}** / {n} — „Pomiń bez zapisu” nie tworzy wpisu, więc osoba dalej liczy się jako bez decyzji.")

    nav_a, nav_b, nav_c = st.columns([2, 2, 2])
    with nav_a:
        jump_to = st.number_input(
            "Skocz do numeru (1…N)",
            min_value=1,
            max_value=n,
            value=idx + 1,
            step=1,
            help="Nie musisz klikać „Następna” setki razy — wpisz np. 100 i przejdź.",
            key=f"jump_num_{idx}",
        )
        if st.button("Przejdź do tego numeru", type="primary"):
            st.session_state.idx = int(jump_to) - 1
            persist_navigation_idx(st.session_state.idx, n)
            st.session_state.candidates = []
            st.session_state.last_features_uri = None
            st.rerun()
    with nav_b:
        if st.button("Pierwsza osoba bez wpisu w CSV"):
            j = first_unannotated_index(people, annotated)
            if j is None:
                st.success("Wszystkie osoby mają już co najmniej jeden wpis w pliku.")
            else:
                st.session_state.idx = j
                persist_navigation_idx(j, n)
                st.session_state.candidates = []
                st.session_state.last_features_uri = None
                st.rerun()
    with nav_c:
        if st.button("Następna bez wpisu (szukaj od bieżącej w przód)"):
            j = next_unannotated_index(people, annotated, idx)
            if j is None:
                st.success("Każda osoba ma już wpis w CSV — nie ma kolejnej „pustej”.")
            else:
                st.session_state.idx = j
                persist_navigation_idx(j, n)
                st.session_state.candidates = []
                st.session_state.last_features_uri = None
                st.rerun()

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ Poprzednia") and idx > 0:
            st.session_state.idx = idx - 1
            persist_navigation_idx(st.session_state.idx, n)
            st.session_state.candidates = []
            st.session_state.last_features_uri = None
            st.rerun()
    with col_next:
        if st.button("Następna ▶") and idx < n - 1:
            st.session_state.idx = idx + 1
            persist_navigation_idx(st.session_state.idx, n)
            st.session_state.candidates = []
            st.session_state.last_features_uri = None
            st.rerun()

    person_uri = URIRef(people[idx])
    feats = extract_person_features(g, person_uri)
    if feats is None:
        st.error("Brak etykiety (rdfs:label) dla tej osoby — użyj **Następna**.")
        return

    search_query = st.text_input(
        "Fraza do wyszukiwarki Wikidata",
        value=feats.label_clean,
        key=f"sq_{idx}",
    )

    with st.expander("Dane z CAC (graf RDF)", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**URI:** `{feats.uri}`")
        c2.markdown(f"**Etykieta:** {feats.label_raw}")
        c3.markdown(f"**Do wyszukiwania:** {feats.label_clean}")
        d1, d2, d3 = st.columns(3)
        d1.write(f"Rok urodzenia: **{feats.birth_year or '—'}**")
        d2.write(f"Rok studiów (z dat wydarzeń): **{feats.study_year or '—'}**")
        if feats.birthplace_normalized and feats.birthplace_normalized != feats.birthplace:
            d3.write(f"Miejsce: **{feats.birthplace or '—'}** → **{feats.birthplace_normalized}**")
        else:
            d3.write(f"Miejsce: **{feats.birthplace or '—'}**")

        has_extra = bool(
            feats.appellations or feats.activity_types or feats.sample_event_labels or feats.publications
        )
        if has_extra:
            st.markdown("---")
        if feats.appellations:
            st.markdown("**Apelatywy / fragmenty nazw:** " + " · ".join(feats.appellations))
        if feats.activity_types:
            st.markdown(
                "**Stopnie, kierunki, funkcje (typy z wydarzeń naukowych i urzędowych):**  \n"
                + " · ".join(f"`{t}`" for t in feats.activity_types)
            )
        if feats.sample_event_labels:
            st.markdown("**Wydarzenia (etykiety z grafu):**")
            for ev in feats.sample_event_labels:
                st.markdown(f"- {ev}")
        if feats.publications:
            st.markdown("**Publikacje / dzieła (jeśli są powiązane w RDF):**")
            for pub in feats.publications:
                st.markdown(f"- {pub}")

    mid = st.session_state.get("matcher_id", "heuristic_rules")

    if st.button("Pobierz propozycje z Wikidata", type="primary"):
        with st.spinner("Łączenie z Wikidata (API + SPARQL)…"):
            try:
                st.session_state.candidates = fetch_candidates(
                    mid,
                    search_query.strip() or feats.label_clean,
                    feats,
                    top_k=st.session_state.get("top_k", 3),
                )
            except Exception as e:
                st.error(f"Błąd: {e}")
                st.session_state.candidates = []

    candidates = st.session_state.candidates
    if not candidates:
        st.warning('Wybierz metodę w panelu bocznym i kliknij **Pobierz propozycje z Wikidata**.')
    else:
        st.success(f"Kandydaci — metoda: **{candidates[0].matcher_label}** (skoring jak wcześniej + kolejność wg metody).")
        notes = st.text_input("Notatka (opcjonalnie)", key=f"notes_{idx}")

        for i, c in enumerate(candidates):
            with st.container():
                st.markdown(f"### {i + 1}. {c.label} (`{c.qid}`)")
                st.caption(c.description or "—")
                r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 2, 2])
                r1.metric("Punktacja", f"{c.score}")
                r2.write("**Wikidata:** " + f"[Otwórz encję]({c.uri})")
                r3.write("**pl.wikipedia:** " + f"[Szukaj]({wikipedia_pl_search_url(c.label)})")
                r4.write(f"ur.: **{c.birth_year_wd or '—'}**")
                r5.write(f"zm.: **{c.death_year_wd or '—'}**")
                st.caption(" · ".join(c.score_reasons))
                if c.birth_place_labels:
                    st.caption(f"Miejsce ur. (Wikidata): {c.birth_place_labels}")
                if c.occupation_labels:
                    st.caption(f"Zawód / zajęcia (Wikidata): {c.occupation_labels}")

                if st.button(f"To jest poprawne dopasowanie — {c.qid}", key=f"pick_{idx}_{c.qid}"):
                    append_row(
                        {
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "person_uri": feats.uri,
                            "label_clean": feats.label_clean,
                            "birth_year_cac": feats.birth_year or "",
                            "study_year_cac": feats.study_year or "",
                            "birthplace_cac": feats.birthplace or "",
                            "search_query_used": search_query,
                            "chosen_qid": c.qid,
                            "chosen_uri": c.uri,
                            "decision": "chosen",
                            "notes": notes,
                            "matcher_id": c.matcher_id,
                            "matcher_label": c.matcher_label,
                        }
                    )
                    st.success(f"Zapisano: {c.qid}. Możesz przejść do następnej osoby.")
                st.divider()

        if st.button("Żaden z kandydatów nie pasuje (zapisz jako „brak dopasowania”)"):
            m0 = candidates[0]
            append_row(
                {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "person_uri": feats.uri,
                    "label_clean": feats.label_clean,
                    "birth_year_cac": feats.birth_year or "",
                    "study_year_cac": feats.study_year or "",
                    "birthplace_cac": feats.birthplace or "",
                    "search_query_used": search_query,
                    "chosen_qid": "",
                    "chosen_uri": "",
                    "decision": "none_match",
                    "notes": notes,
                    "matcher_id": m0.matcher_id,
                    "matcher_label": m0.matcher_label,
                }
            )
            st.info("Zapisano decyzję: brak dopasowania wśród propozycji.")

        if st.button("Pomiń — nie zapisuj (na później)"):
            st.session_state.idx = min(idx + 1, n - 1)
            persist_navigation_idx(st.session_state.idx, n)
            st.session_state.candidates = []
            st.rerun()

    st.divider()
    if OUT_CSV.exists():
        st.subheader("Podgląd zapisu")
        try:
            import pandas as pd

            df = pd.read_csv(OUT_CSV)
            st.dataframe(df.tail(20), use_container_width=True)
        except Exception:
            st.caption("Nie można wczytać podglądu CSV.")


if __name__ == "__main__":
    main()
