# Dokumentacja: aplikacja do dopasowania osób z CAC do Wikidata

*Ostatnia aktualizacja treści: kwiecień 2026.*

Ten dokument jest napisany tak, żeby **za miesiąc czy dwa** nadal było jasne, **o co chodzi w projekcie**, bez żargonu z literatury informatycznej. Nazwy angielskie z kodu (np. w pliku CSV) są tu **wyjaśnione po polsku**.

---

## 1. Po co w ogóle jest ta aplikacja?

W bazie CAC (katalog biblioteki) masz rekordy o osobach związanych z Uniwersytetem Jagiellońskim. W **Wikidata** są encje z unikalnymi identyfikatorami (numery **Q…**), które można potem wykorzystać w innych systemach.

**Problem:** automatycznie „zgadnąć” właściwą osobę jest trudno — w CAC często jest mało danych, a nazwiska powtarzają się.

**Rozwiązanie:** prosta aplikacja w przeglądarce (Streamlit), w której **Ty** oglądasz propozycje z Wikidata i **zapisujesz swoją decyzję**. Z czasem powstaje **zbiór przykładów sprawdzonych ręcznie** — na ich podstawie można później oceniać automatyczne metody (inne programy, modele itd.).  

W literaturze taki sprawdzony zbiór bywa nazywany „zbiorem referencyjnym” lub po angielsku *gold standard* — **nie musisz tego zapamiętywać**. Ważne jest tylko: **to są Twoje potwierdzone lub odrzucone dopasowania**, zapisane w pliku (patrz niżej).

---

## 2. Jak z tego korzystasz w praktyce?

1. Uruchamiasz program (`streamlit run annotation_app.py` — szczegóły na końcu dokumentu).
2. Wczytuje się plik **RDF** z danymi (domyślnie `output_cidoc_cac_1000.rdf` w folderze projektu, jeśli tam jest).
3. Przechodzisz po **kolejnych osobach** z tego pliku.
4. Dla wybranej osoby możesz poprawić **frazę wyszukiwania** i kliknąć **Pobierz propozycje z Wikidata** — program łączy się z internetem i pokazuje kilku kandydatów z krótkim „punktowaniem” (to tylko podpowiedź, nie prawda objawiona).
5. Wybierasz jedną z trzech możliwości:
   - **„To jest poprawne dopasowanie”** przy wybranym Q… — zapisujesz, że ta encja z Wikidata pasuje do tej osoby z CAC.
   - **„Żaden z kandydatów nie pasuje”** — zapisujesz świadomie, że wśród podpowiedzi nie było dobrej pary (to też jest cenna informacja przy późniejszej ocenie metod).
   - **„Pomiń, nie zapisuj”** — idziesz dalej **bez** dopisywania wiersza (np. gdy nie masz czasu teraz decydować).

---

## 3. Gdzie fizycznie zapisują się Twoje decyzje?

Wszystko trafia do jednego pliku:

**`annotations/gold_labels.csv`**

(to jest zwykły plik tekstowy w formacie CSV — otworzysz go w Excelu, LibreOffice albo edytorze tekstu).

- Każde kliknięcie „zapisz dopasowanie” lub „brak dopasowania” **dopisuje nowy wiersz** na końcu pliku. **Nic nie znika**, jeśli zamkniesz aplikację.
- **Nie zapisuje się** numer „którą osobę oglądałaś” — po ponownym uruchomieniu program zaczyna od początku listy osób (ale **wcześniejsze wiersze w CSV zostają**).

### Co znaczą kolumny w tym pliku (w skrócie)

Najważniejsze dla Ciebie:

| W pliku CSV (nagłówek) | Co to znaczy po polsku |
|------------------------|-------------------------|
| `timestamp` | Kiedy zapisałaś decyzję (data i czas). |
| `person_uri` | Identyfikator osoby w pliku RDF (techniczny adres w grafie). |
| `label_clean` | Imię i nazwisko (lub etykieta) po uproszczeniu — do wyszukiwania. |
| `birth_year_cac`, `study_year_cac`, `birthplace_cac` | Co program **wyciągnął z RDF** dla tej osoby (rok urodzenia, rok studiów, miejsce) — może być puste. |
| `search_query_used` | Jakiej frazy użyłaś do wyszukiwarki Wikidata w tym momencie. |
| `chosen_qid` | Wybrany identyfikator Wikidata, np. **Q12345** — albo pusto, jeśli uznałaś, że nikt nie pasuje. |
| `chosen_uri` | Link do strony tej encji na Wikidata (albo pusto). |
| `decision` | Rodzaj decyzji — **w pliku jest po angielsku**, bo tak ustawiono nagłówek: |
| | **`chosen`** = „uznałam, że to właściwe dopasowanie” (wybrane Q…). |
| | **`none_match`** = „żaden z pokazanych kandydatów nie pasuje”. |
| `notes` | Twoja opcjonalna notatka z pola w aplikacji. |

