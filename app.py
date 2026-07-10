"""
=====================================================================
 DAILY QUIZ WEB APP - PRODUCTION GRADE
 Streamlit + Google Sheets + Mobile-First UI
 
 Features:
 ✅ Dynamic Question Bank (unlimited questions)
 ✅ Roster Verification & Attendance Enforcement
 ✅ Once-a-Day Attempt Restriction
 ✅ Global 15-Minute Timer + Per-Question Speed Allocation
 ✅ Auto-Submission on Timeout
 ✅ Khmer Language UI
 ✅ Production-Grade Error Handling
=====================================================================
"""

import streamlit as st
import random
import uuid
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional, Tuple

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# =====================================================================
# 1. PAGE CONFIG
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
        
        .timer-warning {
            background-color: #fff3cd;
            color: #856404;
            padding: 0.7rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: 1rem;
            animation: pulse 1s infinite;
        }
        
        .timer-critical {
            background-color: #f8d7da;
            color: #721c24;
            padding: 0.7rem;
            border-radius: 10px;
            text-align: center;
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: 1rem;
            animation: pulse 0.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        .access-denied {
            background-color: #f8d7da;
            color: #721c24;
            padding: 1.2rem;
            border-radius: 10px;
            border-left: 4px solid #f5c6cb;
            margin-top: 1rem;
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
STUDENTS_TAB = "Students"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Quiz timing (in seconds)
GLOBAL_QUIZ_TIME = 900  # 15 minutes
TIMEZONE = "Asia/Bangkok"  # Cambodia timezone

# =====================================================================
# 4. GOOGLE SHEETS CONNECTION (CACHED)
# =====================================================================

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Get cached gspread client."""
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
        st.error(f"❌ មិនបានផ្ទៀងផ្ទាត់ Google Sheets: {str(e)}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_question_bank() -> List[Dict]:
    """Fetch ALL questions from the Questions tab."""
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(QUESTIONS_TAB)
        records = worksheet.get_all_records()
    except Exception as e:
        st.session_state._fetch_error = str(e)
        return []

    bank = []
    for idx, row in enumerate(records, start=2):
        try:
            question = str(row.get("Question", "")).strip()
            options_raw = str(row.get("Options", ""))
            answer = str(row.get("Correct Answer", "")).strip()

            if not question or not options_raw.strip():
                continue

            options = [opt.strip() for opt in options_raw.split(",") if opt.strip()]

            if len(options) < 2 or answer not in options:
                continue

            bank.append({
                "question": question,
                "options": options,
                "answer": answer,
            })
        except Exception:
            continue

    return bank


@st.cache_data(ttl=300, show_spinner=False)
def fetch_students_roster() -> List[Dict]:
    """Fetch student roster from Students tab."""
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(STUDENTS_TAB)
        records = worksheet.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        return []
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


@st.cache_data(ttl=60, show_spinner=False)
def fetch_today_results() -> List[Dict]:
    """Fetch today's results from Results tab."""
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
    """Log quiz result to Results tab."""
    client = get_gspread_client()
    if client is None:
        return False

    try:
        sheet = client.open(SPREADSHEET_NAME)
        
        try:
            worksheet = sheet.worksheet(RESULTS_TAB)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=RESULTS_TAB, rows="1000", cols="5")
            worksheet.insert_row(["Timestamp", "Student ID", "Student Name", "Class", "Score"], 1)

        tz = pytz.timezone(TIMEZONE)
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([timestamp, student_id, student_name, student_class, f"{score}/{total}"])
        return True
    except Exception:
        return False


# =====================================================================
# 5. AUTHORIZATION & VERIFICATION LOGIC
# =====================================================================

def verify_student_attendance(student_id: str) -> Tuple[bool, str]:
    """
    Verify if student is present in roster and marked as Present.
    Returns: (is_authorized, message)
    """
    roster = fetch_students_roster()
    
    if not roster:
        return False, "❌ មិនបានលើក Roster ឡើងវិញ។ សូមព្យាយាមវិញ។"
    
    student_found = None
    for student in roster:
        if student["student_id"].lower() == student_id.lower():
            student_found = student
            break
    
    if student_found is None:
        return False, f"❌ មិនរកឃើញ Student ID '{student_id}' នៅក្នុង Roster។"
    
    if student_found["status"].lower() != "present":
        return False, (
            f"⚠️ អ្នកមិនមានសិទ្ធិចូលធ្វើតេស្តទេ។\n\n"
            f"📋 ស្ថានភាព: {student_found['status']}\n"
            f"⚠️ សូមស្វាគមន៍ក្រូ ឬ រិទ្ធិយាបាលបិទ។"
        )
    
    return True, ""


def check_today_attempt(student_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if student has already taken quiz today.
    Returns: (can_attempt, previous_score_or_none)
    """
    today_results = fetch_today_results()
    
    for result in today_results:
        try:
            result_student_id = str(result.get("Student ID", "")).strip()
            if result_student_id.lower() == student_id.lower():
                score = str(result.get("Score", "")).strip()
                return False, score
        except Exception:
            continue
    
    return True, None


# =====================================================================
# 6. SESSION STATE MANAGEMENT
# =====================================================================

def start_new_attempt():
    """Initialize a fresh quiz attempt."""
    new_token = str(uuid.uuid4())
    st.session_state.session_token = new_token
    st.session_state.stage = "login"
    st.session_state.student_id = ""
    st.session_state.student_name = ""
    st.session_state.student_class = ""
    st.session_state.current_q_index = 0
    st.session_state.score = 0
    st.session_state.answered_current = False
    st.session_state.last_answer_correct = None
    st.session_state.logged = False
    st.session_state.quiz_questions = []
    st.session_state.quiz_start_time = None
    st.session_state.question_start_time = None
    st.session_state.time_expired = False
    st.query_params["sid"] = new_token


def prepare_quiz_questions():
    """Prepare randomized question set from full bank."""
    full_bank = fetch_question_bank()
    
    if not full_bank:
        return False

    n = len(full_bank)
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
    st.session_state.quiz_start_time = datetime.now(pytz.timezone(TIMEZONE))
    st.session_state.question_start_time = st.session_state.quiz_start_time
    return True


def get_remaining_times() -> Tuple[int, int, bool]:
    """
    Calculate remaining global time and per-question time.
    Returns: (global_remaining_sec, per_question_remaining_sec, is_expired)
    """
    if st.session_state.quiz_start_time is None:
        return GLOBAL_QUIZ_TIME, 0, False
    
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    elapsed_global = (now - st.session_state.quiz_start_time).total_seconds()
    global_remaining = max(0, GLOBAL_QUIZ_TIME - elapsed_global)
    
    if global_remaining <= 0:
        return 0, 0, True
    
    total_questions = len(st.session_state.quiz_questions)
    per_question_limit = GLOBAL_QUIZ_TIME / max(1, total_questions)
    
    elapsed_current = (now - st.session_state.question_start_time).total_seconds()
    per_question_remaining = max(0, per_question_limit - elapsed_current)
    
    return int(global_remaining), int(per_question_remaining), False


def ensure_valid_session():
    """Validate session on every rerun."""
    url_sid = st.query_params.get("sid", None)
    
    if "session_token" not in st.session_state:
        start_new_attempt()
    else:
        if url_sid != st.session_state.session_token:
            start_new_attempt()


# =====================================================================
# 7. UI SCREENS
# =====================================================================

def render_login_screen():
    """Login screen with roster verification."""
    st.markdown("<h1 class='quiz-header'>🧠 Daily Quiz</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666;'>ឆ្លើយសំណួរ។ សូមពិបាក! 💪</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    roster = fetch_students_roster()

    with st.form("login_form", clear_on_submit=False):
        st.write("📋 **ជ្រើសរើស Student ID:**")
        
        if roster:
            student_options = {
                f"{s['student_id']} - {s['full_name']} ({s['class']})": s['student_id']
                for s in roster
            }
            selected_option = st.selectbox(
                "Student",
                options=list(student_options.keys()),
                label_visibility="collapsed"
            )
            student_id = student_options[selected_option] if selected_option else ""
        else:
            st.warning("⚠️ មិនរកឃើញ Roster។ សូមដាក់ 'Students' tab ដែលមាន។")
            student_id = st.text_input("Student ID", placeholder="ឧ: S001")
        
        submitted = st.form_submit_button("ចូលតេស្ត 🚀", use_container_width=True)

        if submitted:
            if not student_id or not student_id.strip():
                st.error("⚠️ សូមជ្រើសរើស Student ID។")
                return

            is_authorized, error_msg = verify_student_attendance(student_id.strip())
            if not is_authorized:
                st.markdown(
                    f"<div class='access-denied'>{error_msg}</div>",
                    unsafe_allow_html=True
                )
                return

            can_attempt, previous_score = check_today_attempt(student_id.strip())
            if not can_attempt:
                st.markdown(
                    f"<div class='access-denied'>"
                    f"⚠️ អ្នកបានធ្វើតេស្តរួចហើយថ្ងៃនេះ។<br><br>"
                    f"📊 ពិន្ទុលើកមុន: <b>{previous_score}</b><br><br>"
                    f"ត្រូវរង់ចាំពេលលើក១ថ្ងៃស្អែក ដើម្បីព្យាយាមម្ដងទៀត។"
                    f"</div>",
                    unsafe_allow_html=True
                )
                return

            student_info = None
            for s in roster:
                if s["student_id"].lower() == student_id.lower():
                    student_info = s
                    break

            if student_info:
                st.session_state.student_id = student_id.strip()
                st.session_state.student_name = student_info["full_name"]
                st.session_state.student_class = student_info["class"]
            else:
                st.session_state.student_id = student_id.strip()
                st.session_state.student_name = student_id.strip()
                st.session_state.student_class = "Unknown"

            with st.spinner("📥 ទាញយកសំណួរ..."):
                ok = prepare_quiz_questions()

            if not ok:
                st.error("❌ មិនបានទាញយកសំណួរ។ សូមព្យាយាមវិញ។")
                return

            st.session_state.stage = "quiz"
            st.rerun()


def render_quiz_screen():
    """Main quiz screen with timers."""
    questions = st.session_state.quiz_questions

    if not questions:
        st.error("❌ មិនមាននូវសំណួរ។ សូមចាប់ផ្តើមម្ដងទៀត។")
        if st.button("🔄 ចាប់ផ្តើមម្ដងទៀត"):
            start_new_attempt()
            st.rerun()
        return

    global_remaining, per_question_remaining, is_expired = get_remaining_times()

    if is_expired:
        st.session_state.stage = "result"
        st.session_state.time_expired = True
        st.rerun()

    idx = st.session_state.current_q_index
    total = len(questions)

    if global_remaining <= 120:
        timer_class = "timer-critical" if global_remaining <= 60 else "timer-warning"
        minutes, seconds = divmod(global_remaining, 60)
        st.markdown(
            f"<div class='{timer_class}'>⏱️ ពេលលេងសម្រាប់គ្រប់គ្រង: {int(minutes)}:{int(seconds):02d}</div>",
            unsafe_allow_html=True
        )
    
    st.progress(idx / total, text=f"សំណួរ {idx + 1} នៃ {total}")

    q = questions[idx]
    st.markdown(f"### {q['question']}")
    
    minutes, seconds = divmod(per_question_remaining, 60)
    st.caption(f"⏳ ពេលលេងសម្រាប់សំណួរនេះ: {int(minutes)}:{int(seconds):02d}")

    if per_question_remaining <= 0 and not st.session_state.answered_current:
        st.session_state.answered_current = True
        st.session_state.last_answer_correct = False
        st.rerun()

    if not st.session_state.answered_current:
        for option in q["options"]:
            if st.button(option, key=f"opt_{idx}_{option}", use_container_width=True):
                is_correct = option == q["answer"]
                st.session_state.answered_current = True
                st.session_state.last_answer_correct = is_correct
                if is_correct:
                    st.session_state.score += 1
                st.session_state.question_start_time = datetime.now(pytz.timezone(TIMEZONE))
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
                "<div class='feedback-correct'>✅ ត្រឹមត្រូវ!</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='feedback-incorrect'>❌ មិនត្រឹមត្រូវ។ ចម្លើយ: <b>{q['answer']}</b></div>",
                unsafe_allow_html=True,
            )

        import time
        time.sleep(1.5)

        if idx + 1 < total:
            st.session_state.current_q_index += 1
            st.session_state.answered_current = False
            st.session_state.last_answer_correct = None
            st.session_state.question_start_time = datetime.now(pytz.timezone(TIMEZONE))
        else:
            st.session_state.stage = "result"

        st.rerun()


def render_result_screen():
    """Results screen with score display and logging."""
    score = st.session_state.score
    total = len(st.session_state.quiz_questions)

    st.balloons()
    st.markdown("<h1 class='quiz-header'>🎉 ការសម្ពឹងស្វាគមន៍!</h1>", unsafe_allow_html=True)

    time_expired_msg = ""
    if st.session_state.get("time_expired", False):
        time_expired_msg = (
            "<p style='color:#d32f2f; font-weight:600;'>"
            "⏰ ពេលលេងបានផុតរលាយ។ សូមប្រើពេលដែលបានគណនាទៅពេលបច្ចុប្បន្ន។"
            "</p>"
        )

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
            {time_expired_msg}
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
            st.success("✅ លទ្ធផលរបស់អ្នកបានរក្សាទុក។ សូមបិទបង្អួចនេះ។")
        else:
            st.info("⚠️ លទ្ធផលមិនបាន រក្សាទុកដោយស្វ័ង់ទេ។ សូមប្រាប់គ្រូ៖ " + str(score) + "/" + str(total))
    else:
        st.success("✅ លទ្ធផលបានរក្សាទុក។ សូមបិទបង្អួច។")

    st.divider()
    st.caption(
        "💡 ក្នុងពេលដែលអ្នកចាក់ឯកសារ ឬបើក link ម្ដងទៀត វាបង្ហាញ "
        "ថា អ្នកបានធ្វើតេស្តរួចហើយថ្ងៃនេះ។"
    )


# =====================================================================
# 8. MAIN APP
# =====================================================================

def main():
    """Main application entry point."""
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
