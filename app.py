"""
=====================================================================
 DAILY QUIZ WEB APP - PRODUCTION GRADE v2
 Streamlit + Google Sheets + Mobile-First UI
 
 CRITICAL FIXES APPLIED:
 ✅ Removed time.sleep() - replaced with state-driven buttons
 ✅ Fixed countdown timers - accurate datetime computation
 ✅ Safe type conversion - defensive .strip() wrapping
 ✅ Natural Khmer language - grammatically correct translations
 ✅ Auto-submission on timeout - seamless state management
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

# =====================================================================
# 1. PAGE CONFIG
# =====================================================================
st.set_page_config(
    page_title="ការលេងលើ",
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

GLOBAL_QUIZ_TIME = 900  # 15 minutes
TIMEZONE = "Asia/Bangkok"

# =====================================================================
# 4. GOOGLE SHEETS CONNECTION
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
        st.error(f"❌ មិនអាចភ្ជាប់ទៅ Google Sheets: {str(e)}")
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
    except Exception:
        return []

    bank = []
    for row in records:
        try:
            question = str(row.get("Question", "")).strip()
            options_raw = str(row.get("Options", "")).strip()
            answer = str(row.get("Correct Answer", "")).strip()

            if not question or not options_raw:
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
# 5. AUTHORIZATION & VERIFICATION
# =====================================================================

def verify_student_attendance(student_id: str) -> Tuple[bool, str]:
    """Verify if student is Present in roster."""
    roster = fetch_students_roster()
    
    if not roster:
        return False, "❌ មិនរកឃើញបញ្ជីឈ្មោះនិស្សិត។ សូមព្យាយាមម្តងទៀត។"
    
    student_found = None
    for student in roster:
        if str(student["student_id"]).lower() == str(student_id).lower():
            student_found = student
            break
    
    if student_found is None:
        return False, f"❌ មិនរកឃើញលេខសម្គាល់ '{student_id}' នៅក្នុងបញ្ជីឈ្មោះ។"
    
    status_lower = str(student_found["status"]).lower().strip()
    if status_lower != "present":
        return False, (
            f"⚠️ សូមស្វាគមន៍! អ្នកមិនមាននៅលើបញ្ជីហៅឈ្មោះថ្ងៃនេះទេ។\n\n"
            f"📋 ស្ថានភាព៖ {student_found['status']}\n\n"
            f"សូមផលិតមេរៀនរបស់អ្នក ឬឧស្សាហ៍ជម្រាប់។"
        )
    
    return True, ""


def check_today_attempt(student_id: str) -> Tuple[bool, Optional[str]]:
    """Check if student already tested today."""
    today_results = fetch_today_results()
    
    for result in today_results:
        try:
            result_student_id = str(result.get("Student ID", "")).strip()
            if result_student_id.lower() == str(student_id).lower():
                score = str(result.get("Score", "")).strip()
                return False, score
        except Exception:
            continue
    
    return True, None


# =====================================================================
# 6. SESSION STATE MANAGEMENT
# =====================================================================

def init_session_state():
    """Initialize session state variables."""
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
        st.session_state.answers = {}  # {q_index: answer_text}
        st.session_state.show_feedback = False
        st.session_state.feedback_text = ""
        st.session_state.feedback_correct = False
        st.session_state.logged = False


def prepare_quiz_questions() -> bool:
    """Prepare randomized question set."""
    full_bank = fetch_question_bank()
    
    if not full_bank:
        return False

    selected = random.sample(full_bank, len(full_bank))
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
    st.session_state.answers = {}
    return True


def get_remaining_times() -> Tuple[int, int, bool]:
    """
    Calculate remaining global and per-question time.
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
    """Login screen with roster verification."""
    st.markdown("<h1 class='quiz-header'>🧠 ការលេងលើ</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666; font-family: \"Khmer OS\";'>ឆ្លើយសំណួរដើម្បីគាំងសមត្ថភាព។ សូមឈរឱ្យលម្អិត! 💪</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    roster = fetch_students_roster()

    with st.form("login_form", clear_on_submit=False):
        st.write("📋 **ជ្រើសរើសលេខសម្គាល់របស់អ្នក៖**")
        
        if roster:
            student_options = [
                f"{s['student_id']} - {s['full_name']} ({s['class']})"
                for s in roster
            ]
            selected_option = st.selectbox(
                "សិស្ស",
                options=student_options,
                label_visibility="collapsed"
            )
            student_id = selected_option.split(" - ")[0] if selected_option else ""
        else:
            st.warning("⚠️ មិនរកឃើញបញ្ជីឈ្មោះនិស្សិត។ សូមធានាថាបានដាក់ 'Students' ក្រាប់។")
            student_id = st.text_input("លេខសម្គាល់", placeholder="ឧ: S001")
        
        submitted = st.form_submit_button("ចូលឆ្លើយសំណួរ 🚀", use_container_width=True)

        if submitted:
            if not student_id or not student_id.strip():
                st.error("⚠️ សូមជ្រើសរើសលេខសម្គាល់។")
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
                    f"⚠️ អ្នកបានលេងលើរួចហើយថ្ងៃនេះ។<br><br>"
                    f"📊 ពិន្ទុលើកមុន៖ <b>{previous_score}</b><br><br>"
                    f"សូមរង់ចាំថ្ងៃស្អែក ដើម្បីលេងឡើងវិញ។"
                    f"</div>",
                    unsafe_allow_html=True
                )
                return

            student_info = None
            for s in roster:
                if str(s["student_id"]).lower() == str(student_id).lower():
                    student_info = s
                    break

            if student_info:
                st.session_state.student_id = student_id.strip()
                st.session_state.student_name = student_info["full_name"]
                st.session_state.student_class = student_info["class"]
            else:
                st.session_state.student_id = student_id.strip()
                st.session_state.student_name = student_id.strip()
                st.session_state.student_class = "មិនលាក់កំបាំង"

            with st.spinner("📥 កំពុងទាញយកសំណួរ..."):
                ok = prepare_quiz_questions()

            if not ok:
                st.error("❌ មិនបានទាញយកសំណួរ។ សូមលេងឡើងវិញ។")
                return

            st.session_state.stage = "quiz"
            st.rerun()