Jeśli kiedyś zobaczysz w Excelu kolumnę `decision` z wartością `chosen` albo `none_match` — **to tylko skrót zapisany przez program**; znaczenie jest jak w tabeli powyżej.

---

## 4. Co dokładnie pokazuje aplikacja z danych CAC?

- **Etykieta** — zwykle imię i nazwisko lub dłuższy opis osoby z grafu.
- **Rok urodzenia** — jeśli w pliku RDF jest powiązane wydarzenie urodzenia z datą.
- **Rok studiów (szacunek)** — program bierze **najwcześniejszy rok** z dat przypiętych do wydarzeń typu udział w nauce (to jest uproszczenie: „pierwszy rok, który udało się odczytać z przedziału czasu”).
- **Miejsce urodzenia** — tekst z grafu; często program pokazuje też **„znormalizowaną”** wersję (np. diecezja → duże miasto), żeby łatwiej porównywać z Wikidata.

Dodatkowo, jeśli są w RDF: **fragmenty imion (apelatywy)**, **typy działalności** (np. immatrykulacja, stopnie), **przykładowe wydarzenia**, **publikacje / dzieła** — żeby ułatwić ręczne rozstrzygnięcie, gdy sama etykieta jest uboga.

---

## 5. Ograniczenia i trudności — to najważniejsza część

Tu nie chodzi o błędy programisty w stylu „zapomniał importu” — tylko o **to, że same dane i źródła są trudne**, niezależnie od aplikacji.

### 5.1 Dziwne i różne zapisy **miejsc pochodzenia** w CAC

W katalogu jedna osoba może mieć np. samą **diecezję**, inna — **miasto i diecezję**, inna — **wieś koło Krakowa**, jeszcze inna — **długi opis z łaciną i nazwami w kilku językach**. Nie ma dwóch identycznych schematów.

**Co zrobił program:** dodał **reguły i słownik** (np. diecezja krakowska → Kraków jako punkt odniesienia do porównania z Wikidata), rozbijanie po przecinkach, usuwanie nawiasów z tłumaczeniami, rozpoznawanie „koło Krakowa”, skrótów typu (sand) itd.

**Czego nie da się zamknąć w 100% regułami:** jednoznacznie powiedzieć „to zawsze to samo miasto” przy zapisach typu *Nova Civitas (które?)*, *Landau (które?)*, łacińskich przydomków (*…ensis*) bez dodatkowej wiedzy historycznej albo **Twojej decyzji przy adnotacji**.

### 5.2 Dziwne zapisy **czasów** w katalogu vs to, co widzi program

W **bazie CAC** (tabele) często jest kolumna z opisem okresu po polsku: *początek semestru zimowego*, *koniec roku akademickiego* itd. — **długi tekst**.

W **eksporcie RDF**, którego używa aplikacja, te same informacje są zapisane inaczej: jako **przedziały czasu na wydarzeniach** (konkretne daty lub rok w strukturze technicznej).

Dlatego:

- **Rok studiów w aplikacji** liczy się z **tego, co jest w pliku RDF** (daty przy wydarzeniach), **a nie** przez odczytanie słów „pocz. sem…” z opisu tekstowego z katalogu.
- Jeśli w RDF **czegoś brakuje** (np. nie ma podpiętego wydarzenia z datą), w aplikacji może być **pusto** przy roku studiów — mimo że w tabeli CAC „coś tam” widnieje. To nie jest „losowy błąd przycisku”, tylko **różnica między tym, co wyeksportowano do RDF, a pełnym opisem w katalogu**.

W samej aplikacji jest krótka informacja przy polach z latami, żeby o tym nie zapomnieć.

### 5.3 Ograniczone informacje o osobie

