# models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UniversalTerm:
    """
    Dil-agnostik terminoloji modeli.
    Hem kaynak hem hedef dil için lemma, varyantlar ve özellikler saklanır.
    Bu model Term_corrector_streamlit_app.py içinde kullanılıyor ve
    service_facade.TermEngineService tarafından TermCorrection'a dönüştürülüyor.
    """

    id: int
    source_language: str
    target_language: str

    lemma_source: str
    lemma_target: str

    source_variants: List[str] = field(default_factory=list)
    target_variants: List[str] = field(default_factory=list)

    source_features: Dict[str, Any] = field(default_factory=dict)
    target_features: Dict[str, Any] = field(default_factory=dict)

    description: str = ""
    domain: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_simple_pair(
        cls,
        idx: int,
        source_term: str,
        target_term: str,
        source_lang: str,
        target_lang: str,
        description: str = "",
        domain: str = "",
    ) -> "UniversalTerm":
        """
        Streamlit arayüzünden gelen basit source/target çiftlerini
        UniversalTerm nesnesine dönüştürmek için yardımcı metod.
        """
        return cls(
            id=idx,
            source_language=source_lang.strip(),
            target_language=target_lang.strip(),
            lemma_source=(source_term or "").strip(),
            lemma_target=(target_term or "").strip(),
            description=(description or "").strip(),
            domain=(domain or "").strip(),
        )

    def to_term_correction_payload(self) -> Dict[str, Any]:
        """
        ultimate_term_corrector içindeki TermCorrection dataclass'ına
        aktarılacak olan alanları dict olarak hazırlar.
        """
        return {
            "term_id": self.id,
            "source_term": self.lemma_source,
            "target_term": self.lemma_target,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "description": self.description,
            # TermCorrection'da 'variants' alanı yok ama ileride eklemek istersek
            # target_variants'ı burada kullanabiliriz. Şimdilik sadece temel alanlar.
        }

    def add_source_variant(self, form: str) -> None:
        form = (form or "").strip()
        if form and form not in self.source_variants:
            self.source_variants.append(form)

    def add_target_variant(self, form: str) -> None:
        form = (form or "").strip()
        if form and form not in self.target_variants:
            self.target_variants.append(form)
