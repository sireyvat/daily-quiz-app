"""
=====================================================================
 DAILY QUIZ WEB APP - MULTI-MODAL ASSESSMENT SYSTEM v3.1 (fixed)
 Streamlit + Google Sheets + Auto-refresh Timer
 
 FEATURES:
 ✅ Multi-Modal Support (MCQ, Writing, Listening, Speaking)
 ✅ Auto-refresh Timer (uses the REAL streamlit-autorefresh API)
 ✅ Safe Cache Clearing - prevents double-attempt bug
 ✅ Defensive Type Conversion - all sheet values wrapped
 ✅ Optional Roster/Attendance check - falls back to manual entry
    if no "Students" tab exists yet
 ✅ Matches your CURRENT "Questions" tab layout:
        Question | Options | Correct Answer  (or add "Type" column
        to unlock Writing/Listening/Speaking question types)

 FIXES APPLIED vs the previous draft:
 1. st.set_page_config() is now called EXACTLY ONCE (calling it
    twice crashed every quiz screen with a StreamlitAPIException).
 2. streamlit_autorefresh's real function is `st_autorefresh`, not
    `rerun_if_updated` (that name doesn't exist in the package, so
    the import always failed silently before).
 3. fetch_question_bank() now reads the "Options" column (matches
    your real sheet) instead of a nonexistent "Data/Options" column.
 4. Added `pytz` to requirements.txt (it was used but not declared).
 5. Fixed the f-string SyntaxError (backslash inside an f-string
    expression is illegal on Python <3.12) by pulling the color/label
    lookups into plain variables first.
 6. The "Students" roster tab is now OPTIONAL. If it doesn't exist,
    the app falls back to a manual Full Name + Class login (no
    attendance/daily-attempt lock), so it works with your sheet
    exactly as it is today.
=====================================================================
"""

import streamlit as st
import random
import uuid
from datetime import datetime
import pytz
from typing import List, Dict, Optional, Tuple

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

try:
    from streamlit_mic_recorder import mic_recorder
    MIC_RECORDER_AVAILABLE = True
except ImportError:
    MIC_RECORDER_AVAILABLE = False