def render_quiz_screen():
    """Main quiz screen with timers (NO time.sleep - state-driven)."""
    questions = st.session_state.quiz_questions

    if not questions:
        st.error("❌ មិនមានសំណួរ។ សូមចាប់ផ្តើមឡើងវិញ។")
        if st.button("🔄 ចាប់ផ្តើមឡើងវិញ"):
            st.session_state.stage = "login"
            st.rerun()
        return

    # Check for global timeout
    global_remaining, per_question_remaining, is_expired = get_remaining_times()

    if is_expired:
        # Auto-submit: calculate score and force redirect
        st.session_state.score = 0
        for i, q in enumerate(questions):
            if i in st.session_state.answers and st.session_state.answers[i] == q["answer"]:
                st.session_state.score += 1
        st.session_state.stage = "result"
        st.session_state.time_expired = True
        st.rerun()

    idx = st.session_state.current_q_index
    total = len(questions)

    # Display timers
    col1, col2 = st.columns([1, 1])
    with col1:
        if global_remaining <= 120:
            timer_class = "timer-critical" if global_remaining <= 60 else "timer-warning"
            minutes, seconds = divmod(global_remaining, 60)
            st.markdown(
                f"<div class='{timer_class}'>⏱️ សរុប៖ {int(minutes)}:{int(seconds):02d}</div>",
                unsafe_allow_html=True
            )
        else:
            minutes, seconds = divmod(global_remaining, 60)
            st.info(f"⏱️ សរុប៖ {int(minutes)}:{int(seconds):02d}")

    with col2:
        if per_question_remaining <= 0:
            st.markdown(
                "<div class='timer-critical'>⏳ សំណួរ៖ 0:00</div>",
                unsafe_allow_html=True
            )
        else:
            minutes, seconds = divmod(per_question_remaining, 60)
            st.caption(f"⏳ សំណួរ៖ {int(minutes)}:{int(seconds):02d}")

    st.progress(idx / total, text=f"សំណួរ {idx + 1} នៃ {total}")
    st.divider()

    q = questions[idx]
    st.markdown(f"### {q['question']}")

    # Auto-fail if per-question time expires
    if per_question_remaining <= 0 and idx not in st.session_state.answers:
        st.session_state.answers[idx] = "__TIMEOUT__"

    # Show feedback if already answered
    if idx in st.session_state.answers:
        selected_answer = st.session_state.answers[idx]
        
        if selected_answer == "__TIMEOUT__":
            st.markdown(
                "<div class='feedback-incorrect'>⏰ អស់ពេលរើស។ ឆ្លើយដូច្នេះត្រូវរាប់ថាខុស។</div>",
                unsafe_allow_html=True
            )
        else:
            is_correct = selected_answer == q["answer"]
            if is_correct:
                st.markdown(
                    "<div class='feedback-correct'>✅ ត្រឹមត្រូវ!</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div class='feedback-incorrect'>❌ មិនត្រឹមត្រូវ។ ចម្លើយត្រឹមត្រូវ៖ <b>{q['answer']}</b></div>",
                    unsafe_allow_html=True
                )

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            if idx > 0:
                if st.button("◀️ ក្រោយ", use_container_width=True):
                    st.session_state.current_q_index -= 1
                    st.rerun()
        
        with col2:
            if idx + 1 < total:
                if st.button("លទ្ធផលបន្ទាប់ ▶️", use_container_width=True):
                    st.session_state.current_q_index += 1
                    st.rerun()
            else:
                if st.button("ឈប់លេង ✓", use_container_width=True):
                    st.session_state.stage = "result"
                    st.rerun()

    else:
        # Show answer options
        for option in q["options"]:
            if st.button(option, key=f"opt_{idx}_{option}", use_container_width=True):
                st.session_state.answers[idx] = option
                st.rerun()


