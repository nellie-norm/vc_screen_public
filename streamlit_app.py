#!/usr/bin/env python3
"""
Bramble Partners - Investment Screening (Streamlit)
"""

import streamlit as st
import os
import tempfile
from pathlib import Path
from datetime import datetime

# Load secrets from .secrets.toml for local dev, or from Streamlit Cloud secrets
def load_secrets():
    secrets_file = Path(__file__).parent / ".secrets.toml"
    if secrets_file.exists():
        import toml
        secrets = toml.load(secrets_file)
        for key, value in secrets.items():
            if key not in os.environ:
                os.environ[key] = str(value)

load_secrets()

# Import existing screening functions (after loading secrets)
from bramble_screen import (
    extract_pdf_text,
    extract_company_info,
    research_companies_house,
    research_investors,
    research_with_perplexity,
    analyze_company
)
from html_generator import create_memo
import anthropic

# ============ CONFIG ============
APP_PASSWORD = os.environ.get("BRAMBLE_PASSWORD", "bramble2026")
BASE_DIR = Path(__file__).parent
OUTPUT_FOLDER = BASE_DIR / 'memos'
OUTPUT_FOLDER.mkdir(exist_ok=True)

# ============ PAGE CONFIG ============
st.set_page_config(
    page_title="Bramble Partners - Investment Screener",
    page_icon="🌿",
    layout="centered"
)

# ============ CUSTOM CSS ============
st.markdown("""
<style>
    .stApp { background-color: #f7f6f3; }
    h1 { color: #2d3b1f !important; text-align: center; }
    .subtitle { text-align: center; color: #666; margin-bottom: 2rem; }
    .stButton > button {
        background-color: #2d3b1f;
        color: white;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #4a5d35;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ============ AUTH ============
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("# Bramble Partners")
        st.markdown('<p class="subtitle">Investment Screener</p>', unsafe_allow_html=True)
        password = st.text_input("Enter password", type="password")
        if st.button("Login"):
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
        st.stop()

check_password()


# ============ MAIN APP ============
st.markdown("# Bramble Partners")
st.markdown('<p class="subtitle">Upload a pitch deck to generate an investment memo</p>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload pitch deck (PDF)", type=["pdf"])
notes = st.text_area("Additional notes (optional)", placeholder="Meeting notes, questions to explore...", height=100)

if uploaded_file is not None:
    if st.button("Run Investment Screen", type="primary"):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        try:
            progress = st.progress(0, text="Starting...")
            status = st.empty()

            status.info("Extracting text from PDF...")
            progress.progress(10)
            deck_content = extract_pdf_text(tmp_path)

            if not deck_content.strip():
                st.error("Could not extract text from PDF.")
                st.stop()

            status.info("Identifying company...")
            progress.progress(20)
            client = anthropic.Anthropic()
            company_info = extract_company_info(client, deck_content)
            company_name = company_info.get('company_name', 'Unknown')
            st.success(f"Found: **{company_name}**")

            status.info("Checking Companies House...")
            progress.progress(35)
            ch_research = research_companies_house(company_name)

            status.info("Researching investors...")
            progress.progress(50)
            investor_research = research_investors(company_name, company_info.get('industry', 'technology'))

            status.info("Deep research...")
            progress.progress(65)
            perplexity_research = research_with_perplexity(company_info)

            research_text = f"""=== COMPANIES HOUSE ===
{ch_research}

=== INVESTOR RESEARCH ===
{investor_research}

=== GENERAL RESEARCH ===
{perplexity_research}"""

            status.info("Running Bull vs Bear analysis...")
            progress.progress(80)
            analysis = analyze_company(deck_content, research_text, notes)

            status.info("Generating memo...")
            progress.progress(95)

            memo_text = analysis['memo']
            bull_case = analysis['bull_case']
            bear_case = analysis['bear_case']
            deliberation = analysis.get('deliberation', '')

            date_str = datetime.now().strftime("%Y-%m-%d")
            date_display = datetime.now().strftime("%d %B %Y")
            safe_name = company_name.replace(" ", "_").replace("/", "-")
            output_filename = f"MEMO_{safe_name}_{date_str}.html"
            output_path = OUTPUT_FOLDER / output_filename

            create_memo(
                analysis=memo_text,
                output_path=str(output_path),
                source=uploaded_file.name,
                date_str=date_display,
                bull_case=bull_case,
                bear_case=bear_case,
                deliberation=deliberation
            )

            progress.progress(100)
            status.empty()

            st.success(f"Memo generated for **{company_name}**")

            with open(output_path, 'r') as f:
                memo_html = f.read()

            st.download_button(
                label="Download Memo (HTML)",
                data=memo_html,
                file_name=output_filename,
                mime="text/html"
            )

            st.markdown("### Preview")
            st.components.v1.html(memo_html, height=800, scrolling=True)

        except Exception as e:
            st.error(f"Error: {str(e)}")

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

# Recent memos
st.markdown("---")
st.markdown("### Recent Memos")
memos = sorted(OUTPUT_FOLDER.glob('*.html'), key=lambda x: x.stat().st_mtime, reverse=True)[:10]

if memos:
    for memo in memos:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{memo.stem}**")
        with col2:
            with open(memo, 'r') as f:
                st.download_button("Download", f.read(), memo.name, "text/html", key=memo.name)
else:
    st.markdown("*No memos yet.*")

# Sidebar
with st.sidebar:
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()
    st.markdown("---")
    st.markdown("**Required API Keys:**")
    st.markdown("- ANTHROPIC_API_KEY")
    st.markdown("- PERPLEXITY_API_KEY")
    st.markdown("- COMPANIES_HOUSE_API_KEY")
