# service_facade.py
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models import UniversalTerm

# ultimate_term_corrector importu:
# Senin projende dosya ismi "ultimate_term_corrector.py" olduğu için
# öncelikle onu deniyoruz. Eğer farklı isimle (ultimate_term_corrector_v8.py)
# varsa oradan import etmeye de çalışır.
try:
    from ultimate_term_corrector import UltimateTermCorrectorV8, TermCorrection
except ImportError:  # fallback
    from ultimate_term_corrector_v8 import UltimateTermCorrectorV8, TermCorrection  # type: ignore

# Robust, format-aware DOM engine (SDL/memoQ/XLIFF), validates XML before saving and
# always enforces the terms. This is the original working engine; Forced mode uses it.
from universal_term_corrector import (
    UniversalTermCorrectorForce,
    TermCorrection as ForceTermCorrection,
)


class TermEngineService:
    """
    Terminology Intelligence Engine için servis katmanı.

    - Tek dosya alır (XLIFF / SDLXLIFF / MQXLIFF)
    - UniversalTerm listesi alır
    - UltimateTermCorrectorV8 motorunu kullanarak düzeltme yapar
    - Çıktıyı bytes + metadata olarak döner
    """

    def __init__(
        self,
        provider: str = "anthropic",
        api_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.provider = provider
        self.api_key = api_key or os.getenv("CLAUDE_API_KEY") or ""
        if not self.api_key:
            raise ValueError(
                "No API key provided. Set CLAUDE_API_KEY env var "
                "or pass api_key to TermEngineService."
            )

        self.logger = logger or self._create_default_logger()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def analyze_file(
        self,
        file_bytes: bytes,
        file_name: str,
        terms: List[UniversalTerm],
        mode: str = "ai_evaluated",  # "ai_evaluated" | "forced"
        lang_pair: Optional[Tuple[str, str]] = None,
        progress_callbacks: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,  # UI-selected current model id
        progress_cb: Optional[Any] = None,  # progress_cb(done:int, total:int)
    ) -> Dict[str, Any]:
        """
        Ana giriş noktası.
        - Dosyayı temp'e yazar
        - UltimateTermCorrectorV8 örneği oluşturur
        - TermCorrection listesini doldurur
        - process_file_v8 çalıştırır
        - Sonuçları ve düzeltilmiş dosyayı döner

        ultimate_term_corrector_v8 içindeki process_file_v8 imzası:
            process_file_v8(self, file_path: str, logger: logging.Logger)
        olduğu için progress_callbacks doğrudan motora gönderilmiyor. İleride
        motoru güncellersen entegre edebiliriz.
        """

        self.logger.info("Starting TermEngineService.analyze_file")

        # 1) Dosyayı temp klasöre yaz
        suffix = Path(file_name).suffix or ".xlf"
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="term_engine_"
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            self.logger.info("Temp file created at %s", tmp_path)

            # 2) Corrector örneği oluştur + işle (moda göre motor seç)
            force_mode = mode.lower() == "forced"

            if force_mode:
                # Forced → robust DOM engine: format-aware, always enforces, and
                # process_xliff_file writes the corrected file back to tmp_path.
                corrector = UniversalTermCorrectorForce(api_key=self.api_key, model=model)
                corrector.term_corrections = [
                    ForceTermCorrection(**t.to_term_correction_payload()) for t in terms
                ]
                corrections_made, detailed_results = corrector.process_xliff_file(
                    tmp_path, self.logger, progress_cb=progress_cb
                )
            else:
                # AI-evaluated (context-aware) → V8 engine; may skip changes it
                # judges semantically wrong.
                corrector = UltimateTermCorrectorV8(
                    api_key=self.api_key,
                    force_mode=False,
                    model=model,
                )
                if lang_pair is not None:
                    src_lang, tgt_lang = lang_pair
                    if hasattr(corrector, "source_lang"):
                        setattr(corrector, "source_lang", src_lang)
                    if hasattr(corrector, "target_lang"):
                        setattr(corrector, "target_lang", tgt_lang)
                corrector.term_corrections = [
                    TermCorrection(**t.to_term_correction_payload()) for t in terms
                ]
                v8_cbs: Dict[str, Any] = {}
                if progress_cb:
                    v8_cbs = {"batches": progress_cb, "variants": progress_cb}
                corrections_made, detailed_results = corrector.process_file_v8(
                    tmp_path, self.logger, v8_cbs
                )

            # Progress callback'i en azından iş bittiğinde %100 olarak set edelim
            if progress_callbacks and "overall" in progress_callbacks:
                cb = progress_callbacks["overall"]
                try:
                    cb("Completed", 1, 1)
                except Exception as e:
                    self.logger.warning(
                        "Progress callback failed at completion: %s", e
                    )

            # 6) Düzeltilmiş dosyayı oku
            with open(tmp_path, "rb") as f:
                corrected_bytes = f.read()

            # 7) JSON rapor üretilebiliyorsa üret (motor tipine göre)
            report_path: Optional[str] = None
            try:
                if hasattr(corrector, "generate_comprehensive_report"):
                    report_path = corrector.generate_comprehensive_report(
                        detailed_results, tmp_path, self.logger
                    )
                elif hasattr(corrector, "save_universal_report"):
                    report_path = corrector.save_universal_report(
                        detailed_results, tmp_path, self.logger
                    )
            except Exception as e:
                self.logger.warning("Report generation failed: %s", e)
                report_path = None

            stats = getattr(corrector, "processing_stats", {}) or {}
            counts = {
                "segments_found": stats.get("segments_found", 0),
                "instances_found": stats.get("instances_found_total", stats.get("instances_found", 0)),
                "segments_corrected": stats.get("segments_corrected", corrections_made),
                "instances_corrected": stats.get("instances_corrected", corrections_made),
                "unmapped_forms": stats.get("unmapped_forms", []),
            }

            return {
                "corrected_file_bytes": corrected_bytes,
                "corrections_made": corrections_made,
                "results": detailed_results,
                "report_path": report_path,
                "tmp_file_path": tmp_path,
                "counts": counts,
            }

        finally:
            self.logger.info("TermEngineService.analyze_file finished")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _create_default_logger(self) -> logging.Logger:
        logger = logging.getLogger("term_engine")
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger
