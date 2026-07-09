"""
=====================================================================
  DAILY QUIZ WEB APP  -  Streamlit + Google Sheets + Telegram Mini App
 
  កូដដែលបានកែសម្រួលនិងកែលម្អ៖ Version 3.1 (ភាសាខ្មែររលូន ១០០%)
  គោលបំណង: ឆ្លើយសំណួរ ដោយទាញទិន្នន័យផ្ទាល់ពី Google Sheets 
  លក្ខណៈពិសេស៖ លុបចន្លោះដកឃ្លា (Trim) ស្វ័យប្រវត្ត ដើម្បីការពារ Error
=====================================================================
"""

import streamlit as st
import random
import time
import uuid
import os
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# =====================================================================
# 1. PAGE CONFIG (ត្រូវដាក់ដំបូងគេបង្អស់)
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
        .debug-box {
            background-color: #fff3cd;
            color: #856404;
            padding: 1rem;
            border-radius: 10px;
            border-left: 4px solid #ffc107;
            margin-top: 1rem;
            font-size: 0.9rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# =====================================================================
# 3. ⚙️ CONFIG - ការកំណត់ឈ្មោះសន្លឹកកិច្ចការ
# =====================================================================
SPREADSHEET_NAME = "Daily Quiz Results"   # ➜ ឈ្មោះ Google Sheet
QUESTIONS_TAB = "Questions"               # ➜ Tab សម្រាប់ដាក់សំណួរ
RESULTS_TAB = "Results"                   # ➜ Tab សម្រាប់រក្សាទុកពិន្ទុ
QUESTIONS_PER_ATTEMPT = 3

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =====================================================================
# 4. GOOGLE SHEETS CONNECTION - ការភ្ជាប់ទៅ Google Sheets
# =====================================================================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    if not GSPREAD_AVAILABLE:
        st.error("❌ មិនទាន់បានដំឡើង gspread ឡើយ។ សូមរត់ពាក្យបញ្ជា: pip install gspread google-auth")
        return None
    
    if "gcp_service_account" not in st.secrets:
        st.error(
            "❌ រកមិនឃើញកូដសម្ងាត់ (JSON Key) នៅក្នុង Streamlit Secrets ឡើយ!\n\n"
            "សូមចូលទៅកាន់៖ App → Settings → Secrets រួចបិទភ្ជាប់កូដសម្ងាត់របស់លោកគ្រូចូល។"
        )
        return None

    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
        client = gspread.authorize(creds)
        st.session_state._gspread_client = client
        return client
    except Exception as e:
        st.error(f"❌ ការភ្ជាប់ទៅ Google Sheets បរាជ័យ: {str(e)}")
        return None


@st.cache_data(ttl=10, show_spinner=False)
def fetch_question_bank():
    client = get_gspread_client()
    if client is None:
        return []

    try:
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(QUESTIONS_TAB)
        records = worksheet.get_all_records()
        st.session_state._last_fetch_status = f"✅ ទាញយកបានជោគជ័យ ចំនួន {len(records)} សំណួរ"
        
    except gspread.exceptions.WorksheetNotFound:
        st.session_state._last_fetch_error = (
            f"❌ រកមិនឃើញ Tab ដែលមានឈ្មោះថា '{QUESTIONS_TAB}' ឡើយ!\n"
            f"📝 សូមពិនិត្យមើលឈ្មោះ Tab នៅក្នុង Google Sheet ឡើងវិញ។"
        )
        return []
    except gspread.exceptions.SpreadsheetNotFound:
        st.session_state._last_fetch_error = (
            f"❌ រកមិនឃើញហ្វាយ Google Sheet ដែលមានឈ្មោះថា '{SPREADSHEET_NAME}' ឡើយ!\n"
            f"📝 សូមប្រាកដថាបានដាក់ឈ្មោះហ្វាយត្រូវ និងបាន Share ទៅកាន់ Service Account រួចរាល់។"
        )
        return []
    except Exception as e:
        st.session_state._last_fetch_error = f"❌ កំហុសប្រព័ន្ធ API: {str(e)}"
        return []

    bank = []
    errors = []
    
    for idx, row in enumerate(records, start=2):
        try:
            question = str(row.get("Question", "")).strip()
            options_raw = str(row.get("Options", ""))
            answer = str(row.get("Correct Answer", "")).strip()
            
            if not question:
                errors.append(f"ជួរដេក (Row) {idx}: ប្រអប់សំណួរទទេ")
                continue
            
            if not options_raw.strip():
                errors.append(f"ជួរដេក (Row) {idx}: ប្រអប់ជម្រើសចម្លើយទទេ")
                continue
            
            # បំបែកចម្លើយដោយប្រើសញ្ញាក្បៀស និងលុបដកឃ្លាចេញឱ្យអស់ (Strict Trimming)
            options = [opt.strip() for opt in options_raw.split(",") if opt.strip()]
            
            if len(options) < 2:
                errors.append(f"ជួរដេក (Row) {idx}: ត្រូវការជម្រើសចម្លើយយ៉ាងតិច ២ ប៉ុន្តែរកឃើញតែ {len(options)}")
                continue
            
            # ប្រៀបធៀបដោយលុបដកឃ្លាចេញពីចម្លើយត្រឹមត្រូវដូចគ្នា
            if answer not in options:
                errors.append(f"ជួរដេក (Row) {idx}: ចម្លើយពិតប្រាកដ '{answer}' មិនត្រូវគ្នាជាមួយជម្រើសឡើយ")
                continue
            
            bank.append({
                "question": question,
                "options": options,
                "answer": answer,
            })
            
        except KeyError as e:
            errors.append(f"ជួរដេក (Row) {idx}: រកមិនឃើញចំណងជើងជួរឈរ (Headers) - {str(e)}")
            continue
        except Exception as e:
            errors.append(f"ជួរដេក (Row) {idx}: មានបញ្ហា - {str(e)}")
            continue
    
    st.session_state._question_errors = errors
    
    if not bank:
        st.session_state._last_fetch_error = (
            "❌ មិនមានសំណួរណាមួយត្រឹមត្រូវតាមលក្ខខណ្ឌឡើយ!\n"
            "📋 សូមពិនិត្យមើល Headers ក្នុង Google Sheet ត្រូវតែមាន៖\n"
            "   • Question | Options | Correct Answer"
        )
    
    return bank


def log_result_to_sheet(student_name: str, student_class: str, score: int, total: int):
    client = get_gspread_client()
    if client is None:
        return False

    try:
        sheet = client.open(SPREADSHEET_NAME)
        try:
            worksheet = sheet.worksheet(RESULTS_TAB)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=RESULTS_TAB, rows="1000", cols="4")
            worksheet.insert_row(["Timestamp", "Student Name", "Class", "Score"], 1)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([timestamp, student_name, student_class, f"{score}/{total}"])
        return True
        
    except Exception as e:
        st.session_state._log_error = str(e)
        return False