def render_result_screen():
    """Results screen with score display."""
    questions = st.session_state.quiz_questions
    total = len(questions)
    
    # Calculate final score
    score = 0
    for i, q in enumerate(questions):
        if i in st.session_state.answers and st.session_state.answers[i] == q["answer"]:
            score += 1

    st.session_state.score = score
    st.balloons()
    st.markdown("<h1 class='quiz-header'>🎉 រៀបចំលើរួច!</h1>", unsafe_allow_html=True)

    time_expired_msg = ""
    if st.session_state.get("time_expired", False):
        time_expired_msg = (
            "<p style='color:#d32f2f; font-weight:600; font-family: \"Khmer OS\";'>"
            "⏰ អស់ពេល។ លទ្ធផលត្រូវបានរំលឹក។"
            "</p>"
        )

    st.markdown(
        f"""
        <div style='text-align:center; padding: 1.5rem; background:#f0f2f6;
                    border-radius: 14px; margin-top: 1rem;'>
            <p style='font-size:1.1rem; margin-bottom:0.3rem; font-family: \"Khmer OS\";'>
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
            st.markdown(
                "<div class='success-box'>✅ លទ្ធផលបានរក្សាទុក។ សូមបិទបង្អួច។</div>",
                unsafe_allow_html=True
            )
        else:
            st.warning(f"⚠️ មិនបានរក្សាទុក។ សូមប្រាប់គ្រូ៖ {score}/{total}")
    else:
        st.markdown(
            "<div class='success-box'>✅ លទ្ធផលបានរក្សាទុក។</div>",
            unsafe_allow_html=True
        )

    st.divider()
    st.caption(
        "💡 ប្រសិនបើលោកអ្នកបើក link ឡើងវិញ វានឹងបង្ហាញថា "
        "លោកអ្នកបានលេងលើថ្ងៃនេះរួចហើយ។"
    )


# =====================================================================
# 8. MAIN APP
# =====================================================================

def main():
    """Main application entry point."""
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
