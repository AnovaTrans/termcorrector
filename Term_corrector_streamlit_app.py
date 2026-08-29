# Term_corrector_streamlit_app.py
# Streamlit UI for the Terminology Intelligence Engine
# Uses TermEngineService + UniversalTerm as the backend interface.

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import xml.etree.ElementTree as ET
import streamlit as st

# Sayfa ayarını EN BAŞA koyun
st.set_page_config(page_title="AICONTEXT Document Analyzer", page_icon="🚀", layout="wide")

# --- KESİN ÇÖZÜM: Fullscreen ve Footer Yok Edici ---
hide_streamlit_style = """
<style>
    /* 1. Alt Çubuğu (Toolbar) ve "Deploy" butonunu yok et */
    .stAppToolbar {visibility: hidden !important; display: none !important; height: 0px !important;}
    [data-testid="stToolbar"] {visibility: hidden !important; display: none !important; height: 0px !important;}
    
    /* 2. Fullscreen Butonunu (Sağ üstteki) yok et */
    button[title="View fullscreen"] {visibility: hidden !important; display: none !important;}
    
    /* 3. Header ve Hamburger Menüsünü yok et */
    header {visibility: hidden !important; display: none !important;}
    #MainMenu {visibility: hidden !important; display: none !important;}
    .stAppHeader {visibility: hidden !important; display: none !important;}
    
    /* 4. Alt kısımdaki "Made with Streamlit" yazısını yok et */
    footer {visibility: hidden !important; display: none !important; height: 0px !important;}
    .stFooter {visibility: hidden !important; display: none !important;}
    
    /* 5. Gömülü moddaki alt çubuğu (viewerBadge) yok et */
    .viewerBadge_container__1QSob {display: none !important;}
    .styles_viewerBadge__1yB5_ {display: none !important;}
    div[class*="viewerBadge"] {display: none !important;}
    
    /* 6. Uygulamanın üstündeki boşluğu kapat */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ... Kodunuzun geri kalanı buradan devam etsin ...

### Bu kodu uygulayıp GitHub'a gönderdiğinizde, Streamlit uygulamanızın altında veya üstünde tıklanacak hiçbir buton kalmayacaktır.

### 2. React Tarafında "Kullanıcı Kontrolü" (Güvenlik Ağı)

##Eğer olur da bir şekilde kullanıcı o butona basarsa veya linki kopyalayıp başka sekmede açarsa, uygulamanın çalışmasını engellemeliyiz.

##Bunun için Streamlit (Python) kodunuza şu mantığı ekleyin:

##**Mantık:** "Eğer bu uygulama bir `iframe` içinde (portalda) çalışmıyorsa veya URL'de geçerli bir `uid` yoksa, çalışmayı durdur."

##python
# app_ui.py dosyasının başlarına ekleyin

# URL parametrelerini al
query_params = st.query_params
user_id = query_params.get("uid", None)

# Eğer UID yoksa (yani portal üzerinden gelmemişse)
if not user_id:
    st.error("⛔ Yetkisiz Erişim! Bu uygulamaya sadece Anova Portal üzerinden erişebilirsiniz.")
    st.stop() # Uygulamayı tamamen durdur, hiçbir şey gösterme.

# Backend service + models (same folder imports)
from service_facade import TermEngineService
from models import UniversalTerm
from derived_term_finder import find_derived_terms


# ---------------------------------------------------------------------------
# Session State Helpers
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """Initialize Streamlit session_state with sane defaults."""
    if "terms" not in st.session_state:
        st.session_state.terms: List[Dict[str, Any]] = []

    if "file_bytes" not in st.session_state:
        st.session_state.file_bytes: Optional[bytes] = None

    if "file_name" not in st.session_state:
        st.session_state.file_name: Optional[str] = None

    if "detected_source_lang" not in st.session_state:
        st.session_state.detected_source_lang: str = "en"

    if "detected_target_lang" not in st.session_state:
        st.session_state.detected_target_lang: str = "tr"

    if "force_mode" not in st.session_state:
        st.session_state.force_mode: bool = False

    if "last_result" not in st.session_state:
        st.session_state.last_result: Optional[Dict[str, Any]] = None

    if "logger" not in st.session_state:
        st.session_state.logger = create_default_logger()

    # Derived term suggestion state
    if "derived_candidates" not in st.session_state:
        st.session_state.derived_candidates: List[str] = []
    if "derived_base_term" not in st.session_state:
        st.session_state.derived_base_term: str = ""

    # Language detection state
    if "lang_detected_from_file" not in st.session_state:
        st.session_state.lang_detected_from_file: bool = False
    if "lang_detected_message" not in st.session_state:
        st.session_state.lang_detected_message: str = ""


def create_default_logger() -> logging.Logger:
    logger = logging.getLogger("term_engine_streamlit")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Language Detection Helper
# ---------------------------------------------------------------------------


def detect_lang_pair_from_file(file_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to detect source/target languages from XLIFF / SDLXLIFF / MQXLIFF.

    Heuristics:
    - Look for attributes like:
      source-language, target-language, srcLang, trgLang, srclang, etc.
    - Scan root and then child elements.
    """
    try:
        root = ET.fromstring(file_bytes)
    except Exception:
        return None, None

    source_lang: Optional[str] = None
    target_lang: Optional[str] = None

    def consider_attribs(attrs: Dict[str, str]) -> None:
        nonlocal source_lang, target_lang
        for k, v in attrs.items():
            lk = k.lower()

            # Source-like keys
            if source_lang is None:
                if (
                    lk == "source-language"
                    or lk.endswith("srclang")
                    or ("source" in lk and "lang" in lk)
                    or lk == "srclang"
                    or lk == "srcloc"
                    or lk == "srclang"
                    or lk == "srclanguage"
                    or lk == "srclocale"
                ):
                    source_lang = v.strip()

            # Target-like keys
            if target_lang is None:
                if (
                    lk == "target-language"
                    or lk.endswith("trglang")
                    or ("target" in lk and "lang" in lk)
                    or lk == "trglang"
                    or lk == "tgtlang"
                    or lk == "trglocale"
                ):
                    target_lang = v.strip()

    # First: root
    consider_attribs(root.attrib)

    # Then: children
    if not (source_lang and target_lang):
        for elem in root.iter():
            consider_attribs(elem.attrib)
            if source_lang and target_lang:
                break

    return source_lang, target_lang


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------


