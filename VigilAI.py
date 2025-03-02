import time
import streamlit as st
import json
from datetime import datetime
import ollama  # Ensure this module is installed or use a subprocess wrapper

# Set page config first
st.set_page_config(page_title="DHS Training Simulator", layout="wide")

# Cache the loading of the scenarios data to avoid re-reading the file on every rerun
@st.cache_data
def load_scenarios():
    with open("scenarios.json") as f:
        data = json.load(f)
    return data["vigilai_ops_data.json"]["scenarios"]

scenarios = load_scenarios()

# Cache extraction of protocols
@st.cache_data
def get_all_protocols():
    protocols = set()
    for scenario in scenarios:
        response_protocols = scenario.get("response_protocols", {})
        immediate = response_protocols.get("immediate_actions", [])
        protocols.update(immediate)
        escalation_paths = response_protocols.get("escalation_paths", [])
        for ep in escalation_paths:
            actions = ep.get("actions", [])
            protocols.update(actions)
    return list(protocols)

# Initialize session state
def init_session():
    session_defaults = {
        'user_input': '',
        'conversation': [],
        'score': 0,
        'start_time': time.time(),
        'selected_protocols': [],
        'protocol_submitted': False,
        'current_traveler': None,
        'protocol_feedback': {},
        'show_hints': False,
        'threat_analysis': None,  # For Ollama integration
        'last_traveler_id': None,  # To check if traveler changed
        'risk_text': "",
        'risk_color': ""
    }
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# Updated risk indicator with caching to avoid duplicate calls if traveler hasn't changed
def risk_indicator(traveler_data):
    # If the traveler hasn't changed and we've already computed the analysis, return it
    if st.session_state.last_traveler_id == traveler_data["id"] and st.session_state.threat_analysis:
        return st.session_state.risk_text, st.session_state.risk_color, st.session_state.threat_analysis

    try:
        response = ollama.chat(
            model='vigilai',
            messages=[{
                'role': 'user',
                'content': f"""Analyze this traveler profile:
{json.dumps(traveler_data, separators=(',', ':'))}
Use the threat matrix and response format"""
            }]
        )
        analysis = response['message']['content']
        st.session_state.threat_analysis = analysis

        if "**Threat Level:** High" in analysis:
            risk_text, risk_color = "🔴 HIGH RISK", "#F44336"
        elif "**Threat Level:** Medium" in analysis:
            risk_text, risk_color = "🟡 MEDIUM RISK", "#FFC107"
        else:
            risk_text, risk_color = "🟢 LOW RISK", "#4CAF50"

        # Cache the result for the current traveler
        st.session_state.last_traveler_id = traveler_data["id"]
        st.session_state.risk_text = risk_text
        st.session_state.risk_color = risk_color

        return risk_text, risk_color, analysis
    except Exception as e:
        st.error(f"Analysis Error: {str(e)}")
        return "⚠️ ANALYSIS ERROR", "#9E9E9E", ""

