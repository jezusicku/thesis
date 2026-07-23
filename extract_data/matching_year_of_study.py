import re
from typing import List, Optional

from rdflib import Namespace

CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
EX = Namespace("http://example.org/ontology#")

# Eksport CAC używa domyślnego namespace CIDOC w RDF/XML; trzeba obsłużyć CRM i ewentualnie EX.
P4_HAS_TIME_SPAN = [CRM["P4_has_time-span"], EX["P4_has_time-span"]]
P82A_BEGIN = [CRM["P82a_begin_of_the_begin"], EX["P82a_begin_of_the_begin"]]
P11_PARTICIPATED = [CRM["P11i_participated_in"], EX["P11i_participated_in"]]
P98_BORN = [CRM["P98i_was_born"], EX["P98i_was_born"]]
P100_DIED = [CRM["P100i_died_in"], EX["P100i_died_in"]]


def _year_from_begin_literal(val) -> Optional[int]:
    """Wyciąga rok z literału daty (np. 1715-01-01) lub samego roku."""
    if not val:
        return None
    s = str(val)
    for m in re.finditer(r"\b([12][0-9]{3})\b", s):
        y = int(m.group(1))
        if 1000 <= y <= 2100:
            return y
    return None


def extract_birth_year(person_uri, graph, verbose=False):
    for p98 in P98_BORN:
        for birth_event in graph.objects(person_uri, p98):
            if verbose:
                print(f"[DEBUG] Sprawdzam event urodzenia: {birth_event}")
            for p4 in P4_HAS_TIME_SPAN:
                for timespan_uri in graph.objects(birth_event, p4):
                    if verbose:
                        print(f"[DEBUG] Timespan znaleziony ({p4}): {timespan_uri}")
                    for p82 in P82A_BEGIN:
                        begin = graph.value(timespan_uri, p82)
                        if verbose:
                            print(f"[DEBUG] Begin ({p82}): {begin}")
                        y = _year_from_begin_literal(begin)
                        if y is not None:
                            return y
    return None


def extract_study_year(person_uri, graph, verbose=False) -> Optional[int]:
    study_years: List[int] = []

    for p11 in P11_PARTICIPATED:
        for event in graph.objects(person_uri, p11):
            for p4 in P4_HAS_TIME_SPAN:
                for timespan_uri in graph.objects(event, p4):
                    for p82 in P82A_BEGIN:
                        begin = graph.value(timespan_uri, p82)
                        if begin:
                            if verbose:
                                print(f"[DEBUG] Study event begin ({p82}): {begin}")
                            y = _year_from_begin_literal(begin)
                            if y is not None:
                                study_years.append(y)

    return min(study_years) if study_years else None


def _years_from_event_resource(event_uri, graph) -> List[int]:
    """Wszystkie lata z P4 → time-span → P82a na jednym zasobie (wydarzenie E7/E67…)."""
    years: List[int] = []
    for p4 in P4_HAS_TIME_SPAN:
        for timespan_uri in graph.objects(event_uri, p4):
            for p82 in P82A_BEGIN:
                begin = graph.value(timespan_uri, p82)
                y = _year_from_begin_literal(begin)
                if y is not None:
                    years.append(y)
    return years


def extract_death_year(person_uri, graph, verbose=False) -> Optional[int]:
    """Rok ze zdarzenia śmierci (P100 → E69 + time-span), jeśli jest w grafie."""
    years: List[int] = []
    for p100 in P100_DIED:
        for death_event in graph.objects(person_uri, p100):
            years.extend(_years_from_event_resource(death_event, graph))
    return min(years) if years else None