def validate_term(term: str, max_length: int = 255) -> Tuple[bool, str]:
    """Basic validation for term strings."""
    if not term or not term.strip():
        return False, "Term cannot be empty."
    if len(term) > max_length:
        return False, f"Term exceeds {max_length} characters."
    # Very simple allowed character set; adjust as needed.
    if not re.match(r"^[\S ].*$", term):
        return False, "Term contains invalid characters."
    return True, "OK"


def detect_term_conflicts(terms: List[Dict[str, Any]]) -> List[str]:
    """Detect simple duplicate/overlap conflicts in current term list."""
    conflicts: List[str] = []
    seen = set()
    for t in terms:
        key = (
            t.get("source_term", "").strip().lower(),
            t.get("target_term", "").strip().lower(),
        )
        if key in seen:
            conflicts.append(f"Duplicate term pair: {key[0]} → {key[1]}")
        else:
            seen.add(key)
    return conflicts


# ---------------------------------------------------------------------------
# UI Sections
# ---------------------------------------------------------------------------


def sidebar_configuration() -> Tuple[str, bool]:
    """Sidebar: API key + mode selection."""
    st.sidebar.title("⚙️ Configuration")

    # Prefer environment variable in production:
    env_api_key = os.getenv("CLAUDE_API_KEY", "")
    if env_api_key:
        st.sidebar.success("Using CLAUDE_API_KEY from environment.")
    api_key_input = st.sidebar.text_input(
        "🔑 Claude API Key",
        type="password",
        help="In production, prefer the CLAUDE_API_KEY environment variable.",
    )

    api_key = api_key_input or env_api_key

    if not api_key:
        st.sidebar.warning("Please provide an API key to run corrections.")

    mode_label = st.sidebar.radio(
        "Correction Mode",
        ["AI-evaluated (context-aware)", "Forced (strict term enforcement)"],
        help=(
            "AI-evaluated mode can sometimes skip changes if they are semantically wrong. "
            "Forced mode always enforces the specified terms."
        ),
    )
    force_mode = mode_label.startswith("Forced")
    st.session_state.force_mode = force_mode

    return api_key, force_mode


