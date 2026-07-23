# Metody dopasowania CAC → Wikidata

Dokument opisuje **trzy strategie** w panelu Streamlit (`matchers/registry.py`). Wszystkie korzystają z **tego samego zbioru Q-id** z wyszukiwarki Wikidata (`wbsearchentities`), ale **różnią się kolejnością** listy przed wspólnym scoringiem w `annotator/wikidata_candidates.py` (`rank_candidates`).

---

## Wspólny schemat

1. Fraza wyszukiwania (domyślnie oczyszczona etykieta z CAC).
2. API Wikidata — język `pl`, limit wyników (`search_limit`, domyślnie 12).
3. SPARQL: P569/P570, P19, P106, weryfikacja **P31 = Q5**.
4. `rank_candidates` — punkty i powody (m.in. rok, miejsce, pozycja na *aktualnej* liście).
5. Zwracane **top‑k** kandydatów.

**Różnica między metodami:** krok między (2) a (4) — albo kolejność z API, albo sortowanie po podobieństwie tekstu / fonetyki.

---

## Profil CAC (`matchers/cac_profile.py`)

Jeden string z: etykiety, miejsca (surowe + znormalizowane), lat, typów aktywności, apelatywów, tytułów. Używany przez **RapidFuzz** i **fonetykę** (część RapidFuzz po etapie DM).

---

## 1. `heuristic_rules` — heurystyka

**Plik:** `annotator/wikidata_candidates.py` — `fetch_top_candidates`.

Kolejność wyników **taka jak zwróciła wyszukiwarka**. Bez dodatkowych bibliotek poza `requests` / `rdflib`.

---

## 2. `fuzzy_rerank` — RapidFuzz

**Plik:** `matchers/fuzzy_wikidata.py`.

Ta sama lista z API; sortowanie malejąco po `token_set_ratio` profilu CAC vs „etykieta + opis” kandydata.

**Zależność:** `rapidfuzz`.

---

## 3. `phonetic_rerank` — fonetyka + RapidFuzz

**Plik:** `matchers/phonetic_wikidata.py`, `annotator/phonetic_polish.py`.

Najpierw dopasowanie **Daitch–Mokotoff** (abydos) na etykietach CAC↔WD, potem RapidFuzz profil↔opis jak w metodzie 2.

**Zależność:** `abydos`, `rapidfuzz`.

---

## Ograniczenia

- Żadna metoda **nie poszerza** zbioru Q ponad wynik jednego zapytania `wbsearchentities` — zmienia tylko **kolejność** (oraz filtry lat w scoringu).
- Jakość zależy od frazy i limitu `search_limit`.
- W kodzie są krótkie pauzy między zapytaniami do API/SPARQL.

---

*Zgodnie z implementacją w `annotator/wikidata_candidates.py` i `matchers/`.*
