
import io
import uuid
import logging
import textwrap
import time
from typing import Optional

import streamlit as st

# PDF extraction
try:
    import pdfplumber
    _PDF_ENGINE = "pdfplumber"
except ImportError:
    import PyPDF2
    _PDF_ENGINE = "PyPDF2"

from dify_client import DifyClient, DifyAPIError, DifyAuthError, DifyStreamError, get_client


# Page config
st.set_page_config(
    page_title="Rissess.AI",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rissess_ai.app")

# CSS
CUSTOM_CSS = """
<style>
  /* ── Google Fonts ───────────────────────────────────────────── */
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

  /* ── Root palette ───────────────────────────────────────────── */
  :root {
    --bg-primary:   #0D0F14;
    --bg-card:      #13161E;
    --bg-elevated:  #1A1E28;
    --border:       #252A36;
    --border-glow:  #2E4A82;
    --accent:       #3B72F0;
    --accent-soft:  #1E3A7A;
    --success:      #22C55E;
    --warning:      #F59E0B;
    --danger:       #EF4444;
    --text-primary: #E8EAF0;
    --text-muted:   #6B7280;
    --text-dim:     #374151;
  }

  /* ── Base ───────────────────────────────────────────────────── */
  html, body, [data-testid="stAppViewContainer"],
  [data-testid="stApp"] {
    background-color: var(--bg-primary) !important;
    font-family: 'DM Sans', sans-serif !important;
    color: var(--text-primary) !important;
  }

  /* ── Hide Streamlit chrome ──────────────────────────────────── */
  #MainMenu, footer, header { visibility: hidden; }
  [data-testid="stDecoration"] { display: none; }

  /* ── Sidebar ────────────────────────────────────────────────── */
  [data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
  }
  [data-testid="stSidebar"] * { color: var(--text-primary) !important; }

  /* ── Main content padding ───────────────────────────────────── */
  .main .block-container {
    padding: 2rem 3rem !important;
    max-width: 1100px !important;
  }

  /* ── Logo / Wordmark ────────────────────────────────────────── */
  .uw-wordmark {
    font-family: 'DM Serif Display', serif;
    font-size: 2.2rem;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    line-height: 1;
  }
  .uw-wordmark span {
    color: var(--accent);
  }
  .uw-tagline {
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-top: 0.35rem;
  }

  /* ── Cards ──────────────────────────────────────────────────── */
  .uw-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
  }
  .uw-card-accent {
    border-left: 3px solid var(--accent);
  }

  /* ── Section labels ─────────────────────────────────────────── */
  .uw-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
  }

  /* ── Risk badge ─────────────────────────────────────────────── */
  .risk-high   { color: var(--danger);  font-weight: 600; }
  .risk-medium { color: var(--warning); font-weight: 600; }
  .risk-low    { color: var(--success); font-weight: 600; }

  /* ── Status pill ────────────────────────────────────────────── */
  .status-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px;
    border-radius: 999px;
    font-family: 'DM Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    border: 1px solid;
  }
  .status-ready  { background: #0F2A1A; border-color: #16532E; color: var(--success); }
  .status-active { background: #0F1E3A; border-color: var(--border-glow); color: #7BA7F7; }
  .status-error  { background: #2A0F0F; border-color: #7F1D1D; color: #FCA5A5; }
  .status-dot    { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

  /* ── Document preview box ───────────────────────────────────── */
  .doc-preview {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    line-height: 1.7;
    max-height: 160px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* ── Memo output container ──────────────────────────────────── */
  .memo-container {
    background: var(--bg-card);
    border: 1px solid var(--border-glow);
    border-radius: 10px;
    padding: 2rem;
    margin-top: 1.5rem;
  }
  .memo-container h1, .memo-container h2, .memo-container h3 {
    font-family: 'DM Serif Display', serif !important;
    color: var(--text-primary) !important;
  }
  .memo-container table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.85rem;
  }
  .memo-container th, .memo-container td {
    border: 1px solid var(--border);
    padding: 0.5rem 0.75rem;
    text-align: left;
  }
  .memo-container th { background: var(--bg-elevated); color: var(--text-muted); }
  .memo-container blockquote {
    border-left: 3px solid var(--accent);
    padding-left: 1rem;
    color: var(--text-muted);
    font-style: italic;
    font-size: 0.88rem;
  }

  /* ── Streamlit button overrides ─────────────────────────────── */
  .stButton > button {
    background: var(--accent) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 7px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 0.55rem 1.4rem !important;
    transition: opacity 0.15s !important;
  }
  .stButton > button:hover { opacity: 0.85 !important; }
  .stButton > button:disabled { opacity: 0.4 !important; cursor: not-allowed !important; }

  /* Secondary buttons */
  .secondary-btn > button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-muted) !important;
  }

  /* ── File uploader ──────────────────────────────────────────── */
  [data-testid="stFileUploader"] {
    border: 1px dashed var(--border) !important;
    border-radius: 10px !important;
    background: var(--bg-elevated) !important;
    padding: 0.5rem !important;
  }
  [data-testid="stFileUploader"] * { color: var(--text-primary) !important; }

  /* ── Divider ────────────────────────────────────────────────── */
  hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

  /* ── Spinner text ───────────────────────────────────────────── */
  .stSpinner > div { color: var(--accent) !important; }

  /* ── Info / warning boxes ───────────────────────────────────── */
  .stAlert { border-radius: 8px !important; }

  /* ── Scrollbar ──────────────────────────────────────────────── */
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: var(--bg-primary); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
</style>
"""


# PDF Extraction
def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    text_parts = []
    page_count = 0

    if _PDF_ENGINE == "pdfplumber":
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())
    else:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text.strip())

    full_text = "\n\n".join(text_parts).strip()

    if not full_text:
        raise ValueError(
            "No text could be extracted. The PDF may be scanned or image-only. "
            "Please provide a text-based PDF."
        )

    return full_text, page_count