# =====================================================================
# 1. PAGE CONFIG  (called exactly once, first Streamlit command)
# =====================================================================
st.set_page_config(
    page_title="ការលេងលើ",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Auto-refresh every 1 second while on the quiz screen, so the
# on-screen timers count down live without needing time.sleep().
# Uses the REAL streamlit-autorefresh API (st_autorefresh), and is a
# no-op if the package isn't installed — no second set_page_config
# call, ever.
if AUTOREFRESH_AVAILABLE and st.session_state.get("stage") == "quiz":
    st_autorefresh(interval=1000, key="quiz_timer_tick")

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

        div.stTextInput > div > div > input,
        div.stTextArea > div > div > textarea {
            padding: 0.7rem;
            border-radius: 10px;
            font-family: 'Arial', sans-serif;
        }

        div.stSelectbox > div > div {
            padding: 0.7rem;
            border-radius: 10px;
        }

        div.stProgress {
            margin-bottom: 1rem;
        }

        .feedback-correct {
            background-color: #d4edda;
            color: #155724;
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 0.8rem;
            border: 2px solid #28a745;
        }
        
        .feedback-incorrect {
            background-color: #f8d7da;
            color: #721c24;
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 0.8rem;
            border: 2px solid #dc3545;
        }

        .feedback-pending {
            background-color: #e2e3e5;
            color: #383d41;
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 0.8rem;
            border: 2px solid #6c757d;
        }
        
        .quiz-header {
            text-align: center;
            margin-bottom: 0.5rem;
            font-family: 'Khmer OS', 'Arial Unicode MS', sans-serif;
        }
        
        .timer-warning {
            background-color: #fff3cd;
            color: #856404;
            padding: 0.8rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 700;
            font-size: 1.05rem;
            margin-bottom: 1rem;
            border: 2px solid #ffc107;
        }
        
        .timer-critical {
            background-color: #f8d7da;
            color: #721c24;
            padding: 0.8rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 700;
            font-size: 1.05rem;
            margin-bottom: 1rem;
            border: 2px solid #dc3545;
            animation: pulse 0.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .access-denied {
            background-color: #f8d7da;
            color: #721c24;
            padding: 1.2rem;
            border-radius: 10px;
            border-left: 5px solid #dc3545;
            margin-top: 1rem;
            font-family: 'Khmer OS', 'Arial Unicode MS', sans-serif;
        }

        .success-box {
            background-color: #d4edda;
            color: #155724;
            padding: 1.2rem;
            border-radius: 10px;
            border-left: 5px solid #28a745;
            margin-top: 1rem;
            font-family: 'Khmer OS', 'Arial Unicode MS', sans-serif;
        }

        .question-type-badge {
            display: inline-block;
            background-color: #007bff;
            color: white;
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# =====================================================================
# 3. CONFIGURATION
# =====================================================================
SPREADSHEET_NAME = "Daily Quiz Results"
QUESTIONS_TAB = "Questions"
RESULTS_TAB = "Results"
STUDENTS_TAB = "Students"   # optional — app works fine without this tab

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GLOBAL_QUIZ_TIME = 900  # 15 minutes, in seconds
TIMEZONE = "Asia/Phnom_Penh"

# =====================================================================
# 4. GOOGLE SHEETS CONNECTION
# =====================================================================

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Get a cached, authorized gspread client from st.secrets.

    SETUP: Google Cloud Console -> enable Sheets + Drive API -> create
    a Service Account -> download its JSON key -> share your Google
    Sheet with the service account's "client_email" as Editor -> paste
    the JSON contents into Streamlit Secrets under [gcp_service_account].
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
        st.error(f"❌ មិនអាចភ្ជាប់ទៅ Google Sheets: {str(e)}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_question_bank() -> List[Dict]:
    """
    Fetch ALL questions from the "Questions" tab.

    Matches YOUR sheet layout:
        Question | Options | Correct Answer
    "Options" is a single comma-separated cell, e.g. "23, 25, 15, 26".

    Optionally, add a "Type" column (MCQ / WRITING / LISTENING /
    SPEAKING) to unlock other question types. If "Type" is missing or
    blank, every row defaults to MCQ (unchanged from your current
    sheet — no edits required).

    For LISTENING questions, put the audio URL in the "Options" cell
    instead of comma-separated choices.
    """
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(QUESTIONS_TAB)
        records = worksheet.get_all_records()
    except Exception:
        return []

    bank = []
    for row in records:
        try:
            question = str(row.get("Question", "")).strip()
            q_type = str(row.get("Type", "MCQ")).strip().upper()
            if not q_type:
                q_type = "MCQ"
            raw_cell = str(row.get("Options", "")).strip()
            correct_answer = str(row.get("Correct Answer", "")).strip()

            if not question:
                continue

            if q_type not in ["MCQ", "WRITING", "LISTENING", "SPEAKING"]:
                q_type = "MCQ"

            if q_type == "MCQ":
                options = [opt.strip() for opt in raw_cell.split(",") if opt.strip()]
                if len(options) < 2 or correct_answer not in options:
                    continue
                bank.append({
                    "question": question,
                    "type": q_type,
                    "options": options,
                    "answer": correct_answer,
                })
            elif q_type == "LISTENING":
                if not raw_cell:
                    continue
                bank.append({
                    "question": question,
                    "type": q_type,
                    "audio_url": raw_cell,
                    "answer": correct_answer,
                    "options": None,
                })
            else:  # WRITING or SPEAKING
                bank.append({
                    "question": question,
                    "type": q_type,
                    "answer": correct_answer if correct_answer else "Teacher Review",
                    "options": None,
                })
        except Exception:
            continue

    return bank


@st.cache_data(ttl=300, show_spinner=False)
def fetch_students_roster() -> List[Dict]:
    """Fetch the optional student roster from a 'Students' tab.
    Returns [] if the tab doesn't exist — this is expected and fine;
    the app falls back to manual login in that case."""
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(STUDENTS_TAB)
        records = worksheet.get_all_records()
    except Exception:
        return []

    roster = []
    for row in records:
        try:
            student_id = str(row.get("Student ID", "")).strip()
            full_name = str(row.get("Full Name", "")).strip()
            student_class = str(row.get("Class", "")).strip()
            status = str(row.get("Status", "")).strip()

            if student_id and full_name and student_class and status:
                roster.append({
                    "student_id": student_id,
                    "full_name": full_name,
                    "class": student_class,
                    "status": status,
                })
        except Exception:
            continue

    return roster


def fetch_today_results() -> List[Dict]:
    """Fetch today's rows from the Results tab (used for the optional
    'already attempted today' check when a Students roster is in use)."""
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(RESULTS_TAB)
        records = worksheet.get_all_records()
    except Exception:
        return []

    today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    today_results = []
    for row in records:
        try:
            timestamp = str(row.get("Timestamp", "")).strip()
            if timestamp.startswith(today):
                today_results.append(row)
        except Exception:
            continue

    return today_results


def log_result_to_sheet(student_id: str, student_name: str, student_class: str,
                         score: int, total: int) -> bool:
    """Append a result row to the Results tab.

    Auto-detects the existing header so it works whether your Results
    tab has 4 columns (Timestamp, Student Name, Class, Score — your
    current sheet) or 5 columns (...with Student ID added). If the
    Results tab doesn't exist yet, it's created with the 5-column
    layout including Student ID.
    """
    client = get_gspread_client()
    if client is None:
        return False

    try:
        sheet = client.open(SPREADSHEET_NAME)

        try:
            worksheet = sheet.worksheet(RESULTS_TAB)
            header = worksheet.row_values(1)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=RESULTS_TAB, rows="1000", cols="5")
            header = ["Timestamp", "Student ID", "Student Name", "Class", "Score"]
            worksheet.insert_row(header, 1)

        tz = pytz.timezone(TIMEZONE)
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        score_str = f"{score}/{total}"

        # Build the row to match whatever columns actually exist,
        # so we never misalign an existing 4-column sheet.
        if "Student ID" in header:
            row = ["" for _ in header]
            values = {
                "Timestamp": timestamp,
                "Student ID": student_id,
                "Student Name": student_name,
                "Class": student_class,
                "Score": score_str,
            }
            for col_name, val in values.items():
                if col_name in header:
                    row[header.index(col_name)] = val
            worksheet.append_row(row)
        else:
            # Your current 4-column layout: Timestamp, Student Name, Class, Score
            worksheet.append_row([timestamp, student_name, student_class, score_str])

        return True
    except Exception:
        return False


# =====================================================================
# 5. OPTIONAL AUTHORIZATION & VERIFICATION (only used if a Students
#    tab exists — otherwise login.py falls back to manual entry)
# =====================================================================

def verify_student_attendance(student_id: str) -> Tuple[bool, str, Optional[Dict]]:
    """Verify if student is 'Present' in the roster."""
    roster = fetch_students_roster()

    student_found = None
    for student in roster:
        if str(student["student_id"]).lower() == str(student_id).lower():
            student_found = student
            break

    if student_found is None:
        return False, f"❌ មិនរកឃើញលេខសម្គាល់ '{student_id}' នៅក្នុងបញ្ជីឈ្មោះ។", None

    status_lower = str(student_found["status"]).lower().strip()
    if status_lower != "present":
        return False, (
            f"⚠️ អ្នកមិនមាននៅលើបញ្ជីហៅឈ្មោះថ្ងៃនេះទេ។\n\n"
            f"📋 ស្ថានភាព៖ {student_found['status']}"
        ), None

    return True, "", student_found


def check_today_attempt(student_id: str) -> Tuple[bool, Optional[str]]:
    """Check if a student already tested today (roster mode only).
    fetch_today_results() is NOT cached, so it already reads the
    Results tab live on every call — no .clear() needed/possible."""
    today_results = fetch_today_results()

    for result in today_results:
        try:
            result_student_id = str(result.get("Student ID", "")).strip()
            if result_student_id and result_student_id.lower() == str(student_id).lower():
                score = str(result.get("Score", "")).strip()
                return False, score
        except Exception:
            continue

    return True, None


# =====================================================================
# 6. SESSION STATE MANAGEMENT
# =====================================================================

def init_session_state():
    if "session_token" not in st.session_state:
        st.session_state.session_token = str(uuid.uuid4())
        st.session_state.stage = "login"
        st.session_state.student_id = ""
        st.session_state.student_name = ""
        st.session_state.student_class = ""
        st.session_state.quiz_questions = []
        st.session_state.current_q_index = 0
        st.session_state.score = 0
        st.session_state.quiz_start_time = None
        st.session_state.question_start_time = None
        st.session_state.time_expired = False
        st.session_state.answers = {}
        st.session_state.logged = False


def prepare_quiz_questions() -> bool:
    """Prepare a randomized question set (uses the full bank as-is;
    reduce QUESTIONS_PER_ATTEMPT sampling here if you want to limit
    how many of your sheet's questions appear per attempt)."""
    full_bank = fetch_question_bank()

    if not full_bank:
        return False

    selected = random.sample(full_bank, len(full_bank))
    st.session_state.quiz_questions = selected
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    st.session_state.quiz_start_time = now
    st.session_state.question_start_time = now
    st.session_state.answers = {}
    return True


def get_remaining_times() -> Tuple[int, int, bool]:
    """Calculate remaining global and per-question time."""
    if st.session_state.quiz_start_time is None:
        return GLOBAL_QUIZ_TIME, 0, False

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    elapsed_global = (now - st.session_state.quiz_start_time).total_seconds()
    global_remaining = max(0, GLOBAL_QUIZ_TIME - elapsed_global)

    if global_remaining <= 0:
        return 0, 0, True

    total_questions = len(st.session_state.quiz_questions)
    if total_questions == 0:
        return int(global_remaining), 0, False

    per_question_limit = GLOBAL_QUIZ_TIME / total_questions
    elapsed_current = (now - st.session_state.question_start_time).total_seconds()
    per_question_remaining = max(0, per_question_limit - elapsed_current)

    return int(global_remaining), int(per_question_remaining), False


# =====================================================================
# 7. UI SCREENS
# =====================================================================

def render_login_screen():
    st.markdown("<h1 class='quiz-header'>🧠 ការលេងលើ</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666; font-family: \"Khmer OS\";'>"
        "ឆ្លើយសំណួរដើម្បីគាំងសមត្ថភាព។ សូមឈរឱ្យលម្អិត! 💪</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    roster = fetch_students_roster()

    if roster:
        # -------- Roster mode: select from list, verify attendance --------
        with st.form("login_form_roster", clear_on_submit=False):
            st.write("📋 **ជ្រើសរើសលេខសម្គាល់របស់អ្នក៖**")
            student_options = [
                f"{s['student_id']} - {s['full_name']} ({s['class']})"
                for s in roster
            ]
            selected_option = st.selectbox(
                "សិស្ស", options=student_options, label_visibility="collapsed"
            )
            student_id = selected_option.split(" - ")[0] if selected_option else ""

            submitted = st.form_submit_button("ចូលឆ្លើយសំណួរ 🚀", use_container_width=True)

            if submitted:
                if not student_id:
                    st.error("⚠️ សូមជ្រើសរើសលេខសម្គាល់។")
                    return

                is_authorized, error_msg, student_info = verify_student_attendance(student_id)
                if not is_authorized:
                    st.markdown(f"<div class='access-denied'>{error_msg}</div>", unsafe_allow_html=True)
                    return

                can_attempt, previous_score = check_today_attempt(student_id)
                if not can_attempt:
                    st.markdown(
                        f"<div class='access-denied'>"
                        f"⚠️ អ្នកបានលេងលើរួចហើយថ្ងៃនេះ។<br><br>"
                        f"📊 ពិន្ទុលើកមុន៖ <b>{previous_score}</b>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    return

                st.session_state.student_id = student_id
                st.session_state.student_name = student_info["full_name"]
                st.session_state.student_class = student_info["class"]
                _start_quiz_after_login()
    else:
        # -------- Fallback mode: no "Students" tab yet -> manual entry --------
        with st.form("login_form_manual", clear_on_submit=False):
            name = st.text_input("Full Name / ឈ្មោះពេញ", placeholder="e.g. Sophea Chan")
            student_class = st.text_input("Class / Grade / ថ្នាក់", placeholder="e.g. Grade 10A")
            submitted = st.form_submit_button("ចូលឆ្លើយសំណួរ 🚀", use_container_width=True)

            if submitted:
                if not name.strip() or not student_class.strip():
                    st.error("⚠️ សូមបំពេញឈ្មោះ និងថ្នាក់របស់អ្នក។")
                    return

                st.session_state.student_id = name.strip()  # no roster ID available
                st.session_state.student_name = name.strip()
                st.session_state.student_class = student_class.strip()
                _start_quiz_after_login()


def _start_quiz_after_login():
    with st.spinner("📥 កំពុងទាញយកសំណួរ..."):
        ok = prepare_quiz_questions()

    if not ok:
        st.error(
            "❌ មិនបានទាញយកសំណួរ។ សូមពិនិត្យមើលថា Sheet ឈ្មោះ 'Questions' "
            "មានជួរឈរ Question / Options / Correct Answer ត្រឹមត្រូវ។"
        )
        return

    st.session_state.stage = "quiz"
    st.rerun()


def render_quiz_screen():
    questions = st.session_state.quiz_questions

    if not questions:
        st.error("❌ មិនមានសំណួរ។ សូមចាប់ផ្តើមឡើងវិញ។")
        if st.button("🔄 ចាប់ផ្តើមឡើងវិញ"):
            st.session_state.stage = "login"
            st.rerun()
        return

    global_remaining, per_question_remaining, is_expired = get_remaining_times()

    if is_expired:
        score = 0
        for i, q in enumerate(questions):
            if i in st.session_state.answers and q["type"] == "MCQ":
                if st.session_state.answers[i] == q["answer"]:
                    score += 1
        st.session_state.score = score
        st.session_state.stage = "result"
        st.session_state.time_expired = True
        st.rerun()

    idx = st.session_state.current_q_index
    total = len(questions)

    col1, col2 = st.columns([1, 1])
    with col1:
        minutes, seconds = divmod(global_remaining, 60)
        if global_remaining <= 60:
            st.markdown(f"<div class='timer-critical'>⏱️ សរុប៖ {int(minutes)}:{int(seconds):02d}</div>", unsafe_allow_html=True)
        elif global_remaining <= 120:
            st.markdown(f"<div class='timer-warning'>⏱️ សរុប៖ {int(minutes)}:{int(seconds):02d}</div>", unsafe_allow_html=True)
        else:
            st.info(f"⏱️ សរុប៖ {int(minutes)}:{int(seconds):02d}")

    with col2:
        minutes, seconds = divmod(per_question_remaining, 60)
        st.caption(f"⏳ សំណួរ៖ {int(minutes)}:{int(seconds):02d}")

    st.progress(idx / total, text=f"សំណួរ {idx + 1} នៃ {total}")
    st.divider()

    q = questions[idx]
    q_type = q["type"]

    badge_colors = {"MCQ": "#007bff", "WRITING": "#28a745", "LISTENING": "#fd7e14", "SPEAKING": "#e83e8c"}
    badge_labels = {"MCQ": "ជ្រើសរើស", "WRITING": "សរសេរ", "LISTENING": "ស្តាប់", "SPEAKING": "និយាយ"}

    # No backslashes inside f-string expressions — resolve to plain
    # variables first (this is what caused the earlier SyntaxError).
    badge_color = badge_colors.get(q_type, "#007bff")
    badge_label = badge_labels.get(q_type, q_type)
    st.markdown(
        f"<span class='question-type-badge' style='background-color: {badge_color};'>{badge_label}</span>",
        unsafe_allow_html=True,
    )

    st.markdown(f"### {q['question']}")

    if q_type == "MCQ":
        render_mcq_question(q, idx)
    elif q_type == "WRITING":
        render_writing_question(q, idx)
    elif q_type == "LISTENING":
        render_listening_question(q, idx)
    elif q_type == "SPEAKING":
        render_speaking_question(q, idx)

    if idx in st.session_state.answers:
        col1, col2 = st.columns([1, 1])
        with col1:
            if idx > 0:
                if st.button("◀️ ក្រោយ", use_container_width=True):
                    st.session_state.current_q_index -= 1
                    st.rerun()
        with col2:
            if idx + 1 < total:
                if st.button("សំណួរបន្ទាប់ ▶️", use_container_width=True):
                    st.session_state.current_q_index += 1
                    tz = pytz.timezone(TIMEZONE)
                    st.session_state.question_start_time = datetime.now(tz)
                    st.rerun()
            else:
                if st.button("ឈប់លេង ✓", use_container_width=True):
                    st.session_state.stage = "result"
                    st.rerun()


def render_mcq_question(q: Dict, idx: int):
    if idx in st.session_state.answers:
        selected_answer = st.session_state.answers[idx]
        is_correct = selected_answer == q["answer"]
        if is_correct:
            st.markdown("<div class='feedback-correct'>✅ ត្រឹមត្រូវ!</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div class='feedback-incorrect'>❌ មិនត្រឹមត្រូវ។ ចម្លើយត្រឹមត្រូវ៖ <b>{q['answer']}</b></div>",
                unsafe_allow_html=True,
            )
    else:
        st.write("**ជ្រើសរើសចម្លើយមួយ៖**")
        for option in q["options"]:
            if st.button(option, key=f"opt_{idx}_{option}", use_container_width=True):
                st.session_state.answers[idx] = option
                st.rerun()


def render_writing_question(q: Dict, idx: int):
    if idx in st.session_state.answers:
        st.markdown("<div class='feedback-pending'>📝 ចម្លើយរបស់អ្នក៖ (គ្រូនឹងវាយតម្លៃ)</div>", unsafe_allow_html=True)
        st.text_area("ចម្លើយរបស់អ្នក:", value=st.session_state.answers[idx], disabled=True)
    else:
        st.write("**សូមសរសេរចម្លើយលម្អិត៖**")
        answer_text = st.text_area(
            "ចម្លើយ", placeholder="សូមសរសេរចម្លើយលម្អិត...", height=150, label_visibility="collapsed"
        )
        if answer_text.strip():
            if st.button("រក្សាទុក ✓", use_container_width=True):
                st.session_state.answers[idx] = answer_text.strip()
                st.rerun()


def render_listening_question(q: Dict, idx: int):
    audio_url = q.get("audio_url", "")
    if audio_url:
        st.write("**ស្តាប់ឯកសារ៖**")
        st.audio(audio_url)
    else:
        st.warning("⚠️ មិនរកឃើញឯកសារជម្រើស។")

    st.write("**សូមឆ្លើយសំណួរខាងលើ៖**")
    if idx in st.session_state.answers:
        st.markdown("<div class='feedback-pending'>📝 ចម្លើយរបស់អ្នក៖ (គ្រូនឹងវាយតម្លៃ)</div>", unsafe_allow_html=True)
        st.text_area("ចម្លើយរបស់អ្នក:", value=st.session_state.answers[idx], disabled=True)
    else:
        answer_text = st.text_area(
            "ចម្លើយ", placeholder="សូមសរសេរចម្លើយ...", height=100, label_visibility="collapsed"
        )
        if answer_text.strip():
            if st.button("រក្សាទុក ✓", use_container_width=True):
                st.session_state.answers[idx] = answer_text.strip()
                st.rerun()


def render_speaking_question(q: Dict, idx: int):
    if idx in st.session_state.answers:
        st.markdown("<div class='feedback-pending'>🎤 ឯកសារថ្នល់របស់អ្នក៖ (គ្រូនឹងវាយតម្លៃ)</div>", unsafe_allow_html=True)
        st.info("✅ ចម្លើយបានរក្សាទុក។ សូមបន្តទៅសំណួរបន្ទាប់។")
    else:
        st.write("**សូមឆ្លើយចម្លើយ៖**")
        if MIC_RECORDER_AVAILABLE:
            try:
                audio_data = mic_recorder(
                    start_prompt="🎤 ចាប់ផ្តើមថ្នល់",
                    stop_prompt="⏹️ ឈប់ថ្នល់",
                    just_once=False,
                    use_container_width=True,
                    key=f"mic_{idx}",
                )
                if audio_data is not None:
                    st.success("✅ ឯកសារបានថ្នល់។ សូមរក្សាទុក។")
                    if st.button("រក្សាទុក ✓", use_container_width=True):
                        st.session_state.answers[idx] = "[AUDIO_RECORDED]"
                        st.rerun()
            except Exception as e:
                st.warning(f"⚠️ មិនអាចថ្នល់សំឡេង៖ {str(e)}")
        else:
            st.info("🎤 mic-recorder មិនត្រូវបានដំឡើងទេ — សូមសរសេរចម្លើយជំនួសវិញ។")
            answer_text = st.text_area(
                "ចម្លើយ", placeholder="សូមសរសេរចម្លើយ...", height=100, label_visibility="collapsed"
            )
            if answer_text.strip():
                if st.button("រក្សាទុក ✓", use_container_width=True):
                    st.session_state.answers[idx] = answer_text.strip()
                    st.rerun()


def render_result_screen():
    questions = st.session_state.quiz_questions
    total = len(questions)

    score = 0
    for i, q in enumerate(questions):
        if i in st.session_state.answers and q["type"] == "MCQ":
            if st.session_state.answers[i] == q["answer"]:
                score += 1
    st.session_state.score = score

    st.balloons()
    st.markdown("<h1 class='quiz-header'>🎉 រៀបចំលើរួច!</h1>", unsafe_allow_html=True)

    time_expired_msg = ""
    if st.session_state.get("time_expired", False):
        time_expired_msg = (
            "<p style='color:#d32f2f; font-weight:600; font-family: \"Khmer OS\";'>"
            "⏰ អស់ពេល។ លទ្ធផលត្រូវបានរំលឹក។</p>"
        )

    st.markdown(
        f"""
        <div style='text-align:center; padding: 1.5rem; background:#f0f2f6;
                    border-radius: 14px; margin-top: 1rem;'>
            <p style='font-size:1.1rem; margin-bottom:0.3rem; font-family: "Khmer OS";'>
                {st.session_state.student_name} ({st.session_state.student_class})
            </p>
            <p style='font-size:2.2rem; font-weight:700; margin:0;'>
                {score} / {total}
            </p>
            {time_expired_msg}
            <p style='font-size:0.9rem; color:#666; margin-top:0.5rem; font-family: "Khmer OS";'>
                (សំណួរសរសេរ ឬ ថ្នល់នឹងវាយតម្លៃដោយគ្រូ)
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.logged:
        success = log_result_to_sheet(
            st.session_state.student_id,
            st.session_state.student_name,
            st.session_state.student_class,
            score,
            total,
        )
        st.session_state.logged = True
        if success:
            st.markdown("<div class='success-box'>✅ លទ្ធផលបានរក្សាទុក។ សូមបិទបង្អួច។</div>", unsafe_allow_html=True)
        else:
            st.warning(f"⚠️ មិនបានរក្សាទុកទេ។ សូមប្រាប់គ្រូ៖ {score}/{total}")
    else:
        st.markdown("<div class='success-box'>✅ លទ្ធផលបានរក្សាទុក។</div>", unsafe_allow_html=True)

    st.divider()
    st.caption(
        "💡 ប្រសិនបើលោកអ្នកបើក link ឡើងវិញ វានឹងចាប់ផ្តើមការធ្វើតេស្តថ្មីមួយ។"
    )


# =====================================================================
# 8. MAIN APP
# =====================================================================

def main():
    init_session_state()
    stage = st.session_state.get("stage", "login")

    if stage == "login":
        render_login_screen()
    elif stage == "quiz":
        render_quiz_screen()
    elif stage == "result":
        render_result_screen()
    else:
        st.session_state.stage = "login"
        st.rerun()


if __name__ == "__main__":
    main()
