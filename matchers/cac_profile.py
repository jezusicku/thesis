"""Jeden tekst profilu osoby z CAC — do porównań tekstowych / embeddingów."""
from __future__ import annotations

from annotator.features import PersonFeatures


def build_cac_profile_text(feats: PersonFeatures) -> str:
    parts: list[str] = []
    if feats.label_clean:
        parts.append(feats.label_clean)
    if feats.birthplace:
        parts.append(feats.birthplace)
    if feats.birthplace_normalized and feats.birthplace_normalized != feats.birthplace:
        parts.append(feats.birthplace_normalized)
    if feats.birth_year:
        parts.append(f"ur. {feats.birth_year}")
    if feats.study_year:
        parts.append(f"studia {feats.study_year}")
    parts.extend((feats.activity_types or [])[:12])
    parts.extend((feats.appellations or [])[:8])
    if feats.publications:
        parts.extend(feats.publications[:5])
    return " ".join(p for p in parts if p).strip()