# Main application
def main():
    init_session()

    st.title("🚨 DHS Border Security Training Simulator")

    # --- Traveler Selection ---
    selected_name = st.selectbox(
        "Select Traveler Profile",
        options=[t["profile"]["name"] for t in scenarios],
        index=0
    )
    selected = next(t for t in scenarios if t["profile"]["name"] == selected_name)
    all_protocols = get_all_protocols()
    correct_protocols = selected.get("protocols", selected.get("response_protocols", {}).get("immediate_actions", []))

    # Reset states on new selection if traveler has changed
    if st.session_state.get("current_traveler") != selected["id"]:
        st.session_state.start_time = time.time()
        st.session_state.current_traveler = selected["id"]
        st.session_state.score = 0
        st.session_state.selected_protocols = []
        st.session_state.protocol_submitted = False
        st.session_state.protocol_feedback = {}
        st.session_state.show_hints = False
        st.session_state.threat_analysis = None

    # --- Profile Header ---
    risk_text, risk_color, analysis = risk_indicator(selected)
    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.subheader(f"Traveler Profile: {selected['profile']['name']}")
        with col2:
            st.markdown(f"<h3 style='color:{risk_color};'>{risk_text}</h3>", unsafe_allow_html=True)
        with col3:
            elapsed = int(time.time() - st.session_state.start_time)
            st.metric("⏱️ Time Elapsed", f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    # Main columns
    main_col, protocol_col = st.columns([3, 2], gap="large")
    with main_col:
        # --- Threat Analysis Section ---
        with st.expander("🔍 AI Threat Analysis", expanded=True):
            if st.session_state.threat_analysis:
                st.markdown(st.session_state.threat_analysis)
            else:
                st.warning("Analysis pending...")

        # --- Compact Profile Details ---
        with st.container():
            cols = st.columns([1, 1, 2, 2])
            with cols[0]:
                st.markdown(f"**Nationality**  \n{selected['profile']['demographics']['nationality']}")
            with cols[1]:
                st.markdown(f"**Age**  \n{selected['profile']['demographics']['age']}")
            with cols[2]:
                st.markdown(f"**Purpose**  \n{selected.get('purpose', 'N/A')}")
            with cols[3]:
                st.markdown(f"**Emotion**  \n{selected.get('emotional_state', 'neutral').title()}")

        # --- Red Flags & Conversation ---
        tab1, tab2 = st.tabs(["🚩 Risk Indicators", "💬 Interview Interface"])
        with tab1:
            red_flags = selected.get("red_flags", [])
            if red_flags:
                st.error(f"⛔ Red Flags Detected: {len(red_flags)}")
                for flag in red_flags:
                    st.markdown(f"• 🔍 {flag}")
            else:
                st.success("✅ No red flags detected")
        with tab2:
            with st.form("question_form"):
                user_input = st.text_input("Ask a question:", key="question_input")
                submitted = st.form_submit_button("➤ Submit", use_container_width=True)
            if submitted:
                process_question(selected, user_input)
            st.subheader("📜 Live Transcript")
            transcript_container = st.container(height=200)
            with transcript_container:
                for entry in st.session_state.conversation[-3:]:
                    st.markdown(f"`{entry['time']}` **{entry['role']}**: {entry['content']}")
            st.subheader("💡 Quick Questions")
            # Create two columns once to optimize rendering
            quick_cols = st.columns(2)
            for i, qa in enumerate(selected.get("script", [])[:4]):
                with quick_cols[i % 2]:
                    if st.button(qa["question"], key=f"suggest_{qa['question'][:10]}"):
                        st.session_state.user_input = qa["question"]
                        st.experimental_rerun()

    with protocol_col:
        st.header("🔒 Protocols")
        with st.container(height=300):
            selected_protocols = []
            protocol_cols = st.columns(2)
            for i, protocol in enumerate(all_protocols):
                col = protocol_cols[i % 2]
                with col:
                    protocol_hash = abs(hash(protocol))
                    unique_key = f"proto_{selected['id']}_{protocol_hash}"
                    if st.checkbox(
                        protocol,
                        value=protocol in st.session_state.selected_protocols,
                        key=unique_key,
                        label_visibility="visible"
                    ):
                        selected_protocols.append(protocol)
        with st.container():
            cols = st.columns([2, 1])
            with cols[0]:
                if st.button("✅ Validate Selection", use_container_width=True):
                    st.session_state.selected_protocols = selected_protocols
                    st.session_state.protocol_submitted = True
                    correct = set(selected_protocols) & set(correct_protocols)
                    incorrect = set(selected_protocols) - set(correct_protocols)
                    missed = set(correct_protocols) - set(selected_protocols)
                    st.session_state.score += len(correct) * 2
                    st.session_state.score -= (len(incorrect) + len(missed)) * 1
                    st.session_state.score = max(st.session_state.score, 0)
                    st.session_state.protocol_feedback = {
                        "correct": list(correct),
                        "incorrect": list(incorrect),
                        "missed": list(missed)
                    }
            with cols[1]:
                st.metric("Score", st.session_state.score)
        if st.session_state.protocol_submitted:
            st.subheader("📝 Feedback")
            feedback = st.session_state.protocol_feedback
            feedback_cols = st.columns(3)
            with feedback_cols[0]:
                st.metric("Correct", len(feedback["correct"]), help="Properly identified protocols")
            with feedback_cols[1]:
                st.metric("Incorrect", len(feedback["incorrect"]), help="Unnecessary protocols selected")
            with feedback_cols[2]:
                st.metric("Missed", len(feedback["missed"]), help="Critical protocols overlooked")
        with st.expander("⚙️ Tools", expanded=True):
            tool_cols = st.columns(2)
            with tool_cols[0]:
                if st.button("💡 Get Hint (-1pt)", help="Reveal protocol clues", use_container_width=True):
                    if st.session_state.score > 0:
                        st.session_state.score = max(st.session_state.score - 1, 0)
                        st.session_state.show_hints = True
            with tool_cols[1]:
                report = f"Report for {selected['profile']['name']}"
                st.download_button("📥 Download Report", report, file_name="dhs_report.md", use_container_width=True)

def process_question(selected, user_input):
    with st.spinner("🔍 Analyzing response..."):
        # Removed time.sleep to reduce unnecessary delay
        response_found = False
        for qa in selected.get("script", []):
            if user_input.strip().lower() == qa["question"].strip().lower():
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": "You",
                    "content": user_input
                })
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": selected["profile"]["name"],
                    "content": qa["response"]
                })
                new_score = st.session_state.score + 2
                st.session_state.score = min(max(new_score, 0), 10)
                response_found = True
                break
        if not response_found:
            try:
                # Override the system instructions for unscripted questions so that the traveler answers naturally.
                response = ollama.chat(
                    model='vigilai',
                    messages=[
                        {'role': 'system', 'content': "Disregard previous instructions. You are a traveler at the border and should answer questions in a realistic, natural manner rather than providing threat analysis."},
                        {'role': 'user', 'content': f"""Traveler profile: {json.dumps(selected, separators=(',', ':'))}
Officer question: {user_input}
Generate an appropriate, realistic response:"""}
                    ]
                )
                ai_response = response['message']['content']
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": "You",
                    "content": user_input
                })
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": selected["profile"]["name"],
                    "content": ai_response
                })
            except Exception as e:
                st.error(f"AI Response Error: {str(e)}")

if __name__ == "__main__":
    main()