Często w CAC jest głównie **imię, nazwisko, ojciec, lata związane ze studiami**, czasem miejsce — a **bez** dat urodzenia/śmierci. Wtedy automatyczne odsianie złych kandydatów z Wikidata jest **słabsze** (program i tak stara się użyć roku studiów i ewentualnie miejsca, ale nie zawsze da się „udowodnić”, że to nie ten sam Jan Kowalski).

### 5.4 Wikidata też nie jest idealna

- Ktoś może **nie mieć daty urodzenia** albo **miejsca** na Wikidata — wtedy porównanie jest tylko po nazwisku i ogólnych cechach.
- Miejsce urodzenia (pole na Wikidata) bywa **krajem** albo **dużym regionem**, a w CAC — **wioską** — dopasowanie jest przybliżone, nie „na milimetr”.
- Wyszukiwarka Wikidata czasem podsuwa **źle brzmiące** trafienia — stąd potrzeba **Twojej oceny** i zapisu do CSV.

### 5.5 Imiona: samo imię, nazwisko w nawiasie, podwójne formy

Etykiety w RDF bywają różnie zapisane (np. wariant nazwiska w nawiasie). Program **czyści** część najczęstszych fragmentów (np. *syn X*), ale **nie rozstrzyga** wszystkich historycznych wariantów zapisu — to nadal pole do **Twojej interpretacji** przy wyszukiwaniu i wyborze Q…

### 5.6 Utrzymanie słownika miejsc

Lista mapowań (diecezje → miasta itd.) **nie jest zamknięta na zawsze**. Jak pojawią się nowe, dziwne opisy w danych, sensowne jest **dopisywanie reguł** albo akceptacja, że część przypadków zawsze zostanie **tylko przy ręcznym dopasowaniu**.

---

## 6. Co program **nie robi** (i nie zrobi sam z siebie)

- **Nie czyta** długich polskich opisów typu „początek semestru…” jako jedynego źródła roku — patrz punkt 5.2.
- **Nie rozstrzyga** wszystkich dwuznacznych miejsc na świecie bez Twojej decyzji lub bez osobnych baz (np. współrzędnych).
- **Nie łączy** automatycznie z VIAF, NUKAT itd. — w tym projekcie jest **Wikidata** jako główny cel identyfikatorów Q….
- **Nie gwarantuje**, że przyszła wersja eksportu RDF z CAC będzie wyglądać identycznie — jeśli zmieni się sposób eksportu, **może być potrzeba aktualizacji kodu** (to normalne przy projektach badawczych).

---

## 7. Krótka notatka techniczna (opcjonalna)

Poniżej tylko dla orientacji, **jeśli kiedyś będziesz rozmawiać z programistą**:

- Aplikacja: `annotation_app.py`.
- RDF: format XML, osoby jako `E21_Person`, namespace predykatów głównie **CIDOC CRM** (wcześniej część kodu zakładała inny namespace — to poprawiono, żeby lata i wydarzenia się wczytywały).
- Wikidata: wyszukiwarka encji + zapytania pobierające m.in. daty urodzenia, śmierci, miejsce urodzenia, informację „człowiek” (Q5).
- Normalizacja miejsc: `extract_data/matching_birth_places.py` + wykorzystanie przy punktacji w `annotator/wikidata_candidates.py`.

**Nie musisz tego pamiętać**, żeby korzystać z adnotacji — ważniejsze są sekcje 1–6.

---

## 8. Jak uruchomić aplikację

W terminalu, w folderze projektu:

```bash
cd /ścieżka/do/JU_heritage
source .venv/bin/activate
streamlit run annotation_app.py
```

Potem w przeglądarce zwykle adres: **http://localhost:8501**

---

## 9. Podsumowanie w jednym akapicie

Aplikacja pomaga **ręcznie** powiązać osoby z eksportu CAC (RDF) z odpowiednimi stronami **Wikidata**, pokazuje dodatkowe informacje z grafu, gdy są dostępne, i **zapisuje Twoje decyzje** w pliku `annotations/gold_labels.csv`. Największe trudności wynikają z **samej natury danych historycznych**: niespójne zapisy miejsc, różnica między opisem tekstowym w katalogu a tym, co trafia do RDF, oraz niepełność informacji — dlatego część pracy zawsze pozostaje **świadomym wyborem człowieka**, a program tylko wspiera i zapisuje wynik.
