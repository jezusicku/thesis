import re

def clean_label(label):
    # Usuń przecinki
    label = label.replace(",", " ")

    # Usuń fragmenty typu "syn XYZ", "Ojciec XYZ", "córka XYZ" — także wieloczłonowe, z ukośnikiem
    label = re.sub(r'\b(Ojciec|ojciec|syn|córka)\s+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż/-]*(/[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż]*)?\b', '', label)

    # Usuń fragmenty typu "z Miasta" lub "z Miasta/Miasta"
    label = re.sub(r'\bz\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:/[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?\b', '', label)

    # Usuń podwójne spacje i spacje brzegowe
    label = re.sub(r'\s{2,}', ' ', label)
    label = label.strip()

    return label

