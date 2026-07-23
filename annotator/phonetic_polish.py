"""
Dopasowanie fonetyczne nazwisk (wczesnonowożytna polszczyzna vs współczesne zapisy na Wikidata).

**Źródło metodologiczne (repo promotora):**
`ER-Wikidata-WF` — https://github.com/luizdovalle2/ER-Wikidata-WF ,
plik ``functions_for_metrics.py`` (m.in. ``sorensen_dice_coverage``, ``build_phonetic_matched_frozensets``).

**Czemu nie ma tu ``import functions_for_metrics``?**
Import całego modułu z tamtego repozytorium ciągnąłby do aplikacji Streamlit ciężkie zależności
(pandas, numpy, swifter, textdistance, multiprocessing w macierzach odległości), które są
potrzebne głównie do **batchowej** ewaluacji w notebookach, a nie do pojedynczego porównania
etykiet w UI. Dlatego zastosowano **tę samą bibliotekę fonetyczną co upstream** — ``abydos.phonetic.DaitchMokotoff`` —
oraz **ten sam wzór Dice–Sørensen** co funkcja ``sorensen_dice_coverage`` w ``functions_for_metrics.py``
(pętle i wzór ``2|M|/(|A|+|B|)`` są zgodne). Pary tokenów dopuszczalne do „miękkiego” dopasowania
są budowane równoważnie idei ``build_phonetic_matched_frozensets`` (wspólny kod DM → przecięcie
zbiorów kodów), przy małej liczbie tokenów (typowe nazwiska) prostszy algorytm O(n²) po słowach
jest wystarczający.

**Do pracy magisterskiej:** w rozdziale o metodach napisz wprost, że realizujesz **pipeline zaproponowany
w repozytorium promotora**, z odchudzoną implementacją pod kątem narzędzia adnotacyjnego; podaj link
do commita lub daty pobrania wersji pliku źródłowego. Jeśli promotor woli **dosłowny** import kodu,
możesz dodać repozytorium jako submodule do ``external/ER-Wikidata-WF`` i rozszerzyć ``requirements.txt``
o pandas/swifter itd. — wtedy ten plik można zastąpić cienkim wrapperem; obecna wersja jest świadomym
kompromisem między wiernością metodzie a prostotą środowiska.
"""
from __future__ import annotations

import re
from typing import List, Set, FrozenSet

from abydos.phonetic import DaitchMokotoff

_dm = DaitchMokotoff()


def tokenize_for_matching(text: str) -> List[str]:
    """Słowa z liter (PL + łacina); małe litery."""
    if not (text or "").strip():
        return []
    return [m.group(0).lower() for m in re.finditer(r"[A-Za-zÀ-ÿąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", text, re.UNICODE)]


def _codes(word: str) -> Set[str]:
    c = _dm.encode(word)
    return set(c) if isinstance(c, (set, frozenset)) else {str(c)}


def tokens_phonetically_pair(t1: str, t2: str) -> bool:
    if t1 == t2:
        return True
    a, b = _codes(t1), _codes(t2)
    return bool(a and b and (a & b))


def _phonetic_allowed_pairs(vocab: List[str]) -> Set[FrozenSet[str]]:
    """Pary tokenów z jednego słownika, które są identyczne lub fonetycznie zgodne (DM)."""
    out: Set[FrozenSet[str]] = set()
    for i, t1 in enumerate(vocab):
        for t2 in vocab[i + 1 :]:
            if tokens_phonetically_pair(t1, t2):
                out.add(frozenset((t1, t2)))
    return out


def sorensen_dice_coverage(
    label_tokens: List[str],
    alias_tokens: List[str],
    matched_frozensets: Set[FrozenSet[str]],
) -> float:
    """
    Dice–Sørensen na listach tokenów z dopasowaniem dokładnym lub z ``matched_frozensets``.
    Jak w ``functions_for_metrics.sorensen_dice_coverage`` (ER-Wikidata-WF).
    """
    remaining_label = list(label_tokens)
    remaining_alias = list(alias_tokens)
    matched_count = 0
    for lt in list(label_tokens):
        for at in list(remaining_alias):
            if at == lt or frozenset({lt, at}) in matched_frozensets:
                if lt in remaining_label:
                    remaining_label.remove(lt)
                if at in remaining_alias:
                    remaining_alias.remove(at)
                matched_count += 1
                break
    denom = len(label_tokens) + len(alias_tokens)
    if denom == 0:
        return 0.0
    return (2.0 * matched_count) / denom


def phonetic_dice_between_strings(cac_text: str, wikidata_blob: str) -> float:
    """
    Współczynnik 0..1: na ile tokeny z pierwszego napisu pokrywają się z drugim
    (dokładnie lub wg DM). W dopasowaniu Wikidata **najczęściej**: etykieta osoby z CAC
    vs **etykieta** encji na WD (różne historyczne zapisy nazwiska), nie cały długi profil.
    """
    a = tokenize_for_matching(cac_text)
    b = tokenize_for_matching(wikidata_blob)
    if not a and not b:
        return 0.0
    vocab = list(dict.fromkeys(a + b))
    pairs = _phonetic_allowed_pairs(vocab)
    return sorensen_dice_coverage(a, b, pairs)
