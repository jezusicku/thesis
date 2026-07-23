"""Normalizacja i ekstrakcja miejsc urodzenia z grafu CIDOC."""

import re
import unicodedata
from typing import List, Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDFS

CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
EX = Namespace("http://example.org/ontology#")

P98_BORN = [CRM["P98i_was_born"], EX["P98i_was_born"]]
P7_PLACE = [CRM["P7_took_place_at"], EX["P7_took_place_at"]]
PLACES_TO_WIKIDATA: dict[str, str] = {
    # --- miasta i skróty (ASCII + polskie) ---
    "krakow": "Kraków",
    "kraków": "Kraków",
    "warszawa": "Warszawa",
    "wilno": "Wilno",
    "lwów": "Lwów",
    "lwow": "Lwów",
    "poznan": "Poznań",
    "poznań": "Poznań",
    "gniezno": "Gniezno",
    "wroclaw": "Wrocław",
    "wrocław": "Wrocław",
    "diecezja krakowska": "Kraków",
    "diecezja wroclawska": "Wrocław",
    "diecezja wrocławska": "Wrocław",
    "archidiecezja wrocławska": "Wrocław",
    # --- diecezje i archidiecezje (korpus CAC) ---
    "diecezja płocka": "Płock",
    "diecezja łucka": "Łuck",
    "diecezja przemyska": "Przemyśl",
    "archidiecezja przemyska": "Przemyśl",
    "diecezja wileńska": "Wilno",
    "archidiecezja wileńska": "Wilno",
    "diecezja chełmińska": "Chełmno",
    "archidiecezja chełmińska": "Chełmno",
    "diecezja chełmska": "Chełm",
    "archidiecezja chełmska": "Chełm",
    "diecezja kujawsko-pomorska": "Włocławek",  # dawniej m.in. struktura administracyjna
    "diecezja kujawska": "Włocławek",
    "archidiecezja lwowska": "Lwów",
    "diecezja lwowska": "Lwów",
    "diecezja lubelska": "Lublin",
    "archidiecezja lubelska": "Lublin",
    "diecezja łomżyńska": "Łomża",
    "diecezja sandomierska": "Sandomierz",
    "diecezja siedlecka": "Siedlce",
    "diecezja tarnowska": "Tarnów",
    "diecezja toruńska": "Toruń",
    "diecezja warszawska": "Warszawa",
    "archidiecezja warszawska": "Warszawa",
    "diecezja warszawsko-praska": "Warszawa",
    "diecezja zamojsko-lubaczowska": "Zamość",
    "diecezja zielonogórsko-gorzowska": "Zielona Góra",
    "diecezja elbląska": "Elbląg",
    "diecezja ełcka": "Ełk",
    "diecezja gliwicka": "Gliwice",
    "diecezja kaliska": "Kalisz",
    "diecezja katowicka": "Katowice",
    "archidiecezja katowicka": "Katowice",
    "diecezja kielecka": "Kielce",
    "diecezja koszalińsko-kołobrzeska": "Koszalin",
    "diecezja legnicka": "Legnica",
    "diecezja łódzka": "Łódź",
    "archidiecezja łódzka": "Łódź",
    "diecezja opolska": "Opole",
    "diecezja pelplińska": "Pelplin",
    "diecezja radomska": "Radom",
    "diecezja rzeszowska": "Rzeszów",
    "diecezja sosnowiecka": "Sosnowiec",
    "diecezja świdnicka": "Świdnica",
    "archidiecezja szczecińsko-kamieńska": "Szczecin",
    "diecezja bydgoska": "Bydgoszcz",
    "diecezja bielsko-żywiecka": "Bielsko-Biała",
    "diecezja drohiczyńska": "Drohiczyn",
    "diecezja łowicka": "Łowicz",
    # --- archidiecezje / stolice metropolitalne (często w CAC bez „diecezja …”) ---
    "archidiecezja krakowska": "Kraków",
    "archidiecezja krakówska": "Kraków",
    "archidiecezja gnieźnieńska": "Gniezno",
    "diecezja gnieźnieńska": "Gniezno",
    "archidiecezja gnieznienska": "Gniezno",
    "diecezja gnieznienska": "Gniezno",
    "diecezja warmińska": "Olsztyn",
    "archidiecezja warmińska": "Olsztyn",
    "diecezja mazowiecka": "Warszawa",
    "diecezja mazowiecka warszawska": "Warszawa",
    # --- województwa historyczne (I RP / Wielkie Księstwo — skróty do miast-siedzib / stolicy regionu) ---
    "województwo krakowskie": "Kraków",
    "województwo rawskie": "Rawa Mazowiecka",
    "województwo sandomierskie": "Sandomierz",
    "województwo lubelskie": "Lublin",
    "województwo łęczyckie": "Łęczyca",
    "województwo poznańskie": "Poznań",
    "województwo brzeskolitewskie": "Brześć Litewski",
    "województwo bełskie": "Bielsk Podlaski",
    "województwo belskie": "Bielsk Podlaski",
    "województwo bracławskie": "Bracław",
    "województwo czernihowskie": "Czernihów",
    "województwo kijowskie": "Kijów",
    "województwo mazowieckie": "Warszawa",
    "województwo podlaskie": "Drohiczyn",
    "województwo ruskie": "Lwów",
    "województwo wołyńskie": "Łuck",
    "województwo wolynskie": "Łuck",
    "województwo sieradzkie": "Sieradz",
    "województwo wieluńskie": "Wieluń",
    "województwo trockie": "Troki",
    "województwo witebskie": "Witebsk",
    "województwo mińskie": "Mińsk",
    "województwo smoleńskie": "Smoleńsk",
    "województwo połockie": "Połock",
    "województwo polockie": "Połock",
    "województwo inflanckie": "Ryga",
    "województwo pomorskie": "Gdańsk",
    "województwo malborskie": "Malbork",
    "województwo chełmińskie": "Chełmno",
    "województwo warmińskie": "Lidzbark Warmiński",
    "województwo wilenskie": "Wilno",
    "województwo wileńskie": "Wilno",
    "województwo nowogrodzkie": "Nowogródek",
    "województwo trockie litewskie": "Troki",
}


def _clean_key(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def normalize_place_name(name: str) -> str:
    if not (name or "").strip():
        return name
    raw = str(name).strip()
    k = _clean_key(raw)
    for key, canon in PLACES_TO_WIKIDATA.items():
        if k == _clean_key(key) or key in k or k in key:
            return canon
    return PLACES_TO_WIKIDATA.get(k, raw)


def _variants_from_text(name: str) -> List[str]:
    raw = str(name).strip()
    if not raw:
        return []
    parts = re.split(r"[,;/]", raw)
    out: List[str] = []
    for p in parts:
        t = p.strip()
        if t:
            out.append(t)
    if not out:
        out = [raw]
    seen: set[str] = set()
    uniq: List[str] = []
    for x in out:
        n = normalize_place_name(x)
        key = _clean_key(n)
        if key and key not in seen:
            seen.add(key)
            uniq.append(n)
    return uniq


def place_matching_strings(name: Optional[str]) -> List[str]:
    """Wszystkie sensowne warianty tekstu CAC do porównania z etykietami P19 na Wikidata."""
    if not name:
        return []
    return _variants_from_text(name)


def extract_birthplace(person_uri: URIRef, graph: Graph) -> Optional[str]:
    for p98 in P98_BORN:
        for birth_ev in graph.objects(person_uri, p98):
            for p7 in P7_PLACE:
                for place in graph.objects(birth_ev, p7):
                    lab = graph.value(place, RDFS.label)
                    if lab:
                        return str(lab).strip()
    return None