def truncate_for_preview(text: str, max_chars: int = 600) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n… [{len(text) - max_chars:,} more characters]"


# Session state initialisation
def init_session_state():
    defaults = {
        "user_id":        f"uw_{uuid.uuid4().hex[:10]}",
        "pdf_text":       None,
        "pdf_name":       None,
        "pdf_pages":      None,
        "memo_result":    None,
        "is_analysing":   False,
        "error_message":  None,
        "client_ready":   False,
        "analysis_count": 0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# Dify client initialisation
@st.cache_resource(show_spinner=False)
def load_dify_client() -> Optional[DifyClient]:

    try:
        client = get_client()
        return client
    except DifyAuthError:
        return None
    except Exception:
        return None

# Sidebar

def render_sidebar(client: Optional[DifyClient]):
    with st.sidebar:
        st.markdown("""
            <div style="margin-bottom: 1.5rem;">
                <div class="uw-wordmark">Ri<span>ssess</span></div>
                <div class="uw-tagline">AI Risk Assessment Platform</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Connection status
        st.markdown('<div class="uw-label">System Status</div>', unsafe_allow_html=True)
        if client:
            st.markdown(
                '<div class="status-pill status-ready">'
                '<span class="status-dot"></span>Agent Online</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-pill status-error">'
                '<span class="status-dot"></span>Not Connected</div>',
                unsafe_allow_html=True,
            )
            st.warning("Set `DIFY_API_KEY` in your `.env` file to connect.", icon="🔑")

        st.markdown("---")

        # Session info
        st.markdown('<div class="uw-label">Session</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-family: DM Mono, monospace; font-size: 0.7rem; '
            f'color: #6B7280;">ID: {st.session_state.user_id[:16]}…</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.analysis_count:
            st.markdown(
                f'<div style="font-family: DM Mono, monospace; font-size: 0.7rem; '
                f'color: #6B7280; margin-top: 4px;">'
                f'Analyses run: {st.session_state.analysis_count}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("")

        # Reset session button
        with st.container():
            st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
            if st.button("↺  New Session", use_container_width=True):
                if client:
                    client.reset_session(st.session_state.user_id)
                for key in ["pdf_text", "pdf_name", "pdf_pages", "memo_result", "error_message"]:
                    st.session_state[key] = None
                st.session_state.analysis_count = 0
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")

        # Instructions
        st.markdown('<div class="uw-label">How to Use</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div style="font-size: 0.8rem; color: #6B7280; line-height: 1.8;">
            <b style="color: #9CA3AF;">1.</b> Upload a loan application<br>
            &nbsp;&nbsp;&nbsp;or insurance PDF<br><br>
            <b style="color: #9CA3AF;">2.</b> Click <b style="color: #E8EAF0;">Run Risk Analysis</b><br><br>
            <b style="color: #9CA3AF;">3.</b> The AI agent will:<br>
            &nbsp;&nbsp;&nbsp;• Extract key entities<br>
            &nbsp;&nbsp;&nbsp;• Search for reputation data<br>
            &nbsp;&nbsp;&nbsp;• Check policy compliance<br>
            &nbsp;&nbsp;&nbsp;• Generate a Risk Memo<br><br>
            <b style="color: #9CA3AF;">4.</b> Review the structured memo
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            '<div style="font-size: 0.68rem; color: #374151; line-height: 1.6;">'
            '⚠️ For demonstration purposes only. Not financial or legal advice.'
            '</div>',
            unsafe_allow_html=True,
        )

def render_header():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            """
            <div style="margin-bottom: 0.25rem;">
                <div class="uw-wordmark" style="font-size: 1.8rem;">
                    Ri<span>ssess</span><span style="color: #374151;">.</span><span style="color: #3B72F0;">AI</span>
                </div>
                <div class="uw-tagline" style="margin-top: 0.2rem;">
                    Autonomous Business Risk Assessment
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        if st.session_state.is_analysing:
            st.markdown(
                '<div style="text-align:right; padding-top: 0.6rem;">'
                '<div class="status-pill status-active">'
                '<span class="status-dot"></span>Analysing</div></div>',
                unsafe_allow_html=True,
            )
        elif st.session_state.memo_result:
            st.markdown(
                '<div style="text-align:right; padding-top: 0.6rem;">'
                '<div class="status-pill status-ready">'
                '<span class="status-dot"></span>Complete</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")


def render_upload_section() -> Optional[bytes]:
    """Render the PDF upload section. Returns raw bytes if a file is uploaded."""
    st.markdown('<div class="uw-label">Document Upload</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader(
            label="Upload PDF",
            type=["pdf"],
            label_visibility="collapsed",
            help="Upload a business loan application or commercial insurance PDF.",
        )

    with col2:
        st.markdown(
            """
            <div class="uw-card" style="padding: 1rem; margin-top: 0;">
              <div class="uw-label">Supported Formats</div>
              <div style="font-size: 0.78rem; color: #6B7280; line-height: 1.8;">
                📄 Loan applications<br>
                📋 Insurance proposals<br>
                🏢 Business financials<br>
                📑 Credit submissions
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if uploaded_file:
        return uploaded_file.read(), uploaded_file.name
    return None, None


def render_document_preview():
    """Show a preview card of the uploaded and extracted document."""
    if not st.session_state.pdf_text:
        return

    text   = st.session_state.pdf_text
    name   = st.session_state.pdf_name
    pages  = st.session_state.pdf_pages
    chars  = len(text)
    words  = len(text.split())

    st.markdown('<div class="uw-label" style="margin-top: 1.5rem;">Document Preview</div>', unsafe_allow_html=True)

    # Metadata row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("File", name[:22] + "…" if len(name) > 22 else name)
    with col2:
        st.metric("Pages", pages)
    with col3:
        st.metric("Words", f"{words:,}")
    with col4:
        st.metric("Characters", f"{chars:,}")

    # Text preview
    preview = truncate_for_preview(text)
    st.markdown(
        f'<div class="doc-preview">{preview}</div>',
        unsafe_allow_html=True,
    )


def render_analysis_trigger(client: Optional[DifyClient]) -> bool:
    """
    Render the analysis trigger button.
    Returns True if the user clicked it and we should begin analysis.
    """
    st.markdown("", unsafe_allow_html=True)  # spacer

    col1, col_gap, col2 = st.columns([2, 0.3, 1.5])
    with col1:
        can_run = (
            client is not None
            and st.session_state.pdf_text is not None
            and not st.session_state.is_analysing
        )
        clicked = st.button(
            "▶  Run Risk Analysis",
            disabled=not can_run,
            use_container_width=True,
            type="primary",
        )

    with col2:
        if not client:
            st.caption("⚠️ Connect to Dify to enable analysis.")
        elif not st.session_state.pdf_text:
            st.caption("Upload a PDF to begin.")
        elif st.session_state.is_analysing:
            st.caption("Analysis in progress…")
        else:
            st.caption(
                f"Agent will run up to 5 reasoning iterations "
                f"using {len(st.session_state.pdf_text):,} chars of document text."
            )

    return clicked


# Execute  analysis
def run_streaming_analysis(client: DifyClient):
    st.markdown("---")
    st.markdown('<div class="uw-label">Live Analysis Feed</div>', unsafe_allow_html=True)

    # The streaming output placeholder
    stream_placeholder = st.empty()
    full_text = ""

    # Progress indicator
    status_bar = st.status(
        "🤖 Agent initialising — parsing document…",
        expanded=True,
    )

    status_messages = [
        "🔍 Extracting entities from document…",
        "🌐 Running web reputation checks…",
        "📚 Cross-referencing policy compliance KB…",
        "⚖️  Synthesising risk factors…",
        "📋 Compiling Risk Memo…",
    ]
    status_idx = 0
    last_status_update = time.time()

    try:
        for chunk in client.stream_message(
            query=st.session_state.pdf_text,
            user_id=st.session_state.user_id,
        ):
            full_text += chunk

            stream_placeholder.markdown(
                f'<div class="memo-container">{full_text}</div>',
                unsafe_allow_html=True,
            )

            now = time.time()
            if now - last_status_update > 4 and status_idx < len(status_messages) - 1:
                status_idx += 1
                status_bar.update(label=status_messages[status_idx])
                last_status_update = now

        status_bar.update(label="✅ Analysis complete.", state="complete", expanded=False)

        st.session_state.memo_result    = full_text
        st.session_state.is_analysing   = False
        st.session_state.analysis_count += 1

#Exceptions
    except DifyAuthError as e:
        status_bar.update(label="❌ Authentication failed.", state="error", expanded=False)
        st.session_state.is_analysing  = False
        st.session_state.error_message = (
            f"**API Key Error:** {e}\n\n"
            "Check that `DIFY_API_KEY` in your `.env` is correct."
        )

    except DifyStreamError as e:
        status_bar.update(label="❌ Stream error.", state="error", expanded=False)
        st.session_state.is_analysing  = False
        st.session_state.error_message = (
            f"**Stream Error:** {e}\n\n"
            "The agent encountered an error mid-response. "
            "Check your Dify workflow configuration."
        )

    except DifyAPIError as e:
        status_bar.update(label="❌ API error.", state="error", expanded=False)
        st.session_state.is_analysing  = False
        st.session_state.error_message = f"**API Error:** {e}"

    except Exception as e:
        status_bar.update(label="❌ Unexpected error.", state="error", expanded=False)
        st.session_state.is_analysing = False
        st.session_state.error_message = (
            f"**Unexpected Error:** {e}\n\n"
            "Please check the console logs for details."
        )
        logger.exception("Unexpected error during streaming analysis")


#Render complete risk memo
def render_memo_result():
    if not st.session_state.memo_result:
        return

    st.markdown("---")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown('<div class="uw-label">Risk Assessment Memo</div>', unsafe_allow_html=True)
    with col2:
        # Download button
        st.download_button(
            label="⬇  Download Memo (.md)",
            data=st.session_state.memo_result.encode("utf-8"),
            file_name=f"risk_memo_{st.session_state.user_id[:8]}.md",
            mime="text/markdown",
            use_container_width=False,
        )

    st.markdown(
        f'<div class="memo-container">{st.session_state.memo_result}</div>',
        unsafe_allow_html=True,
    )

    # Re-run analysis button
    st.markdown("")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
        if st.button("↺  Re-analyse Document", use_container_width=True):
            st.session_state.memo_result = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

#Render placeholder
def render_empty_state():
    st.markdown(
        """
        <div class="uw-card" style="text-align: center; padding: 3rem 2rem; margin-top: 2rem; border-style: dashed;">
          <div style="font-size: 2.5rem; margin-bottom: 1rem;">📋</div>
          <div style="font-family: 'DM Serif Display', serif; font-size: 1.3rem;
                      color: #9CA3AF; margin-bottom: 0.5rem;">
            Ready for Assessment
          </div>
          <div style="font-size: 0.82rem; color: #4B5563; max-width: 380px; margin: 0 auto; line-height: 1.7;">
            Upload a business loan application or commercial insurance PDF
            to begin an autonomous AI risk assessment.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_error():
    """Display any pending error message from session state."""
    if st.session_state.error_message:
        st.error(st.session_state.error_message, icon="🚨")
        st.markdown('<div class="secondary-btn" style="width:fit-content">', unsafe_allow_html=True)
        if st.button("Clear Error"):
            st.session_state.error_message = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)



#Main app entrypoint

def main():
    #Inject CSS
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    init_session_state()

    #Load Dify client (cached)
    client = load_dify_client()

    render_sidebar(client)

    render_header()

    render_error()

    #Upload section
    pdf_bytes, pdf_name = render_upload_section()

    # Process uploaded file
    if pdf_bytes and pdf_name != st.session_state.pdf_name:
        with st.spinner("Extracting text from PDF…"):
            try:
                text, pages = extract_text_from_pdf(pdf_bytes)
                st.session_state.pdf_text    = text
                st.session_state.pdf_name    = pdf_name
                st.session_state.pdf_pages   = pages
                st.session_state.memo_result = None  # clear previous result
                st.session_state.error_message = None
                st.success(
                    f"✅ Extracted {len(text):,} characters from "
                    f"**{pdf_name}** ({pages} pages). Ready for analysis.",
                    icon="📄",
                )
            except ValueError as e:
                st.session_state.error_message = f"**PDF Extraction Error:** {e}"
                st.session_state.pdf_text = None
                st.rerun()

    # Show document preview if we have extracted text
    if st.session_state.pdf_text:
        render_document_preview()

    #Analysis trigger
    if not st.session_state.memo_result:
        clicked = render_analysis_trigger(client)

        if clicked:
            st.session_state.is_analysing = True
            st.session_state.error_message = None
            run_streaming_analysis(client)
            st.rerun()

    render_memo_result()

    if not st.session_state.pdf_text and not st.session_state.error_message:
        render_empty_state()


if __name__ == "__main__":
    main()
