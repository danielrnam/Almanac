import streamlit as st
import datetime
import os
import io
import json
from PIL import Image
import google.auth
from google.genai import Client
from google.genai import types
from google.adk.runners import Runner
from google.adk.apps import App

from app.database import (
    init_db,
    save_user_profile,
    get_user_profile,
    add_plant,
    remove_plant,
    get_active_plants,
    save_watering_plan,
    get_watering_plans
)
from app.tools import get_coordinates
from app.agent import app as adk_app, root_agent
from app.plugins.model_armor import ModelArmorSafetyFilterPlugin
from app.app_utils import services

# Initialize database tables
init_db()

import re
import json
import asyncio
import logging

# Set up structured logging for intent-vs-outcome observability
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("almanac")

def log_intent_vs_outcome(intent: str, outcome: str):
    """Structured logger capturing agent intent versus outcome for robust distributed tracing and observability."""
    payload = {
        "event_type": "intent_vs_outcome",
        "agent_intent": intent,
        "agent_outcome": outcome,
        "timestamp": datetime.datetime.now().isoformat()
    }
    logger.info(json.dumps(payload))
    print(f"📝 [OBSERVABILITY LOG] {json.dumps(payload)}")


async def compact_session_history_async(session, selected_user_id: str):
    """Asynchronously compacts old session history when context turns exceed threshold (12 events),
    summarizing older messages to prevent memory context bloat and context-window token exhaustion."""
    if len(session.events) <= 12:
        return

    # Extract old events to summarize (e.g. first 8 events)
    old_events = session.events[:8]
    summary_prompt = "Summarize the following past conversation context between a gardening user and Almanac assistant into a single concise paragraph. Retain key plant states, coordinates, and watering rules:\n\n"
    for e in old_events:
        if e.content and e.content.parts:
            role = "User" if e.content.role == "user" else "Assistant"
            text = "".join([p.text or "" for p in e.content.parts])
            summary_prompt += f"{role}: {text}\n"

    try:
        # Perform asynchronous/non-blocking LLM call for summarization
        client = Client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3.6-flash",
            contents=summary_prompt
        )
        summary_text = f"🔄 [CONSOLIDATED MEMORY SUMMARY]: {response.text.strip()}"
        
        # Replace the first 8 events with a single summarized event in a non-blocking background thread
        from google.genai.types import Content, Part, Event
        summary_event = Event(
            content=Content(
                role="user",
                parts=[Part.from_text(text=summary_text)]
            )
        )
        
        # Update session events list
        session.events = [summary_event] + session.events[8:]
        print(f"Successfully compacted history for session {session.id}. Reduced token context bloat.")
    except Exception as e:
        print(f"Error during async history compaction: {e}")


