"""
=====================================================================
 DAILY QUIZ WEB APP  -  Streamlit + Google Sheets + Telegram Mini App
=====================================================================
Author  : Claude (Anthropic)
Purpose : A mobile-friendly quiz app, opened inside a Telegram Group
          as a Web App link (Telegram Mini App).

Version 2 changes
------------------
- Questions are NO LONGER hardcoded. They are fetched live from a
  Google Sheet worksheet named "Questions".
- Results are appended to a separate worksheet named "Results" in
  the SAME spreadsheet.
- A single gspread service account connection (cached) is reused for
  both reading questions and writing results.
- Question fetching is cached with @st.cache_data(ttl=60) so rapid
  button clicks within the same quiz don't re-hit the Sheets API,
  while still refreshing at most once a minute so new/edited
  questions show up for new attempts without a redeploy.

Google Sheet structure required
--------------------------------
Spreadsheet name: "Daily Quiz Results"  (change SPREADSHEET_NAME below
to match yours)

Tab 1 - "Questions"
    Row 1 (header): Question | Options | Correct Answer
    Row 2+: one question per row.
      - "Options" holds ALL choices in a single cell, comma-separated,
        e.g.:  23, 25, 15, 26
      - "Correct Answer" must exactly match (after trimming spaces)
        one of the values inside "Options".
    Any number of options per question is fine (2, 3, 4, 5...) since
    they're simply split on commas.

Tab 2 - "Results"
    Row 1 (header): Timestamp | Student Name | Class | Score
    The app only appends rows here; you don't need to pre-fill it
    beyond the header row.

Run locally:
    streamlit run app.py
=====================================================================
"""

import streamlit as st
import random
import time
import uuid
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