def tab_upload_and_settings() -> None:
    st.header("1️⃣ Upload & Settings")

    st.markdown(
        "Upload the XLIFF / SDLXLIFF / MQXLIFF file you want to process "
        "and specify the source/target language codes."
    )

    allowed_extensions = {".xliff", ".xlf", ".xml", ".sdlxliff", ".mqxliff"}
    uploaded_file = st.file_uploader(
        "📂 Upload XLIFF / SDLXLIFF / MQXLIFF file",
        type=["xliff", "xlf", "xml", "sdlxliff", "mqxliff"],
    )

    if uploaded_file is not None:
        file_ext = Path(uploaded_file.name).suffix.lower()
        if file_ext not in allowed_extensions:
            st.error(
                f"Invalid file type. Allowed extensions: {', '.join(allowed_extensions)}"
            )
        else:
            st.success(f"File uploaded: {uploaded_file.name}")
            st.session_state.file_bytes = uploaded_file.getvalue()
            st.session_state.file_name = uploaded_file.name

            # Reset language detection state for this new file
            st.session_state.lang_detected_from_file = False
            st.session_state.lang_detected_message = ""

    # Auto-detect language pair ONCE per file
    if (
        st.session_state.get("file_bytes") is not None
        and not st.session_state.get("lang_detected_from_file", False)
    ):
        src_lang, tgt_lang = detect_lang_pair_from_file(st.session_state.file_bytes)
        if src_lang or tgt_lang:
            if src_lang:
                st.session_state.detected_source_lang = src_lang
            if tgt_lang:
                st.session_state.detected_target_lang = tgt_lang

            st.session_state.lang_detected_from_file = True
            st.session_state.lang_detected_message = (
                f"Language pair auto-detected from file metadata: "
                f"{src_lang or '?'} → {tgt_lang or '?'} (you can still override below)."
            )

    with st.expander("Language Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            s_lang = st.text_input(
                "Source language code (e.g. en, bg, de)",
                value=st.session_state.get("detected_source_lang", "en"),
                max_chars=8,
            )
        with col2:
            t_lang = st.text_input(
                "Target language code (e.g. tr, ro, fr)",
                value=st.session_state.get("detected_target_lang", "tr"),
                max_chars=8,
            )

        st.session_state.detected_source_lang = s_lang.strip() or "en"
        st.session_state.detected_target_lang = t_lang.strip() or "tr"

        st.info(
            f"Current language pair: **{st.session_state.detected_source_lang} → "
            f"{st.session_state.detected_target_lang}**"
        )
        if st.session_state.get("lang_detected_message"):
            st.caption(st.session_state.lang_detected_message)


