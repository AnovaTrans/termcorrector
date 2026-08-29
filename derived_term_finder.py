# derived_term_finder.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Set


# Bu karakterleri compound/kelime devamı olarak kabul ediyoruz
WORD_CHARS = r"[A-Za-zÀ-ÖØ-öø-ÿßÜüÄäÖö0-9_]"


def extract_segment_texts_from_xliff(file_bytes: bytes) -> List[str]:
    """
    XLIFF / SDLXLIFF / MQXLIFF benzeri dosyalardan <source> ve <target>
    içeriklerini çıkarır.

    XML parse edemezse fallback olarak tüm metni döndürür.
    """
    try:
        root = ET.fromstring(file_bytes)
    except Exception:
        text = file_bytes.decode(errors="ignore")
        return [text]

    texts: List[str] = []

    for elem in root.iter():
        tag = elem.tag
        if not isinstance(tag, str):
            continue

        tag_lower = tag.lower()
        if tag_lower.endswith("source") or tag_lower.endswith("target"):
            text = "".join(elem.itertext())
            if text and text.strip():
                texts.append(text)

    return texts


def find_derived_terms(
    file_bytes: bytes,
    base_term: str,
    modes: List[str] | None = None,
) -> List[str]:
    """
    base_term için derived candidate'lar bulur (source + target metinlerinde).

    modes:
        - 'prefix' → baseTerm*
        - 'suffix' → *baseTerm
        - 'any'    → *baseTerm*

    Artık:
    ✅ Case-insensitive
    ✅ Compound destekli
    ✅ Tire/bağlaç toleranslı
    """

    if modes is None:
        modes = ["prefix", "suffix"]

    base = (base_term or "").strip()
    if not base:
        return []

    base_escaped = re.escape(base)
    patterns: List[re.Pattern] = []

    # Örnekler:
    # Rezeptversionen, rezeptvarianten
    if "prefix" in modes:
        patterns.append(
            re.compile(
                rf"\b{base_escaped}{WORD_CHARS}+",
                re.IGNORECASE | re.UNICODE,
            )
        )

    # Örnekler:
    # Standardrezept, Portrezept
    if "suffix" in modes:
        patterns.append(
            re.compile(
                rf"{WORD_CHARS}+{base_escaped}\b",
                re.IGNORECASE | re.UNICODE,
            )
        )

    # Daha agresif mod: her yerde geçenler
    if "any" in modes:
        patterns.append(
            re.compile(
                rf"{WORD_CHARS}*{base_escaped}{WORD_CHARS}*",
                re.IGNORECASE | re.UNICODE,
            )
        )

    texts = extract_segment_texts_from_xliff(file_bytes)

    candidates: Set[str] = set()

    for txt in texts:
        if not txt:
            continue

        for pattern in patterns:
            for match in pattern.findall(txt):
                word = match.strip()

                if not word:
                    continue

                # Base kelimenin kendisini alma
                if word.lower() == base.lower():
                    continue

                candidates.add(word)

    # Alfabetik döndür
    return sorted(candidates, key=lambda x: x.lower())
