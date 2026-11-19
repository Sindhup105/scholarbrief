import streamlit as st
import re
import os
from datetime import datetime

# ---------- Third-party libraries ----------
from spellchecker import SpellChecker
try:
    from fastlangml import FastLangDetector
    LANG_DETECTOR_AVAILABLE = True
except ImportError:
    LANG_DETECTOR_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ============================================================
# 1. Page configuration and title
# ============================================================
st.set_page_config(
    page_title="ScholarBrief",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 2. Session state initialization
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "search_history" not in st.session_state:
    st.session_state.search_history = []

if "welcome_shown" not in st.session_state:
    st.session_state.welcome_shown = True


# ============================================================
# 3. Core tools initialization
# ============================================================
@st.cache_resource
def init_spell_checker():
    """Initialize English spell checker"""
    return SpellChecker()

@st.cache_resource
def init_lang_detector():
    """Initialize language detector (supports Hinglish mixed language)"""
    if LANG_DETECTOR_AVAILABLE:
        return FastLangDetector()
    return None

@st.cache_resource
def init_openai():
    """Initialize OpenAI client (prioritize environment variable, then sidebar input)"""
    api_key = os.environ.get("OPENAI_API_KEY") or st.session_state.get("openai_api_key")
    if api_key and OPENAI_AVAILABLE:
        return OpenAI(api_key=api_key)
    return None


spell = init_spell_checker()
detector = init_lang_detector()


# ============================================================
# 4. Preprocessing functions (typo correction + language detection)
# ============================================================
ABBREVIATIONS = {
    "plz": "please", "pls": "please", "thx": "thanks", "tnx": "thanks",
    "diff": "difference", "def": "definition", "eg": "example",
    "ml": "machine learning", "ai": "artificial intelligence",
    "soln": "solution", "prob": "problem", "q": "question",
    "ans": "answer", "wat": "what", "hw": "how",
    "doubt": "doubt", "dbt": "doubt",
}

def correct_spelling(text: str) -> str:
    """Correct spelling errors in English text, preserving original case style"""
    words = text.split()
    corrected = []
    for word in words:
        # Skip short words and pure numbers
        if len(word) <= 3 or word.isdigit():
            corrected.append(word)
            continue
        # Remove punctuation and check
        clean = re.sub(r'[^\w]', '', word)
        if not clean:
            corrected.append(word)
            continue
        misspelled = spell.unknown([clean])
        if misspelled:
            suggestion = spell.correction(clean)
            if suggestion:
                # Keep punctuation prefix/suffix
                prefix = word[:word.find(clean)] if clean in word else ""
                suffix = word[word.find(clean)+len(clean):] if clean in word else ""
                corrected.append(prefix + suggestion + suffix)
            else:
                corrected.append(word)
        else:
            corrected.append(word)
    return " ".join(corrected)

def detect_language(text: str) -> str:
    """Detect user input language, return language code"""
    if detector:
        result = detector.detect(text)
        return result.language_code if hasattr(result, 'language_code') else "en"
    # Simple fallback: if contains Hindi/Devanagari characters, consider Hindi
    if re.search(r'[\u0900-\u097F]', text):
        return "hi"
    return "en"

def prepare_query(raw: str) -> str:
    """Full preprocessing pipeline: normalization → abbreviation expansion → spell correction"""
    q = raw.lower().strip()
    q = re.sub(r'\s+', ' ', q)
    # Expand abbreviations
    for abbr, full in ABBREVIATIONS.items():
        q = re.sub(r'\b' + re.escape(abbr) + r'\b', full, q)
    # Spell correction
    q = correct_spelling(q)
    return q


# ============================================================
# 5. System prompt (core constraint for ScholarBrief)
# ============================================================
SYSTEM_PROMPT = """You are ScholarBrief, an academic doubt assistant for students.

YOUR THREE CORE RULES:
1. BE BRIEF. Answer directly. Do NOT use preambles like "Great question" or "Let me explain."
   - Simple factual questions: 1-2 sentences only.
   - "Explain" questions: max 4 sentences.
   - Never restate the question.
2. BE TRUE. If you are not confident, say "I'm not sure about this. Please check with your teacher or textbook."
   Never guess or fabricate an answer.
3. MATCH THE USER'S LANGUAGE. If the user writes in English, answer in English.
   If the user writes in Hindi/Hinglish, answer in the same style.

FORMAT: First sentence = the answer. No lists unless genuinely necessary.
"""


# ============================================================
# 6. Sidebar: brand + search history
# ============================================================
with st.sidebar:
    st.markdown("### 📘 ScholarBrief")
    st.caption("*Learn with ease, answers that please. Brief and true, made for you.*")
    st.divider()
    
    # API key input
    if not os.environ.get("OPENAI_API_KEY"):
        st.markdown("**🔑 API Settings**")
        api_key = st.text_input("OpenAI API Key", type="password", 
                                 placeholder="sk-...",
                                 key="api_key_input")
        if api_key:
            st.session_state.openai_api_key = api_key
            st.success("Key saved for this session.")
        st.divider()
    
    # Search history
    st.markdown("**🕒 Recent Doubts**")
    if st.session_state.search_history:
        for i, item in enumerate(st.session_state.search_history[:10]):
            label = item["query"][:28] + ("..." if len(item["query"]) > 28 else "")
            if st.button(f"🔍 {label}", key=f"hist_{i}", use_container_width=True):
                st.session_state.pending_query = item["query"]
                st.rerun()
    else:
        st.caption("No doubts asked yet.")
    
    st.divider()
    if st.button("🗑️ Clear History", use_container_width=True):
        st.session_state.search_history = []
        st.session_state.messages = []
        st.rerun()


# ============================================================
# 7. Main area: welcome screen or chat interface
# ============================================================
if not st.session_state.messages and "pending_query" not in st.session_state:
    # ---------- Welcome screen ----------
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center;">
            <h1 style="font-size: 3.2em; margin-bottom: 0.2em;">📘 ScholarBrief</h1>
            <p style="font-size: 1.4em; font-style: italic; color: #555;">
                Learn with ease, answers that please.<br>
                Brief and true, made for you.
            </p>
            <br>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background-color: #f0f4f8; padding: 1.2em; border-radius: 10px; border-left: 5px solid #4a7c9b;">
            <b>💡 Quick tip:</b> Type your doubt naturally — spelling mistakes are okay. 
            I'll try to understand and keep the answer <b>short</b>, <b>clear</b>, and <b>honest</b>.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Chat input on welcome screen
        welcome_input = st.chat_input("Type your doubt here...")
        if welcome_input:
            st.session_state.pending_query = welcome_input
            st.rerun()

else:
    # ---------- Chat interface ----------
    # Welcome title at top
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1em;">
        <h2 style="margin: 0;">📘 ScholarBrief</h2>
        <p style="font-style: italic; color: #777; margin: 0;">
            Learn with ease, answers that please. Brief and true, made for you.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Chat input
    user_input = st.chat_input("Ask another doubt...")
    
    # Handle query (from either welcome screen or chat input)
    query_to_process = None
    if "pending_query" in st.session_state:
        query_to_process = st.session_state.pending_query
        del st.session_state.pending_query
    elif user_input:
        query_to_process = user_input
    
    if query_to_process:
        # 1. Preprocess
        cleaned = prepare_query(query_to_process)
        lang = detect_language(cleaned)
        lang_names = {"en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French"}
        lang_display = lang_names.get(lang, lang)
        
        # 2. Save search history (save original question)
        st.session_state.search_history.insert(0, {
            "query": query_to_process,
            "time": datetime.now().isoformat()
        })
        st.session_state.search_history = st.session_state.search_history[:20]
        
        # 3. Display user message
        with st.chat_message("user"):
            st.markdown(query_to_process)
        st.session_state.messages.append({"role": "user", "content": query_to_process})
        
        # 4. Generate answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking briefly..."):
                api_key = os.environ.get("OPENAI_API_KEY") or st.session_state.get("openai_api_key")
                
                if not api_key:
                    answer = "⚠️ Please enter your OpenAI API Key in the sidebar to use ScholarBrief."
                else:
                    try:
                        client = OpenAI(api_key=api_key)
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": f"[User language: {lang_display}] {cleaned}"}
                            ],
                            temperature=0.3,
                            max_tokens=250,
                        )
                        answer = response.choices[0].message.content.strip()
                        
                        # Post-processing: if answer is clearly too long, truncate
                        sentences = re.split(r'(?<=[.!?])\s+', answer)
                        if len(sentences) > 6:
                            answer = " ".join(sentences[:5]) + " ...(answer shortened for brevity)"
                            
                    except Exception as e:
                        answer = f"⚠️ Something went wrong: {str(e)[:100]}"
                
                st.markdown(answer)
        
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()