def tab_terms() -> None:
    st.header("2️⃣ Term List")

    st.markdown(
        "Define source/target term pairs here. "
        "These will be enforced/corrected in the file, context-aware."
    )

    # Term input form
    with st.form("add_term_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            source_term = st.text_input("Source term")
        with col2:
            target_term = st.text_input("Target term")

        description = st.text_input("Description (optional)")
        submitted = st.form_submit_button("➕ Add term")

    if submitted:
        ok_s, msg_s = validate_term(source_term)
        ok_t, msg_t = validate_term(target_term)
        if not ok_s:
            st.error(f"Invalid source term: {msg_s}")
        elif not ok_t:
            st.error(f"Invalid target term: {msg_t}")
        else:
            st.session_state.terms.append(
                {
                    "source_term": source_term.strip(),
                    "target_term": target_term.strip(),
                    "description": description.strip(),
                }
            )
            st.success(f"Term added: {source_term.strip()} → {target_term.strip()}")

    # Conflict check
    conflicts = detect_term_conflicts(st.session_state.terms)
    if conflicts:
        with st.expander("⚠️ Term conflicts detected", expanded=False):
            for c in conflicts:
                st.warning(c)

    # Term list display + derived term suggestion
    if st.session_state.terms:
        st.subheader("Current term list")
        for idx, t in enumerate(st.session_state.terms, start=1):
            st.markdown(
                f"**{idx}.** `{t['source_term']}` → `{t['target_term']}`  "
                f"_{t.get('description', '') or 'No description'}_"
            )

        # Simple delete by index
        with st.expander("Remove a term", expanded=False):
            max_index = len(st.session_state.terms)
            to_delete = st.number_input(
                "Term index to remove",
                min_value=1,
                max_value=max_index,
                step=1,
                value=1,
            )
            if st.button("🗑️ Delete selected term"):
                removed = st.session_state.terms.pop(to_delete - 1)
                st.success(
                    f"Removed term: {removed['source_term']} → {removed['target_term']}"
                )

        # ---- Derived term suggestion block ----
        with st.expander("🔍 Suggest derived terms (experimental)", expanded=False):
            if not st.session_state.get("file_bytes"):
                st.info(
                    "To suggest derived terms, please upload a file in the 'Upload & Settings' tab first."
                )
            else:
                base_options = [
                    f"{idx+1}. {t['source_term']} → {t['target_term']}"
                    for idx, t in enumerate(st.session_state.terms)
                ]
                if not base_options:
                    st.info("No base terms available.")
                else:
                    selected_idx = st.selectbox(
                        "Select a base term to scan for derived forms",
                        options=list(range(len(base_options))),
                        format_func=lambda i: base_options[i],
                        key="derived_base_select",
                    )

                    modes = st.multiselect(
                        "Search patterns",
                        options=["prefix (term*)", "suffix (*term)", "any (*term*)"],
                        default=["prefix (term*)", "suffix (*term)"],
                        help="Use 'any' carefully; it can be noisy.",
                        key="derived_modes_select",
                    )

                    mode_keys: List[str] = []
                    if "prefix (term*)" in modes:
                        mode_keys.append("prefix")
                    if "suffix (*term)" in modes:
                        mode_keys.append("suffix")
                    if "any (*term*)" in modes:
                        mode_keys.append("any")

                    # Scan button: update candidates in session_state
                    if st.button("Scan file for derived terms", key="scan_derived"):
                        base_term = st.session_state.terms[selected_idx]["source_term"]
                        candidates = find_derived_terms(
                            st.session_state.file_bytes,
                            base_term,
                            modes=mode_keys or ["prefix", "suffix"],
                        )

                        st.session_state.derived_base_term = base_term
                        st.session_state.derived_candidates = candidates

                        if not candidates:
                            st.info(
                                "No derived candidates were found for this base term."
                            )
                        else:
                            st.success(
                                f"Found {len(candidates)} candidate(s). "
                                f"Scroll down to enter target terms and add them."
                            )

                    # Show current candidates from state
                    candidates = st.session_state.get("derived_candidates", [])
                    base_term = st.session_state.get("derived_base_term", "")

                    if candidates:
                        st.markdown(
                            f"**Base term:** `{base_term}` — enter target terms for the derived forms:"
                        )
                        st.caption(
                            "Each row: source variant (left), target term input (middle), 'Add term' button (right)."
                        )

                        # Per-row add buttons
                        for cand in candidates:
                            cols = st.columns([2, 3, 1])
                            with cols[0]:
                                st.markdown(f"- `{cand}`")

                            target_key = f"derived_target_{base_term}_{cand}"
                            with cols[1]:
                                st.text_input(
                                    "Target term",
                                    key=target_key,
                                    label_visibility="collapsed",
                                )

                            add_button_key = f"derived_addbtn_{base_term}_{cand}"
                            with cols[2]:
                                if st.button(
                                    "Add term",
                                    key=add_button_key,
                                ):
                                    tgt = (
                                        st.session_state.get(target_key, "")
                                        .strip()
                                    )
                                    if not tgt:
                                        st.warning(
                                            f"Please enter a target term for '{cand}' before adding."
                                        )
                                    else:
                                        st.session_state.terms.append(
                                            {
                                                "source_term": cand,
                                                "target_term": tgt,
                                                "description": f"Derived from base term '{base_term}'",
                                            }
                                        )
                                        st.rerun()

                        # ---- Add ALL terms at once ----
                        if st.button(
                            "➕ Add ALL terms",
                            key=f"derived_add_all_{base_term}",
                        ):
                            added = 0
                            for cand in candidates:
                                target_key = f"derived_target_{base_term}_{cand}"
                                tgt = (
                                    st.session_state.get(target_key, "")
                                    .strip()
                                )
                                if tgt:
                                    st.session_state.terms.append(
                                        {
                                            "source_term": cand,
                                            "target_term": tgt,
                                            "description": f"Derived from base term '{base_term}'",
                                        }
                                    )
                                    added += 1

                            if added == 0:
                                st.warning(
                                    "No target terms entered. Please fill in at least one target term."
                                )
                            else:
                                st.success(
                                    f"Added {added} new derived term(s) to the term list."
                                )
                                st.rerun()
                    else:
                        st.info(
                            "No derived candidates loaded yet. Click 'Scan file for derived terms' to search."
                        )
    else:
        st.info("No terms defined yet. Please add at least one term.")


def tab_process(api_key: str, force_mode: bool) -> None:
    st.header("3️⃣ Process File")

    if not api_key:
        st.error("Please provide an API key in the sidebar.")
        return

    if not st.session_state.file_bytes or not st.session_state.file_name:
        st.warning("Please upload a file in the 'Upload & Settings' tab.")
        return

    if not st.session_state.terms:
        st.warning("Please add at least one term in the 'Term List' tab.")
        return

    source_lang = st.session_state.detected_source_lang
    target_lang = st.session_state.detected_target_lang

    st.write(
        f"Ready to process file **{st.session_state.file_name}** "
        f"with {len(st.session_state.terms)} terms "
        f"({source_lang} → {target_lang})."
    )

    # Progress elements
    overall_progress = st.progress(0, text="Waiting to start...")
    status_placeholder = st.empty()

    def make_progress_callbacks() -> Dict[str, Any]:
        """
        Create callbacks compatible with TermEngineService/UltimateTermCorrectorV8.
        We expect something like: callback(stage, done, total)
        """

        def overall_cb(stage: str, done: int, total: int) -> None:
            if total <= 0:
                return
            ratio = done / total
            percent = int(ratio * 100)
            overall_progress.progress(percent, text=f"{stage}: {percent}%")

        return {"overall": overall_cb}

    callbacks = make_progress_callbacks()

    if st.button("🚀 Run Terminology Correction"):
        status_placeholder.info("Processing file, please wait...")
        try:
            service = TermEngineService(
                provider="anthropic",
                api_key=api_key,
                logger=st.session_state.logger,
            )

            # Convert term dicts → UniversalTerm list
            universal_terms: List[UniversalTerm] = []
            for idx, t in enumerate(st.session_state.terms, start=1):
                ut = UniversalTerm.from_simple_pair(
                    idx=idx,
                    source_term=t.get("source_term", ""),
                    target_term=t.get("target_term", ""),
                    source_lang=source_lang,
                    target_lang=target_lang,
                    description=t.get("description", ""),
                )
                universal_terms.append(ut)

            mode = "forced" if force_mode else "ai_evaluated"

            result = service.analyze_file(
                file_bytes=st.session_state.file_bytes,
                file_name=st.session_state.file_name,
                terms=universal_terms,
                mode=mode,
                lang_pair=(source_lang, target_lang),
                progress_callbacks=callbacks,
            )

            st.session_state.last_result = result
            status_placeholder.success("Processing complete.")
            overall_progress.progress(100, text="Completed")

            st.success(
                f"Corrections made: {result['corrections_made']} "
                f"(see 'Results' tab for details)."
            )

        except Exception as e:
            status_placeholder.error("An error occurred during processing.")
            st.error(str(e))
            st.session_state.logger.exception("Error in processing")


def tab_results() -> None:
    st.header("4️⃣ Results & Download")

    result = st.session_state.get("last_result")
    if not result:
        st.info("No results yet. Please process a file first.")
        return

    corrections_made = result.get("corrections_made", 0)
    detailed_results = result.get("results") or []
    report_path = result.get("report_path")

    st.subheader("Summary")
    st.write(f"**Corrections made:** {corrections_made}")
    st.write(f"**Units processed:** {len(detailed_results)}")

    # Preview a few results if available
    if detailed_results:
        st.subheader("Sample of corrected units")
        sample_size = min(5, len(detailed_results))

        for r in detailed_results[:sample_size]:
            # r can be dict or dataclass-like object
            if isinstance(r, Dict):
                unit_id = r.get("unit_id")
                src = r.get("source_text", "")
                orig_tgt = r.get("original_target", "")
                new_tgt = r.get("new_target", "")
            else:
                unit_id = getattr(r, "unit_id", None)
                src = getattr(r, "source_text", "")
                orig_tgt = getattr(r, "original_target", "")
                new_tgt = getattr(r, "new_target", "")

            st.markdown(f"**Unit ID:** `{unit_id}`")
            st.markdown(f"**Source:** {src}")
            st.markdown(f"**Original target:** {orig_tgt}")
            st.markdown(f"**New target:** {new_tgt}")
            st.markdown("---")

    # Download corrected file
    corrected_bytes = result.get("corrected_file_bytes")
    if corrected_bytes:
        out_name = st.session_state.file_name or "corrected_file.xlf"
        st.download_button(
            "⬇️ Download corrected file",
            data=corrected_bytes,
            file_name=f"corrected_{out_name}",
            mime="application/xml",
        )

    # Download JSON report if exists
    if report_path and Path(report_path).exists():
        with open(report_path, "rb") as f:
            report_bytes = f.read()
        st.download_button(
            "⬇️ Download JSON report",
            data=report_bytes,
            file_name=Path(report_path).name,
            mime="application/json",
        )


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Terminology Intelligence Engine",
        page_icon="🧠",
        layout="wide",
    )

    init_session_state()

    st.title("🧠 Terminology Intelligence Engine")
    st.caption(
        "Smart, context-aware terminology correction for XLIFF / SDLXLIFF / MQXLIFF files. "
        "Powered by LLMs, designed for CAT tool workflows."
    )

    api_key, force_mode = sidebar_configuration()

    tabs = st.tabs(
        [
            "Upload & Settings",
            "Terms",
            "Process",
            "Results",
        ]
    )

    with tabs[0]:
        tab_upload_and_settings()
    with tabs[1]:
        tab_terms()
    with tabs[2]:
        tab_process(api_key, force_mode)
    with tabs[3]:
        tab_results()


if __name__ == "__main__":
    main()
