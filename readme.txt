# Terminology Intelligence Engine (TermCorrector)

Smart, context-aware terminology correction tool for bilingual translation files (XLIFF / SDLXLIFF / MQXLIFF).  
Designed for CAT tool workflows and powered by **Claude 3 Opus** via the Anthropics API.

This app lets you define terminology rules, discover derived term variants (e.g. `Rezeptversionen`, `Standardrezept`), and safely correct target segments with full control.

---

## ✨ Features

- 🔁 **Bilingual file support**  
  - XLIFF / SDLXLIFF / MQXLIFF / MQXLIFF-like XML

- 🧠 **LLM-powered terminology engine**
  - Uses Anthropics’ Claude (currently `claude-3-opus`) via the `anthropic` Python SDK  
  - Two modes:
    - **AI-evaluated (context-aware)** – only change terms if contextually correct  
    - **Forced mode** – strictly enforce the term list

- 🧬 **Derived term discovery (regex + human-in-the-loop)**
  - Start from a base term: `Rezept → Tarif`
  - Scan file for variants:
    - `Rezeptversionen`, `Standardrezept`, `Portrezept`, `Rezepte`, …
  - For each variant:
    - Enter the target term
    - Add individually **or** use **“Add ALL terms”** to add them in bulk

- 🌍 **Automatic language pair detection**
  - Reads XLIFF/SDLXLIFF metadata (`source-language`, `target-language`, etc.)
  - Pre-fills source/target language codes on upload (you can still override manually)

- 📊 **Progress tracking & result preview**
  - Global progress bar
  - Summary of units processed and corrections made
  - Sample of changed segments (source / original target / new target)
  - Download:
    - Corrected bilingual file
    - JSON report (if enabled in backend)

---

## 🗂 Project Structure

Typical repository layout:

```text
.
├── Term_corrector_streamlit_app.py   # Main Streamlit UI
├── service_facade.py                 # TermEngineService: LLM & engine wrapper
├── models.py                         # UniversalTerm and related data models
├── universal_term_corrector.py       # Core term correction logic
├── derived_term_finder.py            # Regex-based derived term discovery
├── requirements.txt                  # Python dependencies
├── README.md                         # This file
└── .gitignore                        # Ignore cache, env, and client data
