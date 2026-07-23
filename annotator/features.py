"""Wyciąga cechy osoby z grafu CIDOC (namespace CRM i EX)."""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDFS

from extract_data import matching_birth_places, matching_conditions
from extract_data.matching_year_of_study import extract_birth_year, extract_study_year

CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
EX = Namespace("http://example.org/ontology#")

P4_HAS_TIME_SPAN = [CRM["P4_has_time-span"], EX["P4_has_time-span"]]
P82A_BEGIN = [CRM["P82a_begin_of_the_begin"], EX["P82a_begin_of_the_begin"]]
P98_BORN = [CRM["P98i_was_born"], EX["P98i_was_born"]]

P1_IDENTIFIED = [CRM["P1_is_identified_by"], EX["P1_is_identified_by"]]
P11_PARTICIPATED = [CRM["P11i_participated_in"], EX["P11i_participated_in"]]
P14_CARRIED_OUT = [CRM["P14_carried_out_by"], EX["P14_carried_out_by"]]
P94_CREATED = [CRM["P94_has_created"], EX["P94_has_created"]]
P2_HAS_TYPE = [CRM["P2_has_type"], EX["P2_has_type"]]

MAX_APPELLATIONS = 16
MAX_ACTIVITY_TYPES = 45
MAX_EVENT_LABELS = 22
MAX_PUBLICATIONS = 28


def _year_from_birth_events(person_uri: URIRef, graph: Graph) -> Optional[int]:
    for p98 in P98_BORN:
        for birth_event in graph.objects(person_uri, p98):
            for p4 in P4_HAS_TIME_SPAN:
                for timespan_uri in graph.objects(birth_event, p4):
                    for p82 in P82A_BEGIN:
                        begin = graph.value(timespan_uri, p82)
                        if begin:
                            m = re.search(r"(1[3-9][0-9]{2}|\d{4})", str(begin))
                            if m:
                                y = int(m.group(1))
                                if 1000 <= y <= 2100:
                                    return y
    return extract_birth_year(person_uri, graph, verbose=False)


def _resource_label(graph: Graph, uri: URIRef) -> str:
    lab = graph.value(uri, RDFS.label)
    if lab:
        return str(lab).strip()
    s = str(uri)
    frag = s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]
    return frag.replace("_", " ").replace("-", " ").strip()


def _gather_appellations(graph: Graph, person_uri: URIRef) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for p1 in P1_IDENTIFIED:
        for app in graph.objects(person_uri, p1):
            for lab in graph.objects(app, RDFS.label):
                t = str(lab).strip()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
                    if len(out) >= MAX_APPELLATIONS:
                        return out
    return out


def _gather_activity_types_and_events(graph: Graph, person_uri: URIRef) -> tuple[List[str], List[str]]:
    types_set: set = set()
    event_labels: List[str] = []
    seen_events: set = set()
    for p11 in P11_PARTICIPATED:
        for ev in graph.objects(person_uri, p11):
            el = graph.value(ev, RDFS.label)
            if el:
                sl = str(el).strip()
                if sl and sl not in seen_events and len(event_labels) < MAX_EVENT_LABELS * 2:
                    seen_events.add(sl)
                    event_labels.append(sl)
            for p2 in P2_HAS_TYPE:
                for typ in graph.objects(ev, p2):
                    types_set.add(_resource_label(graph, typ))
    types_sorted = sorted(types_set)[:MAX_ACTIVITY_TYPES]
    # Krótsze etykiety wydarzeń często bardziej zwięzłe — pokaż pierwsze unikalne do limitu
    compact: List[str] = []
    seen2: set = set()
    for lab in sorted(event_labels, key=len):
        if lab not in seen2 and len(compact) < MAX_EVENT_LABELS:
            seen2.add(lab)
            compact.append(lab)
    return types_sorted, compact


def _gather_publications(graph: Graph, person_uri: URIRef) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for p14 in P14_CARRIED_OUT:
        for creation in graph.subjects(p14, person_uri):
            for lab in graph.objects(creation, RDFS.label):
                t = str(lab).strip()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
                    if len(out) >= MAX_PUBLICATIONS:
                        return out
            for p94 in P94_CREATED:
                for work in graph.objects(creation, p94):
                    for lab in graph.objects(work, RDFS.label):
                        t = str(lab).strip()
                        if t and t not in seen:
                            seen.add(t)
                            out.append(t)
                            if len(out) >= MAX_PUBLICATIONS:
                                return out
    return out


@dataclass
class PersonFeatures:
    uri: str
    label_raw: str
    label_clean: str
    birth_year: Optional[int]
    study_year: Optional[int]
    birthplace: Optional[str]
    birthplace_normalized: Optional[str]
    appellations: List[str] = field(default_factory=list)
    activity_types: List[str] = field(default_factory=list)
    sample_event_labels: List[str] = field(default_factory=list)
    publications: List[str] = field(default_factory=list)
    life_anchor_year: Optional[int] = None  # np. rok z działalności gdy brak ur.


def _guess_life_anchor_from_texts(parts: List[str]) -> Optional[int]:
    """Szacunkowy rok z etykiet wydarzeń / apelatyw (gdy brak dat urodzenia w grafie)."""
    years: List[int] = []
    for s in parts:
        for m in re.finditer(r"\b(1[3-8][0-9]{2})\b", s):
            y = int(m.group(1))
            if 1300 <= y <= 1800:
                years.append(y)
    return min(years) if years else None


def extract_person_features(graph: Graph, person_uri: URIRef) -> Optional[PersonFeatures]:
    labels = list(graph.objects(person_uri, RDFS.label))
    if not labels:
        return None
    raw = str(labels[0])
    clean = matching_conditions.clean_label(raw)
    birth_y = _year_from_birth_events(person_uri, graph)
    study_y = extract_study_year(person_uri, graph, verbose=False)
    bp = matching_birth_places.extract_birthplace(person_uri, graph)
    bp_norm = matching_birth_places.normalize_place_name(bp) if bp else None
    appellations = _gather_appellations(graph, person_uri)
    activity_types, sample_events = _gather_activity_types_and_events(graph, person_uri)
    publications = _gather_publications(graph, person_uri)
    life_anchor = _guess_life_anchor_from_texts(sample_events + appellations)
    return PersonFeatures(
        uri=str(person_uri),
        label_raw=raw,
        label_clean=clean.strip() or raw,
        birth_year=birth_y,
        study_year=study_y,
        birthplace=bp,
        birthplace_normalized=bp_norm,
        appellations=appellations,
        activity_types=activity_types,
        sample_event_labels=sample_events,
        publications=publications,
        life_anchor_year=life_anchor,
    )
