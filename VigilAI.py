import time
import streamlit as st
import json
from datetime import datetime

# Load scenarios
with open("scenarios.json") as f:
    data = json.load(f)
    scenarios = data["travelers"]

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
        'show_hints': False
    }
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# Risk indicator component
def risk_indicator(flags):
    risk_level = len(flags)
    if risk_level == 0:
        return "🟢 LOW RISK", "#4CAF50"
    elif 1 <= risk_level <= 2:
        return "🟡 MEDIUM RISK", "#FFC107"
    else:
        return "🔴 HIGH RISK", "#F44336"

# Get all possible protocols from all scenarios
def get_all_protocols():
    all_protocols = set()
    for traveler in scenarios:
        all_protocols.update(traveler.get("protocols", []))
    return sorted(all_protocols)

# Main application
def main():
    st.set_page_config(page_title="DHS Training Simulator", layout="wide")
    init_session()
    
    st.title("🚨 DHS Border Security Training Simulator")
    
    # --- Traveler Selection ---
    selected_name = st.selectbox(
        "Select Traveler Profile",
        options=[t["name"] for t in scenarios],
        index=0
    )
    selected = next(t for t in scenarios if t["name"] == selected_name)
    all_protocols = get_all_protocols()
    correct_protocols = selected.get("protocols", [])
    
    # Reset states on new selection
    if 'current_traveler' not in st.session_state or st.session_state.current_traveler != selected['id']:
        st.session_state.start_time = time.time()
        st.session_state.current_traveler = selected['id']
        st.session_state.score = 0
        st.session_state.selected_protocols = []
        st.session_state.protocol_submitted = False
        st.session_state.protocol_feedback = {}
        st.session_state.show_hints = False

    # --- Profile Header ---
    risk_text, risk_color = risk_indicator(selected["red_flags"])
    with st.container():
        col1, col2, col3 = st.columns([2,1,1])
        with col1:
            st.subheader(f"Traveler Profile: {selected['name']}")
        with col2:
            st.markdown(f"<h3 style='color:{risk_color};'>{risk_text}</h3>", unsafe_allow_html=True)
        with col3:
            elapsed = int(time.time() - st.session_state.start_time)
            st.metric("⏱️ Time Elapsed", f"{elapsed // 60:02d}:{elapsed % 60:02d}")
    
    # Main columns
    main_col, protocol_col = st.columns([3, 2], gap="large")

    with main_col:
        # --- Compact Profile Details ---
        with st.container():
            cols = st.columns([1,1,2,2])  # Adjusted column widths
            with cols[0]:
                st.markdown(f"**Nationality**  \n{selected['nationality']}")
            with cols[1]:
                st.markdown(f"**Age**  \n{selected['age']}")
            with cols[2]:
                st.markdown(f"**Purpose**  \n{selected['purpose']}")
            with cols[3]:
                st.markdown(f"**Emotion**  \n{selected['emotional_state'].title()}")
        
        # --- Red Flags & Conversation ---
        tab1, tab2 = st.tabs(["🚩 Risk Analysis", "💬 Interview Interface"])
        
        with tab1:
            if selected["red_flags"]:
                st.error(f"⛔ Red Flags Detected: {len(selected['red_flags'])}")
                for flag in selected["red_flags"]:
                    st.markdown(f"• 🔍 {flag}")
            else:
                st.success("✅ No red flags detected")
            
        with tab2:
            # Conversation Input
            with st.form("question_form"):
                user_input = st.text_input("Ask a question:", key="question_input")
                submitted = st.form_submit_button("➤ Submit", use_container_width=True)
            
            if submitted:
                process_question(selected, user_input)
            
            # Compact Conversation History
            st.subheader("📜 Live Transcript")
            transcript_container = st.container(height=200)
            with transcript_container:
                for entry in st.session_state.conversation[-3:]:
                    st.markdown(f"`{entry['time']}` **{entry['role']}**: {entry['content']}")
            
            # Suggested Questions Grid
            st.subheader("💡 Quick Questions")
            cols = st.columns(2)
            for i, qa in enumerate(selected["script"][:4]):
                with cols[i % 2]:
                    if st.button(qa["question"], key=f"suggest_{qa['question'][:10]}"):
                        st.session_state.user_input = qa["question"]
                        st.experimental_rerun()

    with protocol_col:
        # --- Protocol Selection ---
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
        
        # Protocol Actions
        with st.container():
            cols = st.columns([2,1])
            with cols[0]:
                if st.button("✅ Validate Selection", use_container_width=True):
                    st.session_state.selected_protocols = selected_protocols
                    st.session_state.protocol_submitted = True
                    
                    # Calculate protocol score
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
        
        # --- Compact Feedback ---
        if st.session_state.protocol_submitted:
            st.subheader("📝 Feedback")
            feedback = st.session_state.protocol_feedback
            
            cols = st.columns(3)
            with cols[0]:
                st.metric("Correct", len(feedback["correct"]), help="Properly identified protocols")
            with cols[1]:
                st.metric("Incorrect", len(feedback["incorrect"]), help="Unnecessary protocols selected")
            with cols[2]:
                st.metric("Missed", len(feedback["missed"]), help="Critical protocols overlooked")
        
        # --- Performance & Tools ---
        with st.expander("⚙️ Tools", expanded=True):
            cols = st.columns(2)
            with cols[0]:
                if st.button("💡 Get Hint (-1pt)", help="Reveal protocol clues", use_container_width=True):
                    if st.session_state.score > 0:
                        st.session_state.score = max(st.session_state.score - 1, 0)
                        st.session_state.show_hints = True
            with cols[1]:
                report = f"Report for {selected['name']}"
                st.download_button("📥 Download Report", report, file_name="dhs_report.md", use_container_width=True)

def process_question(selected, user_input):
    with st.spinner("🔍 Analyzing response..."):
        time.sleep(0.5)
        
        response_found = False
        for qa in selected["script"]:
            if user_input.strip().lower() == qa["question"].strip().lower():
                # Update conversation history
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": "You",
                    "content": user_input
                })
                st.session_state.conversation.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "role": selected["name"],
                    "content": qa["response"]
                })
                
                # Update score with bounds check (0-10)
                new_score = st.session_state.score + 2
                st.session_state.score = min(max(new_score, 0), 10)
                
                response_found = True
                break
        
        if not response_found:
            st.session_state.score = max(st.session_state.score - 1, 0)

if __name__ == "__main__":
    main()