def parse_schedule_json(text_plan: str) -> dict | None:
    """Helper to extract and parse a JSON block from the generated text plan."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text_plan, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return None

# Page Styling and Layout Configuration
st.set_page_config(
    page_title="Almanac | Smart Watering Assistant",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling
st.markdown("""
<style>
    .reportview-container {
        background: #fcfcfc;
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: 800;
        color: #1b4d3e;
        letter-spacing: -0.03em;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .card-container {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        margin-bottom: 1.5rem;
        border: 1px solid #eef2f0;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #2e7d32;
    }
    .tag-active {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .tag-warning {
        background-color: #fff3e0;
        color: #e65100;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# App Setup / GCP Credentials Helper
@st.cache_resource
def get_genai_client():
    try:
        # Attempts to resolve credentials from local environment
        credentials, _ = google.auth.default()
        return Client(vertexai=True)
    except Exception:
        # Fallback to local API key if available, else None
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            return Client(api_key=api_key)
    return None

client = get_genai_client()

# --- Sidebar: User Authentication & Mock Profile Switcher ---
st.sidebar.markdown("<h2 style='color:#1b4d3e; margin-bottom: 0px;'>👤 Profiles & Location</h2>", unsafe_allow_html=True)
st.sidebar.caption("Multi-tenant Mock Isolation & Settings")

# Default profiles for quick demonstration
DEFAULT_PROFILES = {
    "user_alice": "Alice (Seattle Garden - Hydrangeas, Herbs)",
    "user_bob": "Bob (Miami Yard - Tropical Palms, Ferns)",
    "user_charlie": "Charlie (Phoenix Xeriscape - Cactus, Succulents)"
}

# Seed default profiles in DB if they do not exist
for user_id, name in DEFAULT_PROFILES.items():
    if not get_user_profile(user_id):
        if user_id == "user_alice":
            save_user_profile(user_id, "Seattle, WA", 47.6062, -122.3321)
            # Seed Alice's starting plants
            add_plant(user_id, "Hydrangeas", "Mature", "Healthy")
            add_plant(user_id, "Rosemary Bush", "Established", "Dehydrated")
        elif user_id == "user_bob":
            save_user_profile(user_id, "Miami, FL", 25.7617, -80.1918)
            add_plant(user_id, "Areca Palm", "Mature", "Healthy")
            add_plant(user_id, "Ferns", "Seedling", "Water-stressed")
        elif user_id == "user_charlie":
            save_user_profile(user_id, "Phoenix, AZ", 33.4484, -112.0740)
            add_plant(user_id, "Saguaro Cactus", "Established", "Healthy")
            add_plant(user_id, "Agave", "Mature", "Healthy")

# Add a custom profile option
all_profiles = list(DEFAULT_PROFILES.keys())
selected_user_id = st.sidebar.selectbox(
    "Active Account",
    all_profiles,
    format_func=lambda x: DEFAULT_PROFILES.get(x, x)
)

# Fetch current profile details
profile = get_user_profile(selected_user_id)
location_name = profile["location_name"] if profile else "Unknown Location"
lat = profile["latitude"] if profile else 0.0
lng = profile["longitude"] if profile else 0.0

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Current Location:** `{location_name}`")
st.sidebar.caption(f"Coordinates: {lat:.4f}, {lng:.4f}")

# Update location input
with st.sidebar.expander("🗺️ Update Location"):
    new_loc = st.text_input("Enter City, State / Country", value=location_name)
    if st.button("Set Location"):
        with st.spinner("Geocoding..."):
            coords = get_coordinates(new_loc)
            if coords:
                save_user_profile(selected_user_id, coords["name"], coords["latitude"], coords["longitude"])
                st.sidebar.success(f"Updated location to {coords['name']}!")
                st.rerun()
            else:
                st.sidebar.error("Could not find location. Please be more specific.")

# --- Main Layout ---
st.markdown("<div class='main-header'>🌱 Almanac Smart Yard Watering</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Personalized 7-day watering schedules generated parallelly through multi-agent coordination. Built with Google ADK.</div>", unsafe_allow_html=True)

# Grid Layout for Workspace
col_inventory, col_planner = st.columns([1.1, 1.4])

# --- Column 1: Garden Premises & Inventory ---
with col_inventory:
    st.markdown("### 🏡 Active Yard Inventory")
    active_plants = get_active_plants(selected_user_id)
    
    if not active_plants:
        st.info("Your yard is currently empty. Add some plants below using a photo or manual description!")
    else:
        for plant in active_plants:
            with st.container():
                st.markdown(f"""
                <div class='card-container'>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <strong style='font-size: 1.15rem; color:#1b4d3e;'>🌿 {plant['name']}</strong>
                        <span class="{'tag-warning' if plant['health_state'].lower() in ['wilted', 'dehydrated', 'water-stressed'] else 'tag-active'}">
                            {plant['health_state']}
                        </span>
                    </div>
                    <div style='margin-top: 0.5rem; color:#555; font-size: 0.9rem;'>
                        <strong>Maturity:</strong> {plant['maturity']} | 
                        <strong>Added:</strong> {plant['added_at'][:10]}
                        {f"<br><strong>Care Notes:</strong> <span style='color:#1565C0; font-style:italic;'>{plant['watering_guidelines']}</span>" if plant.get('watering_guidelines') else ""}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Delete button positioned neatly
                if st.button(f"🗑️ Remove {plant['name']}", key=f"del_{plant['id']}", use_container_width=True):
                    remove_plant(selected_user_id, plant["id"])
                    st.toast(f"Removed {plant['name']} from your premises.")
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📷 Add New Plant")
    
    # Vision & upload methods
    upload_method = st.radio("Add via:", ["Mobile Camera Snap 🤳", "Upload Garden Photo 🖼️", "Manual Description ✏️"])
    
    # Use session state to persist computer vision analysis across form submit runs
    if "cv_name" not in st.session_state:
        st.session_state.cv_name = ""
    if "cv_maturity" not in st.session_state:
        st.session_state.cv_maturity = "Mature"
    if "cv_health" not in st.session_state:
        st.session_state.cv_health = "Healthy"
    
    image_bytes = None
    
    if upload_method == "Mobile Camera Snap 🤳":
        camera_img = st.camera_input("Snap a live photo of the plant")
        if camera_img:
            image_bytes = camera_img.getvalue()
            
    elif upload_method == "Upload Garden Photo 🖼️":
        uploaded_file = st.file_uploader("Choose a photo of the plant", type=["png", "jpg", "jpeg"])
        if uploaded_file:
            image_bytes = uploaded_file.getvalue()
            st.image(uploaded_file, caption="Selected Plant", use_container_width=True)

    # Trigger Vertex AI computer vision model to analyze plant if photo is supplied
    if image_bytes and client:
        if st.button("🔍 Run Computer Vision Analysis on Photo", use_container_width=True):
            with st.spinner("Gemini Multimodal analyzing plant photo..."):
                try:
                    # Convert to PIL for SDK compatibility
                    pil_img = Image.open(io.BytesIO(image_bytes))
                    
                    prompt = (
                        "Analyze this plant photo. Provide the output in clean JSON format matching "
                        "this schema exactly: {\"name\": \"plant name\", \"maturity\": \"seedling, mature, or established\", "
                        "\"health\": \"healthy, wilted, dehydrated, or water-stressed\"}. Do not write markdown blocks or backticks."
                    )
                    
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[pil_img, prompt]
                    )
                    
                    # Parse the vision analysis
                    res_text = response.text.strip()
                    if "```" in res_text:
                        res_text = res_text.split("```")[1]
                        if res_text.startswith("json"):
                            res_text = res_text[4:]
                    res_text = res_text.strip()
                    
                    parsed_analysis = json.loads(res_text)
                    st.session_state.cv_name = parsed_analysis.get("name", "Unknown Species")
                    st.session_state.cv_maturity = parsed_analysis.get("maturity", "Mature").capitalize()
                    st.session_state.cv_health = parsed_analysis.get("health", "Healthy").capitalize()
                    
                    st.success(f"Detected: **{st.session_state.cv_name}** ({st.session_state.cv_maturity}, {st.session_state.cv_health})")
                    
                except Exception as e:
                    st.error(f"Failed to analyze image using Vertex AI: {e}. You can enter details manually below.")
                    st.session_state.cv_name = "Generic Plant"

    # Plant Entry Form
    with st.form("add_plant_form", clear_on_submit=True):
        p_name = st.text_input("Plant Name / Species", value=st.session_state.cv_name)
        p_maturity = st.selectbox("Maturity", ["Seedling", "Mature", "Established"], 
                                  index=["Seedling", "Mature", "Established"].index(st.session_state.cv_maturity))
        p_health = st.selectbox("Health State", ["Healthy", "Wilted", "Dehydrated", "Water-stressed"], 
                                index=["Healthy", "Wilted", "Dehydrated", "Water-stressed"].index(st.session_state.cv_health))
        
        p_guidelines = st.text_input("Custom Watering Guidelines / Care Notes (Optional)", placeholder="e.g. Tomato should be watered until water drains under the pot")
        
        submit_plant = st.form_submit_button("➕ Confirm & Save to Yard", use_container_width=True)
        if submit_plant:
            if not p_name:
                st.error("Please provide a plant name.")
            else:
                add_plant(selected_user_id, p_name, p_maturity, p_health, watering_guidelines=p_guidelines)
                # Clear session state for next plant entry
                st.session_state.cv_name = ""
                st.session_state.cv_maturity = "Mature"
                st.session_state.cv_health = "Healthy"
                st.success(f"Added {p_name} successfully!")
                st.rerun()

# --- Column 2: Water Schedule Planner & Chat ---
with col_planner:
    st.markdown("### 🗓️ Smart 7-Day Watering Schedule")
    
    # Query latest plans from database
    historical_plans = get_watering_plans(selected_user_id)
    active_plants = get_active_plants(selected_user_id)
    
    # Render the latest plan persistently
    if historical_plans:
        latest_plan = historical_plans[0]
        text_plan = latest_plan["schedule_data"].get("text_plan", "")
        
        st.markdown(f"#### 🎉 Latest Compiled Plan")
        st.info(f"📅 **Start Date:** {latest_plan['start_date']} (Compiled: {latest_plan['generated_at'][:16]})")
        
        # Parse and display the horizontal 7-day visual schedule grid
        schedule_json = parse_schedule_json(text_plan)
        if schedule_json:
            st.markdown("##### 📅 Weekly Visual Calendar")
            days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            cols = st.columns(7)
            for i, day in enumerate(days_of_week):
                with cols[i]:
                    # Render nice bold abbreviated day names with customized background feel
                    st.markdown(f"**{day[:3]}**")
                    plants_to_water = schedule_json.get(day, [])
                    if plants_to_water:
                        for plant in plants_to_water:
                            st.markdown(f"<span style='color:#2E7D32; font-weight:600;'>💧 {plant}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='color:#757575; font-style:italic;'>☀️ Clear</span>", unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)
            
        with st.expander("📖 View Full Detailed Report & Reasoning"):
            st.markdown(text_plan)
            st.caption(f"**Reasoning Details:** {latest_plan['reasoning_summary']}")
    else:
        st.info("No active watering plan found. Click the button below to coordinate agents and compile one!")

    if "pending_plan" not in st.session_state:
        st.session_state.pending_plan = None

    # Human-in-the-Loop (HITL) Verification Card
    if st.session_state.pending_plan:
        st.markdown("""
        <div style='background-color:#E3F2FD; border-left: 6px solid #1565C0; padding: 15px; border-radius: 4px; margin-bottom: 20px;'>
            <strong style='color:#0D47A1; font-size:1.1rem;'>⚠️ Human-in-the-Loop (HITL) Authorization Required</strong><br>
            <span style='color:#1565C0;'>Almanac's multi-agent team has generated a tentative schedule. Please review and authorize below before committing this schedule to your official database.</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 📋 Propose Schedule Recommendations")
        st.markdown(st.session_state.pending_plan["text_plan"])
        st.caption(f"**Generated Reasoning Summary**: {st.session_state.pending_plan['summary']}")
        
        # User confirmation checkbox represents human verification gate
        hitl_authorized = st.checkbox("👉 I have reviewed these recommendations and authorize applying this plan to my premises.")
        
        col_hitl_ok, col_hitl_cancel = st.columns(2)
        with col_hitl_ok:
            if st.button("✅ Authorize & Commit to Yard", type="primary", disabled=not hitl_authorized, use_container_width=True):
                # Save plan to DB only after user authorization
                save_watering_plan(
                    user_id=selected_user_id,
                    start_date=datetime.date.today().isoformat(),
                    schedule_data={"text_plan": st.session_state.pending_plan["text_plan"]},
                    reasoning_summary=st.session_state.pending_plan["summary"]
                )
                log_intent_vs_outcome(
                    intent="Apply authorized watering plan to DB",
                    outcome="Plan successfully committed to SQLite after explicit human-in-the-loop validation."
                )
                st.session_state.pending_plan = None
                st.success("Plan committed successfully!")
                st.rerun()
        with col_hitl_cancel:
            if st.button("❌ Discard Plan", type="secondary", use_container_width=True):
                log_intent_vs_outcome(
                    intent="User choice: discard plan",
                    outcome="Proposed plan discarded by user operator."
                )
                st.session_state.pending_plan = None
                st.rerun()
                
        st.markdown("---")

    # Active plan button
    if st.button("🚀 Coordinate Agents & Compile 7-Day Watering Plan", type="primary", use_container_width=True):
        if not active_plants:
            st.error("Cannot generate plan: Your yard currently has no active plants! Add some first.")
        else:
            with st.spinner("Orchestrator (gemini-2.5-pro) coordinating weather & botanical leaf-agents parallelly..."):
                try:
                    # Construct clean inputs context for the Orchestrator with custom guidelines
                    plants_summary = "\n".join([
                        f"- Name: {p['name']}, Maturity: {p['maturity']}, State: {p['health_state']}" +
                        (f" (Watering Guideline: {p['watering_guidelines']})" if p.get('watering_guidelines') else "")
                        for p in active_plants
                    ])
                    
                    prompt = (
                        f"Generate a 7-day watering plan for my premises.\n"
                        f"Location: {location_name} (Lat: {lat}, Lng: {lng})\n"
                        f"My Active Plants:\n{plants_summary}\n"
                        f"Current Date: {datetime.date.today().strftime('%B %d, %Y')}"
                    )
                    
                    # Log Agent Intent
                    log_intent_vs_outcome(
                        intent=f"Coordinate multi-agent planning over {len(active_plants)} plants using Pro reasoning and parallel weather fetches.",
                        outcome="Dispatched parallel tool coordinates and forecast actions to background threads."
                    )
                    
                    # Local execution of the ADK App using local Runner
                    runner = Runner(
                        app=adk_app,
                        session_service=services.get_session_service(),
                        artifact_service=services.get_artifact_service(),
                        auto_create_session=True,
                    )
                    
                    # Standard ADK run sequence matching verified integration tests
                    session_service = services.get_session_service()
                    session_id = f"user-session-{selected_user_id}"
                    session = session_service.get_session_sync(app_name="app", user_id=str(selected_user_id), session_id=session_id)
                    if session is None:
                        session = session_service.create_session_sync(app_name="app", user_id=str(selected_user_id), session_id=session_id)
                    
                    from google.genai import types
                    message = types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)]
                    )
                    
                    # Run the agent in a non-blocking asynchronous thread to prevent UI lockups
                    events = asyncio.run(asyncio.to_thread(
                        lambda: list(
                            runner.run(
                                new_message=message,
                                user_id=selected_user_id,
                                session_id=session.id,
                            )
                        )
                    ))
                    
                    # Collate response parts from events
                    response_text_parts = []
                    for event in events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if part.text:
                                    response_text_parts.append(part.text)
                    response_content = "".join(response_text_parts)
                    
                    # Log Agent Outcome and hold for review
                    log_intent_vs_outcome(
                        intent="Synthesize 7-day watering calendar",
                        outcome=f"Successfully compiled plan ({len(response_content)} chars). Now holding for user HITL verification."
                    )
                    
                    # Hold plan for review (HITL) instead of immediate auto-save
                    st.session_state.pending_plan = {
                        "text_plan": response_content,
                        "summary": f"Synthesized 7-day schedule for {len(active_plants)} plants."
                    }
                    st.toast("Watering plan compiled! Please authorize below.")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error compiling watering plan: {e}")

    # --- Interactive Chat Section ---
    st.markdown("---")
    st.markdown("### 💬 Chat with Almanac Orchestrator")
    st.caption("Discuss the watering recommendations, adjust schedules, or ask garden care questions with memory context.")
    
    session_service = services.get_session_service()
    session_id = f"user-session-{selected_user_id}"
    session = session_service.get_session_sync(app_name="app", user_id=str(selected_user_id), session_id=session_id)
    if session is None:
        session = session_service.create_session_sync(app_name="app", user_id=str(selected_user_id), session_id=session_id)
        
    # Display message history from session events
    for event in session.events:
        msg = event.content
        if msg and msg.parts:
            # Skip internal/system-heavy planning prompts to keep chat conversational
            if msg.role == "user" and any(p.text and "Generate a 7-day watering plan" in p.text for p in msg.parts):
                continue
            role = "user" if msg.role == "user" else "assistant"
            text = "".join([p.text or "" for p in msg.parts]).strip()
            if text:
                with st.chat_message(role):
                    st.markdown(text)
                
    # Chat Input Box
    chat_query = st.chat_input("Ask Almanac about your plants or schedule...")
    if chat_query:
        with st.chat_message("user"):
            st.markdown(chat_query)
            
        with st.chat_message("assistant"):
            with st.spinner("Almanac considering..."):
                try:
                    # Log Agent Chat Intent
                    log_intent_vs_outcome(
                        intent=f"Formulate conversational chat answer for query: '{chat_query}'",
                        outcome="Invoking ADK agent runner on a background non-blocking thread."
                    )
                    
                    # Execute runner
                    runner = Runner(
                        app=adk_app,
                        session_service=services.get_session_service(),
                        artifact_service=services.get_artifact_service(),
                        auto_create_session=True,
                    )
                    from google.genai import types
                    user_msg = types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=chat_query)]
                    )
                    
                    # Run the agent in a non-blocking asynchronous thread to prevent UI lockups
                    events = asyncio.run(asyncio.to_thread(
                        lambda: list(
                            runner.run(
                                new_message=user_msg,
                                user_id=selected_user_id,
                                session_id=session.id,
                            )
                        )
                    ))
                    
                    reply_parts = []
                    for event in events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if part.text:
                                    reply_parts.append(part.text)
                    reply_text = "".join(reply_parts)
                    
                    # Log Agent Chat Outcome
                    log_intent_vs_outcome(
                        intent="Respond to conversational query",
                        outcome=f"Successfully generated reply ({len(reply_text)} chars)."
                    )
                    
                    # Run memory compaction asynchronously in the background to prevent context bloat
                    asyncio.run(compact_session_history_async(session, selected_user_id))
                    
                    st.markdown(reply_text)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error communicating with agent: {e}")

    # --- Archival Section ---
    if len(historical_plans) > 1:
        st.markdown("---")
        st.markdown("### 📜 Watering History & Archives")
        for plan in historical_plans[1:]:
            with st.expander(f"📅 Plan Generated: {plan['generated_at'][:19]} ({plan['start_date']})"):
                text_plan = plan["schedule_data"].get("text_plan", "")
                st.markdown(text_plan)
                st.caption(f"Reasoning Details: {plan['reasoning_summary']}")