# =====================================================================
# 1. PAGE CONFIG  (must be the first Streamlit command)
# =====================================================================
st.set_page_config(
    page_title="Daily Quiz",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =====================================================================
# 2. MOBILE-FIRST CSS
# =====================================================================
st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 480px;
        }

        div.stButton > button {
            width: 100%;
            padding: 0.9rem 0.5rem;
            font-size: 1.05rem;
            border-radius: 12px;
            margin-bottom: 0.5rem;
            border: 1px solid #dcdcdc;
        }

        div.stTextInput > div > div > input {
            padding: 0.7rem;
            border-radius: 10px;
        }

        div.stProgress {
            margin-bottom: 1rem;
        }

        .feedback-correct {
            background-color: #d4edda;
            color: #155724;
            padding: 0.9rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 0.6rem;
        }
        .feedback-incorrect {
            background-color: #f8d7da;
            color: #721c24;
            padding: 0.9rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 0.6rem;
        }
        .quiz-header {
            text-align: center;
            margin-bottom: 0.5rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# 3. CONFIG — change these to match your Google Sheet
# =====================================================================
SPREADSHEET_NAME = "Daily Quiz Results"   # <-- your Google Sheet's name
QUESTIONS_TAB = "Questions"               # <-- tab with the question bank
RESULTS_TAB = "Results"                   # <-- tab to log student scores
QUESTIONS_PER_ATTEMPT = 3

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# =====================================================================
# 4. GOOGLE SHEETS CONNECTION (cached — one client per app lifetime)
# =====================================================================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """
    Builds and caches an authorized gspread client from the service
    account credentials stored in Streamlit secrets.

    SETUP INSTRUCTIONS:
    --------------------------------------------------------------
    1. Go to https://console.cloud.google.com/ and create a project.
    2. Enable the "Google Sheets API" and "Google Drive API".
    3. Create a Service Account -> generate a JSON key file.
    4. Share your Google Sheet (both tabs live in the SAME sheet)
       with the service account's email (the "client_email" field
       inside the JSON key), giving it "Editor" access.
    5. In Streamlit Community Cloud: App -> Settings -> Secrets, paste:

           [gcp_service_account]
           type = "service_account"
           project_id = "..."
           private_key_id = "..."
           private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
           client_email = "...@....iam.gserviceaccount.com"
           client_id = "..."
           token_uri = "https://oauth2.googleapis.com/token"

       (For local testing, put the same block in .streamlit/secrets.toml)
    --------------------------------------------------------------
    Returns None if gspread isn't installed or secrets aren't configured,
    so the rest of the app can degrade gracefully instead of crashing.
    """
    if not GSPREAD_AVAILABLE:
        return None
    if "gcp_service_account" not in st.secrets:
        return None

    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Failed to authorize Google Sheets client: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_question_bank():
    """
    Reads every row from the "Questions" worksheet and returns a list
    of dicts:
        {"question": str, "options": [opt1, opt2, ...], "answer": str}

    Matches THIS sheet layout exactly:
        Column A: Question
        Column B: Options        <- comma-separated, e.g. "23, 25, 15, 26"
        Column C: Correct Answer <- must match one of the split options

    The number of options per question is flexible (2, 3, 4, 5...) since
    they're just split on commas — it doesn't have to be exactly 4.

    Cached for 60 seconds (ttl=60) so:
    - Rapid reruns during a single quiz (e.g. clicking an answer)
      don't re-hit the Sheets API.
    - Edits made to the Questions tab (add/remove/change questions)
      are picked up automatically within a minute for any NEW
      attempt, with no redeploy needed.

    Returns an empty list on any failure — callers must handle that.
    """
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(QUESTIONS_TAB)
        records = worksheet.get_all_records()  # list of dicts keyed by header row
    except Exception as e:
        st.session_state["_fetch_error"] = str(e)
        return []

    bank = []
    for row in records:
        try:
            question_text = str(row["Question"]).strip()
            options_raw = str(row["Options"])
            answer = str(row["Correct Answer"]).strip()
        except KeyError:
            # Row/header mismatch — skip malformed row instead of crashing.
            continue

        # Split the single "Options" cell on commas into a clean list,
        # e.g. "23, 25, 15, 26" -> ["23", "25", "15", "26"]
        options = [opt.strip() for opt in options_raw.split(",") if opt.strip() != ""]

        # Skip incomplete/malformed rows: blank question, fewer than 2
        # options, or an answer that doesn't exactly match one of them.
        if not question_text or len(options) < 2 or answer not in options:
            continue

        bank.append({
            "question": question_text,
            "options": options,
            "answer": answer,
        })

    return bank


def log_result_to_sheet(student_name: str, student_class: str, score: int, total: int) -> bool:
    """Appends [Timestamp, Student Name, Class, Score] to the 'Results' tab."""
    client = get_gspread_client()
    if client is None:
        return False

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(RESULTS_TAB)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([timestamp, student_name, student_class, f"{score}/{total}"])
        return True
    except Exception as e:
        st.error(f"Could not save your result to Google Sheets. (Error: {e})")
        return False


# =====================================================================
# 5. ANTI-CHEAT / SESSION MANAGEMENT
#
#    Every fresh visit gets a unique "session_token" stored both in
#    st.session_state AND in the URL query params. If they don't
#    match (hard refresh wiped session_state, but the old URL still
#    carries the old sid), we treat it as a NEW attempt: fresh
#    questions re-fetched from the sheet, score reset to zero.
# =====================================================================
def start_new_attempt():
    """Resets all quiz state and pulls a fresh randomized question set
    live from the Google Sheet."""
    new_token = str(uuid.uuid4())

    st.session_state.session_token = new_token
    st.session_state.stage = "login"          # login -> quiz -> result
    st.session_state.student_name = ""
    st.session_state.student_class = ""
    st.session_state.current_q_index = 0
    st.session_state.score = 0
    st.session_state.answered_current = False
    st.session_state.last_answer_correct = None
    st.session_state.logged = False
    st.session_state.quiz_questions = []       # filled in once student logs in

    st.query_params["sid"] = new_token


def prepare_quiz_questions():
    """
    Fetches the live question bank from the Google Sheet, randomly
    picks QUESTIONS_PER_ATTEMPT questions, and shuffles each
    question's options. Called once, right after login.
    """
    full_bank = fetch_question_bank()

    if not full_bank:
        st.session_state.quiz_questions = []
        return False

    n = min(QUESTIONS_PER_ATTEMPT, len(full_bank))
    selected = random.sample(full_bank, n)

    prepared = []
    for q in selected:
        opts = q["options"][:]
        random.shuffle(opts)
        prepared.append({
            "question": q["question"],
            "options": opts,
            "answer": q["answer"],
        })

    st.session_state.quiz_questions = prepared
    return True


def ensure_valid_session():
    """Called at the top of every rerun. Detects refresh/reopen and
    forces a brand-new attempt when needed."""
    url_sid = st.query_params.get("sid", None)

    if "session_token" not in st.session_state:
        start_new_attempt()
    else:
        if url_sid != st.session_state.session_token:
            start_new_attempt()


# =====================================================================
# 6. UI SCREENS
# =====================================================================
def render_login_screen():
    st.markdown("<h1 class='quiz-header'>🧠 Daily Quiz</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666;'>Answer a few quick questions. "
        "Good luck!</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.form("login_form", clear_on_submit=False):
        name = st.text_input("Full Name", placeholder="e.g. Sophea Chan")
        student_class = st.text_input("Class / Grade", placeholder="e.g. Grade 10A")
        submitted = st.form_submit_button("Start Quiz 🚀", use_container_width=True)

        if submitted:
            if not name.strip() or not student_class.strip():
                st.error("Please fill in both your Full Name and Class/Grade.")
                return

            with st.spinner("Fetching today's questions..."):
                ok = prepare_quiz_questions()

            if not ok:
                st.error(
                    "Couldn't load questions right now. Please check that the "
                    "'Questions' worksheet is set up correctly, or try again "
                    "in a moment."
                )
                return

            st.session_state.student_name = name.strip()
            st.session_state.student_class = student_class.strip()
            st.session_state.stage = "quiz"
            st.rerun()


def render_quiz_screen():
    questions = st.session_state.quiz_questions

    if not questions:
        st.error("No questions are loaded for this attempt. Please restart.")
        if st.button("Restart"):
            start_new_attempt()
            st.rerun()
        return

    idx = st.session_state.current_q_index
    total = len(questions)

    st.progress(idx / total, text=f"Question {idx + 1} of {total}")

    q = questions[idx]
    st.markdown(f"### {q['question']}")

    if not st.session_state.answered_current:
        for option in q["options"]:
            if st.button(option, key=f"opt_{idx}_{option}", use_container_width=True):
                is_correct = option == q["answer"]
                st.session_state.answered_current = True
                st.session_state.last_answer_correct = is_correct
                if is_correct:
                    st.session_state.score += 1
                st.rerun()
    else:
        for option in q["options"]:
            st.button(
                option,
                key=f"opt_disabled_{idx}_{option}",
                use_container_width=True,
                disabled=True,
            )

        if st.session_state.last_answer_correct:
            st.markdown(
                "<div class='feedback-correct'>✅ Correct!</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='feedback-incorrect'>❌ Incorrect. "
                f"Correct answer: <b>{q['answer']}</b></div>",
                unsafe_allow_html=True,
            )

        time.sleep(1)

        if idx + 1 < total:
            st.session_state.current_q_index += 1
            st.session_state.answered_current = False
            st.session_state.last_answer_correct = None
        else:
            st.session_state.stage = "result"

        st.rerun()


def render_result_screen():
    score = st.session_state.score
    total = len(st.session_state.quiz_questions)

    st.balloons()
    st.markdown("<h1 class='quiz-header'>🎉 Quiz Complete!</h1>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style='text-align:center; padding: 1.2rem; background:#f0f2f6;
                    border-radius: 14px; margin-top: 1rem;'>
            <p style='font-size:1.1rem; margin-bottom:0.3rem;'>
                {st.session_state.student_name} ({st.session_state.student_class})
            </p>
            <p style='font-size:2.2rem; font-weight:700; margin:0;'>
                {score} / {total}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.logged:
        success = log_result_to_sheet(
            st.session_state.student_name,
            st.session_state.student_class,
            score,
            total,
        )
        st.session_state.logged = True
        if success:
            st.success("✅ Your score has been recorded. You may close this window.")
        else:
            st.info(
                "Your score was calculated, but could not be saved automatically. "
                "Please inform your teacher of your score above."
            )
    else:
        st.success("✅ Your score has been recorded. You may close this window.")

    st.divider()
    st.caption(
        "Note: Refreshing or reopening this link will start a brand-new "
        "quiz attempt with new random questions — your previous score "
        "stays recorded."
    )


# =====================================================================
# 7. MAIN APP FLOW
# =====================================================================
def main():
    ensure_valid_session()

    stage = st.session_state.get("stage", "login")

    if stage == "login":
        render_login_screen()
    elif stage == "quiz":
        render_quiz_screen()
    elif stage == "result":
        render_result_screen()
    else:
        start_new_attempt()
        st.rerun()


if __name__ == "__main__":
    main()