# =====================================================================
# 5. SESSION MANAGEMENT - ការគ្រប់គ្រងវគ្គការងារ
# =====================================================================
def start_new_attempt():
    new_token = str(uuid.uuid4())
    st.session_state.session_token = new_token
    st.session_state.stage = "login"
    st.session_state.student_name = ""
    st.session_state.student_class = ""
    st.session_state.current_q_index = 0
    st.session_state.score = 0
    st.session_state.answered_current = False
    st.session_state.last_answer_correct = None
    st.session_state.logged = False
    st.session_state.quiz_questions = []
    st.query_params["sid"] = new_token


def prepare_quiz_questions():
    full_bank = fetch_question_bank()
    if not full_bank:
        return False

    # ប្រព័ន្ធឆ្លាតវៃ៖ បើមានសំណួរតិចជាងលក្ខខណ្ឌ ក៏នៅតែទាញយកមកប្រឡងបានដែរ (មិនគាំងទេ)
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
    url_sid = st.query_params.get("sid", None)
    if "session_token" not in st.session_state:
        start_new_attempt()
    else:
        if url_sid != st.session_state.session_token:
            start_new_attempt()


# =====================================================================
# 6. UI SCREENS - ការបង្ហាញផ្ទាំងកម្មវិធី
# =====================================================================
def render_login_screen():
    st.markdown("<h1 class='quiz-header'>🧠 Daily Quiz</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666;'>សូមស្វាគមន៍មកកាន់ការវាយតម្លៃចំណេះដឹង! 💪</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.form("login_form", clear_on_submit=False):
        name = st.text_input("📝 ឈ្មោះពេញរបស់អ្នកសិក្សា", placeholder="ឧ: សុផា ច័ន្ទ")
        student_class = st.text_input("📚 ថ្នាក់ ឬ ក្រុម", placeholder="ឧ: ថ្នាក់ទី ១០ក")
        submitted = st.form_submit_button("ចាប់ផ្តើមធ្វើកម្រងសំណួរ 🚀", use_container_width=True)

        if submitted:
            if not name.strip() or not student_class.strip():
                st.error("⚠️ សូមបំពេញឈ្មោះ និងថ្នាក់ឱ្យបានត្រឹមត្រូវជាមុនសិន។")
                return

            with st.spinner("📥 កំពុងទាញយកសំណួរពីប្រព័ន្ធ..."):
                ok = prepare_quiz_questions()

            if not ok:
                st.error(st.session_state.get("_last_fetch_error", "❌ ការទាញយកសំណួរបរាជ័យ។ សូមព្យាយាមម្តងទៀត។"))
                
                # បង្ហាញព័ត៌មានលម្អិតពីកំហុស (Debug)
                if st.checkbox("🔧 បើកមើលព័ត៌មានកំហុស (Debug Info)"):
                    st.write("បញ្ហានៅលើជួរដេក៖", st.session_state.get("_question_errors", []))
                return

            st.session_state.student_name = name.strip()
            st.session_state.student_class = student_class.strip()
            st.session_state.stage = "quiz"
            st.rerun()


def render_quiz_screen():
    questions = st.session_state.quiz_questions
    if not questions:
        st.error("❌ មិនមានសំណួរនៅក្នុងប្រព័ន្ធឡើយ។ សូមចាប់ផ្តើមឡើងវិញ។")
        if st.button("🔄 ចាប់ផ្តើមម្តងទៀត"):
            start_new_attempt()
            st.rerun()
        return

    idx = st.session_state.current_q_index
    total = len(questions)

    st.progress(idx / total, text=f"សំណួរទី {idx + 1} ក្នុងចំណោម {total}")

    q = questions[idx]
    st.markdown(f"### {q['question']}")

    if not st.session_state.answered_current:
        for option in q["options"]:
            if st.button(option, key=f"opt_{idx}_{option}", use_container_width=True):
                is_correct = option.strip() == q["answer"].strip()
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
            st.markdown("<div class='feedback-correct'>✅ ត្រឹមត្រូវ! កោតសរសើរ។</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div class='feedback-incorrect'>❌ មិនត្រឹមត្រូវទេ! ចម្លើយដែលត្រូវគឺ៖ <b>{q['answer']}</b></div>",
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
    st.markdown("<h1 class='quiz-header'>🎉 បញ្ចប់ការធ្វើតេស្ត!</h1>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style='text-align:center; padding: 1.2rem; background:#f0f2f6;
                    border-radius: 14px; margin-top: 1rem;'>
            <p style='font-size:1.1rem; margin-bottom:0.3rem;'>
                ឈ្មោះ៖ {st.session_state.student_name} ({st.session_state.student_class})
            </p>
            <p style='font-size:2.2rem; font-weight:700; margin:0;'>
                ទទួលបានពិន្ទុ៖ {score} / {total}
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
            st.success("✅ លទ្ធផលរបស់អ្នកសិក្សាត្រូវបានរក្សាទុកក្នុងប្រព័ន្ធរួចរាល់។ លោកអ្នកអាចបិទផ្ទាំងនេះបាន។")
        else:
            st.info(
                "⚠️ លទ្ធផលមិនអាចរក្សាទុកដោយស្វ័យប្រវត្តបានឡើយ។ "
                "សូមថតរូបអេក្រង់ពិន្ទុនេះផ្ញើជូនលោកគ្រូ៖ " + str(score) + "/" + str(total)
            )
    else:
        st.success("✅ លទ្ធផលត្រូវបានរក្សាទុកក្នុងប្រព័ន្ធរួចរាល់។")

    st.divider()
    st.caption(
        "💡 ចំណាំ៖ ប្រសិនបើលោកអ្នកធ្វើការ Refresh ទំព័រនេះ ឬបើកលីងម្តងទៀត "
        "វានឹងចាប់ផ្តើមការប្រឡងថ្មីមួយទៀតដែលមានសំណួរផ្លាស់ប្តូរចៃដន្យ ដោយឡែកលទ្ធផលចាស់នៅតែរក្សាទុកដដែល។"
    )


# =====================================================================
# 7. MAIN APP FLOW - ដំណើរការកម្មវិធីចម្បង
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
