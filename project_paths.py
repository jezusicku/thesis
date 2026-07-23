"""
Katalog główny projektu — zawsze względem tego pliku, nie względem CWD.
Dzięki temu skrypty działają po przeniesieniu folderu (np. Downloads → Documents/UJ).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def data_path(name: str) -> Path:
    return ROOT / "data" / name
