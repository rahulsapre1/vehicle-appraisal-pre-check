"""
Vehicle Appraisal Pre-Check - Streamlit UI
Streamlit UI for submitting appraisals and viewing results.
"""
import os
import json
import uuid
import time
import requests
from datetime import datetime
from typing import Any

import streamlit as st

# Import custom components and utilities
from utils.styling import inject_custom_css
from components.header import render_header, render_hero_section, render_feature_cards


# Configuration
_raw_api_url = os.getenv("API_BASE_URL", "http://localhost:8000")

# Smart URL construction for Render and other platforms
if _raw_api_url and not _raw_api_url.startswith(("http://", "https://")):
    if "." not in _raw_api_url and _raw_api_url != "localhost":
        API_BASE_URL = f"https://{_raw_api_url}.onrender.com"
    else:
        API_BASE_URL = f"https://{_raw_api_url}"
else:
    API_BASE_URL = _raw_api_url


def format_timestamp(ts: str | None, include_ms: bool = False) -> str:
    """Format ISO timestamp for display."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if include_ms:
            return dt.strftime("%H:%M:%S.%f")[:-3]
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def normalize_file_content_type(file, content_type: str | None) -> str:
    """Normalize content type for file uploads."""
    import mimetypes
    
    if content_type:
        content_lower = content_type.lower()
        if content_lower == "image/jpg":
            return "image/jpeg"
        if content_lower in ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]:
            return content_lower
    
    if hasattr(file, 'name') and file.name:
        guessed_type, _ = mimetypes.guess_type(file.name)
        if guessed_type:
            if guessed_type.lower() == "image/jpg":
                return "image/jpeg"
            return guessed_type.lower()
        
        ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
        ext_to_type = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
            'heic': 'image/heic',
            'heif': 'image/heif',
        }
        if ext in ext_to_type:
            return ext_to_type[ext]
    
    return content_type or "image/jpeg"


def call_api(method: str, endpoint: str, **kwargs) -> tuple[bool, Any]:
    """Make API call and return (success, data/error)."""
    url = f"{API_BASE_URL}{endpoint}"
    api_timeout = int(os.getenv("API_TIMEOUT_SECONDS", "60"))
    
    if "timeout" not in kwargs:
        kwargs["timeout"] = api_timeout
    
    try:
        resp = requests.request(method, url, **kwargs)
        if resp.status_code < 400:
            return True, resp.json()
        else:
            # Try to parse JSON error response, fallback to text
            try:
                error_data = resp.json()
                error_message = error_data.get("error", resp.text)
            except (ValueError, KeyError):
                error_message = resp.text
            return False, {"error": error_message, "status_code": resp.status_code}
    except requests.exceptions.Timeout:
        return False, {"error": f"Request timeout after {api_timeout}s. The API may be starting up. Please try again."}
    except requests.exceptions.ConnectionError as e:
        error_msg = str(e)
        if "Name or service not known" in error_msg or "Failed to resolve" in error_msg:
            return False, {"error": f"Cannot connect to API at {url}. Please check API_BASE_URL is set correctly."}
        return False, {"error": f"Connection error: {error_msg}"}
    except Exception as e:
        return False, {"error": str(e)}


def main():
    st.set_page_config(
        page_title="Vehicle Appraisal Pre-Check",
        page_icon="🚗",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize session state
    if "initialized" not in st.session_state:
        st.session_state["initialized"] = True
        st.session_state["current_page"] = "home"
        st.session_state["waiting_for_analysis"] = False
        st.session_state["page_transition"] = False
        st.session_state["staged_photos"] = []
        st.session_state["current_appraisal_id"] = None
        st.session_state["appraisal_metadata"] = {}
        st.session_state["upload_counter"] = 0
    
    # Inject custom CSS
    inject_custom_css()
    
    # Priority check: If analysis is waiting, show simple message and redirect
    if st.session_state.get("waiting_for_analysis"):
        # Clear form state
        st.session_state["staged_photos"] = []
        st.session_state["current_appraisal_id"] = None
        st.session_state["appraisal_metadata"] = {}
        st.session_state["upload_counter"] = 0
        st.session_state["last_uploaded_filename"] = None
        
        show_analysis_waiting_screen()
        st.stop()
        return
    
    # Check if we're in a transition state
    if st.session_state.get("page_transition"):
        target_page = st.session_state.get("target_page", "home")
        st.session_state["current_page"] = target_page
        st.session_state["page_transition"] = False
        st.rerun()
        return
    
    # Get current page from query params or session state
    query_params = st.query_params
    if query_params.get("page"):
        current_page = query_params.get("page")[0] if isinstance(query_params.get("page"), list) else query_params.get("page")
        st.session_state["current_page"] = current_page
    else:
        current_page = st.session_state.get("current_page", "home")
    
    # Render header navigation
    render_header(current_page)
    
    # Route to appropriate page
    if current_page == "home":
        show_home_page()
    elif current_page == "submit":
        show_submission_form()
    elif current_page == "view":
        show_appraisal_viewer()
    else:
        show_home_page()


def show_home_page():
    """Display the home/landing page."""
    if st.session_state.get("current_page") not in ["home", None]:
        return
    
    render_hero_section()
    
    st.markdown("---")
    st.markdown("### What This Does")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%); padding: 28px; border-radius: 12px; border-left: 5px solid #0066cc; margin-bottom: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <div style="display: flex; align-items: start; gap: 16px;">
            <div style="font-size: 32px; line-height: 1;">🎯</div>
            <div style="flex: 1;">
                <p style="font-size: 17px; line-height: 1.7; color: #2c3e50; margin: 0 0 12px 0; font-weight: 500;">
                    <strong>Automates pre-processing</strong> to ensure sufficient evidence before appraisal begins
                </p>
                <p style="font-size: 15px; line-height: 1.6; color: #495057; margin: 0;">
                    Validates photo coverage, extracts vehicle data, checks completeness, and calculates readiness—preventing 
                    incomplete submissions from reaching human appraisers.
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### Technologies Behind It")
    render_feature_cards()
    
    st.markdown("---")
    st.markdown("### How to Use")
    
    steps = [
        {"number": "1", "title": "Create Appraisal", "description": "Enter vehicle details (year, make, model) and any notes"},
        {"number": "2", "title": "Upload Photos", "description": "Upload up to 3 photos (front, rear, sides, interior, odometer, etc.)"},
        {"number": "3", "title": "AI Analysis", "description": "System extracts data, checks completeness, and calculates readiness score (~2 minutes)"},
        {"number": "4", "title": "Review Results", "description": "View readiness score, missing evidence, risk flags, and next steps"}
    ]
    
    step_cols = st.columns(2)
    for i, step in enumerate(steps):
        col = step_cols[i % 2]
        with col:
            step_html = f'''
            <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 16px; border-left: 4px solid #0066cc;">
                <div style="display: flex; align-items: start; gap: 12px;">
                    <div style="background: #0066cc; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; flex-shrink: 0;">
                        {step["number"]}
                    </div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; font-size: 16px; color: #2c3e50; margin-bottom: 4px;">
                            {step["title"]}
                        </div>
                        <div style="font-size: 14px; color: #6c757d; line-height: 1.5;">
                            {step["description"]}
                        </div>
                    </div>
                </div>
            </div>
            '''
            st.markdown(step_html, unsafe_allow_html=True)


def show_submission_form():
    """Display appraisal submission form."""
    if st.session_state.get("current_page") != "submit":
        return
    
    if st.session_state.get("analysis_started"):
        st.session_state["analysis_started"] = False
        st.session_state["page_transition"] = True
        st.session_state["target_page"] = "view"
        st.rerun()
        return
    
    st.markdown('<h1 style="margin-bottom: 2rem;">Submit New Appraisal</h1>', unsafe_allow_html=True)
    
    # Initialize session state for photo staging
    if "staged_photos" not in st.session_state:
        st.session_state["staged_photos"] = []
    if "current_appraisal_id" not in st.session_state:
        st.session_state["current_appraisal_id"] = None
    if "appraisal_metadata" not in st.session_state:
        st.session_state["appraisal_metadata"] = {}
    if "upload_counter" not in st.session_state:
        st.session_state["upload_counter"] = 0
    
    # Step 1: Vehicle Metadata
    st.subheader("Step 1: Vehicle Information")
    with st.form("metadata_form"):
        col1, col2 = st.columns(2)
        with col1:
            year = st.number_input("Year", min_value=1900, max_value=2030, value=2020)
            make = st.text_input("Make", placeholder="e.g., Toyota")
            model = st.text_input("Model", placeholder="e.g., Camry")
        
        with col2:
            trim = st.text_input("Trim (optional)", placeholder="e.g., LE")
            mileage = st.number_input("Mileage (optional)", min_value=0, value=0)
            color = st.text_input("Color (optional)", placeholder="e.g., Silver")
        
        st.subheader("Appraiser Notes")
        notes = st.text_area(
            "Notes",
            placeholder="Describe the vehicle condition, damage, special features, etc.",
            height=150,
        )
        
        submitted = st.form_submit_button("Create Appraisal", type="primary")
        
        if submitted:
            if not make or not model:
                st.error("❌ Make and Model are required")
                return
            
            metadata = {
                "year": year,
                "make": make,
                "model": model,
            }
            if trim:
                metadata["trim"] = trim
            if mileage > 0:
                metadata["mileage"] = mileage
            if color:
                metadata["color"] = color
            
            with st.spinner("Creating appraisal..."):
                success, result = call_api(
                    "POST", 
                    "/api/appraisals/create",
                    json={
                        "metadata_json": metadata,
                        "notes_raw": notes
                    }
                )
            
            if success:
                appraisal_id = result.get("id")
                st.session_state["current_appraisal_id"] = appraisal_id
                st.session_state["last_appraisal_id"] = appraisal_id
                st.session_state["appraisal_metadata"] = metadata
                st.session_state["appraisal_notes"] = notes
                st.session_state["staged_photos"] = []
                st.success(f"✅ Appraisal created! Reference: **{appraisal_id}**")
                st.info(f"🔑 **Save this ID for viewing results:** `{appraisal_id}`")
                st.caption("Copy the ID above to view this appraisal later")
                st.rerun()
            else:
                st.error(f"❌ Failed to create appraisal: {result.get('error', 'Unknown error')}")
    
    # Step 2: Photo Upload
    if st.session_state["current_appraisal_id"]:
        st.markdown("---")
        st.subheader("Step 2: Upload Photos")
        appraisal_id = st.session_state["current_appraisal_id"]
        
        metadata = st.session_state["appraisal_metadata"]
        st.info(f"📝 {metadata.get('year')} {metadata.get('make')} {metadata.get('model')} - Reference: **{appraisal_id}**")
        
        staged_photos = st.session_state["staged_photos"]
        if staged_photos:
            st.write(f"**{len(staged_photos)} photo(s) uploaded:**")
            cols = st.columns(min(len(staged_photos), 4))
            for i, photo_info in enumerate(staged_photos):
                with cols[i % 4]:
                    status_icon = "✅" if photo_info.get("status") == "processing" else "⏳"
                    st.write(f"{status_icon} {photo_info.get('filename', 'Photo')[:20]}")
        
        if "last_uploaded_filename" not in st.session_state:
            st.session_state["last_uploaded_filename"] = None
        
        uploaded_file = st.file_uploader(
            f"📸 Select photo to upload (max 3, currently {len(staged_photos)}/3)",
            type=["jpg", "jpeg", "png", "heic", "heif"],
            accept_multiple_files=False,
            key=f"photo_uploader_{st.session_state['upload_counter']}",
            disabled=len(staged_photos) >= 3,
            label_visibility="visible"
        )
        
        if uploaded_file is not None and len(staged_photos) < 3:
            if st.session_state["last_uploaded_filename"] != uploaded_file.name:
                st.session_state["last_uploaded_filename"] = uploaded_file.name
                
                with st.spinner(f"⬆️ Uploading {uploaded_file.name}..."):
                    files = [("photo", (uploaded_file.name, uploaded_file, normalize_file_content_type(uploaded_file, uploaded_file.type)))]
                    success, result = call_api(
                        "POST",
                        f"/api/appraisals/{appraisal_id}/photos/upload",
                        files=files
                    )
                
                if success:
                    st.session_state["staged_photos"].append({
                        "filename": uploaded_file.name,
                        "artifact_id": result.get("artifact_id"),
                        "status": "processing"
                    })
                    st.session_state["upload_counter"] += 1
                    st.session_state["last_uploaded_filename"] = None
                    st.toast(f"✅ {uploaded_file.name} uploaded!", icon="✅")
                    st.rerun()
                else:
                    st.error(f"❌ Upload failed: {result.get('error', 'Unknown error')}")
                    st.session_state["last_uploaded_filename"] = None
        
        if len(staged_photos) >= 3:
            st.warning("⚠️ Maximum 3 photos reached")
        
        # Step 3: Request Appraisal
        st.markdown("---")
        st.subheader("Step 3: Request AI Analysis")
        
        min_photos_required = 1
        can_request_appraisal = len(staged_photos) >= min_photos_required
        
        if not can_request_appraisal:
            st.info(f"ℹ️ Upload at least {min_photos_required} photo to request analysis. ({len(staged_photos)}/{min_photos_required})")
        
        if st.button(
            "🚀 Start AI Analysis",
            disabled=not can_request_appraisal,
            type="primary",
            use_container_width=True
        ):
            with st.spinner("Starting AI analysis..."):
                idempotency_key = str(uuid.uuid4())
                success, result = call_api(
                    "POST",
                    f"/api/appraisals/{appraisal_id}/run",
                    headers={"Idempotency-Key": idempotency_key},
                )
            
            if success:
                completed_appraisal_id = appraisal_id
                
                st.session_state["current_appraisal_id"] = None
                st.session_state["staged_photos"] = []
                st.session_state["appraisal_metadata"] = {}
                st.session_state["upload_counter"] = 0
                st.session_state["last_uploaded_filename"] = None
                
                # Show waiting screen briefly, then user can navigate to View Appraisal
                st.session_state["waiting_for_analysis"] = True
                st.session_state["waiting_appraisal_id"] = completed_appraisal_id
                st.session_state["last_appraisal_id"] = completed_appraisal_id
                
                st.rerun()
            else:
                st.error(f"❌ Failed to start analysis: {result.get('error', 'Unknown error')}")
        
        if st.button("🗑️ Cancel & Start New"):
            st.session_state["current_appraisal_id"] = None
            st.session_state["staged_photos"] = []
            st.session_state["appraisal_metadata"] = {}
            st.session_state["upload_counter"] = 0
            st.rerun()


def show_analysis_waiting_screen():
    """Display simple message to check View Appraisals in 2 minutes."""
    appraisal_id = st.session_state.get("waiting_appraisal_id", "")
    short_id = appraisal_id  # Use the short ID for display
    
    # Simple centered message
    st.markdown("""
    <div style="text-align: center; padding: 5rem 2rem;">
    """, unsafe_allow_html=True)
    
    st.markdown('<h1 style="margin-bottom: 2rem; font-size: 3rem;">✅ Analysis Started!</h1>', unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="background: #e7f3ff; border: 2px solid #0066cc; border-radius: 12px; padding: 2rem; margin: 2rem auto; max-width: 600px;">
        <p style="font-size: 1.2rem; margin-bottom: 1rem;">
            Your appraisal <strong>{short_id}</strong> is being analyzed.
        </p>
        <p style="font-size: 1.1rem; color: #333;">
            ⏱️ Please check <strong>"View Appraisal"</strong> in approximately <strong>2 minutes</strong> to see the results.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Button to go to View Appraisal
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("📊 View Appraisal Now", type="primary", use_container_width=True, key="go_to_view"):
            st.session_state["waiting_for_analysis"] = False
            st.session_state["current_page"] = "view"
            st.session_state["last_appraisal_id"] = appraisal_id
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)


def show_appraisal_viewer():
    """Display appraisal details and results."""
    if st.session_state.get("current_page") != "view":
        return
    
    if "analysis_started" in st.session_state:
        st.session_state["analysis_started"] = False
    
    st.markdown('<h1 style="margin-bottom: 2rem;">View Appraisal Results</h1>', unsafe_allow_html=True)
    
    with st.container():
        st.markdown("### Enter Appraisal ID")
        default_id = st.session_state.get("last_appraisal_id", "")
        
        input_id = st.text_input(
            "ID", 
            value=default_id if default_id else "", 
            label_visibility="collapsed", 
            placeholder="Enter 4-character reference (e.g., QE43) or full ID"
        )
    
    if not input_id:
        st.info("💡 Enter your appraisal reference to view details")
        return
    
    appraisal_id = input_id.strip()
    
    with st.spinner("Loading appraisal..."):
        success, data = call_api("GET", f"/api/appraisals/{appraisal_id}")
    
    if not success:
        st.error(f"❌ Failed to load appraisal: {data.get('error', 'Unknown error')}")
        return
    
    appraisal = data.get("appraisal", {})
    latest_run = data.get("latest_run")
    
    short_id = appraisal.get("short_id", appraisal_id)
    
    metadata = appraisal.get("metadata_json", {})
    run_status = latest_run.get("status", "").upper() if latest_run else None
    is_running = run_status in ["PENDING", "RUNNING", "IN_PROGRESS"]
    
    if is_running:
        show_analysis_progress(latest_run, short_id)
        # Auto-check every 2 seconds
        if "last_status_check" not in st.session_state:
            st.session_state["last_status_check"] = time.time()
        
        current_time = time.time()
        if current_time - st.session_state["last_status_check"] >= 2:
            st.session_state["last_status_check"] = current_time
            # Re-check status
            success, data = call_api("GET", f"/api/appraisals/{appraisal_id}")
            if success:
                latest_run_new = data.get("latest_run")
                if latest_run_new:
                    run_status_new = latest_run_new.get("status", "").upper()
                    if run_status_new not in ["PENDING", "RUNNING", "IN_PROGRESS"]:
                        st.rerun()
                        return
        
        time.sleep(2)
        st.rerun()
        return
    
    col_header1, col_header2 = st.columns([3, 1])
    with col_header1:
        st.markdown(f"## {metadata.get('year')} {metadata.get('make')} {metadata.get('model')}")
        caption_parts = []
        if metadata.get('trim'):
            caption_parts.append(metadata.get('trim'))
        if metadata.get('color'):
            caption_parts.append(metadata.get('color'))
        if metadata.get('mileage'):
            caption_parts.append(f"{metadata.get('mileage'):,} miles")
        
        if caption_parts:
            st.caption(" • ".join(caption_parts))
    with col_header2:
        st.markdown(f"""
        <div style="background: #e7f3ff; border: 2px solid #0066cc; border-radius: 8px; padding: 8px 16px; text-align: center; margin-top: 8px;">
            <div style="font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px;">Reference</div>
            <div style="font-size: 24px; font-weight: bold; color: #0066cc; letter-spacing: 2px; font-family: monospace;">{short_id}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Make tabs more visible with custom styling
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f0f2f6;
        padding: 8px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 10px 20px;
        background-color: white;
        border-radius: 6px;
        font-weight: 600;
        font-size: 16px;
        border: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0066cc;
        color: white;
        border-color: #0066cc;
    }
    .stTabs [aria-selected="false"] {
        background-color: white;
        color: #333;
        border-color: #ddd;
    }
    </style>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Analysis Results", "📸 Photos", "📝 Notes & Details", "🔍 Event Log (Dev)"])
    
    with tab1:
        if latest_run and run_status == "COMPLETED":
            display_run_results(latest_run, appraisal_id, metadata, appraisal)
        elif latest_run and run_status == "FAILED":
            st.error("❌ Analysis failed. Please try again or contact support.")
            if st.button("🔄 Refresh to Check Status", use_container_width=True):
                st.rerun()
        else:
            # Show processing status
            st.markdown("""
            <div style="background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%); border: 2px solid #0066cc; border-radius: 12px; padding: 2rem; text-align: center; margin: 2rem 0;">
                <h3 style="color: #0066cc; margin-bottom: 1rem;">🔄 Processing</h3>
                <p style="font-size: 1rem; color: #333; margin: 0;">
                    Analysis is in progress. Results will appear here automatically when ready (typically within 2 minutes).
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # Auto-check every 2 seconds for completion
            if "last_tab_check_time" not in st.session_state:
                st.session_state["last_tab_check_time"] = time.time()
            
            current_time = time.time()
            if current_time - st.session_state["last_tab_check_time"] >= 2:
                st.session_state["last_tab_check_time"] = current_time
                # Re-check status
                success, data = call_api("GET", f"/api/appraisals/{appraisal_id}")
                if success:
                    latest_run_new = data.get("latest_run")
                    if latest_run_new:
                        run_status_new = latest_run_new.get("status", "").upper()
                        if run_status_new in ["COMPLETED", "FAILED"]:
                            st.rerun()
                            return
            
            with st.spinner("Analyzing..."):
                time.sleep(2)
                st.rerun()
    
    with tab2:
        # Load photos first to get vision outputs
        with st.spinner("Loading photos..."):
            success_photos, photos_data = call_api("GET", f"/api/appraisals/{appraisal_id}/photos")
        
        if not success_photos:
            st.error("Failed to load photos")
            return
        
        photos = photos_data.get("photos", [])
        
        # Extract detected angles from vision outputs
        detected_angles_set = set()
        required_angles = ["front", "rear", "left", "right", "interior", "odometer"]
        
        for photo in photos:
            vision_output = photo.get("vision_output_json")
            if vision_output:
                extraction = vision_output.get("extraction", {})
                photo_angle = extraction.get("photo_angle", {})
                angle = photo_angle.get("angle", "unknown")
                confidence = photo_angle.get("confidence", 0.0)
                if angle != "unknown" and confidence >= 0.7:
                    angle_lower = angle.lower()
                    if angle_lower in required_angles:
                        detected_angles_set.add(angle_lower)
        
        detected_angles = sorted(list(detected_angles_set))
        missing_angles = [angle for angle in required_angles if angle not in detected_angles_set]
        
        # Get photo coverage information from latest run (if completed)
        if latest_run and run_status == "COMPLETED":
            outputs = latest_run.get("outputs_json", {})
            evidence_completeness = outputs.get("evidence_completeness", {})
            covered_angles = evidence_completeness.get("covered_angles", [])
            missing_angles = evidence_completeness.get("missing_angles", [])
        else:
            # Use detected angles from vision outputs
            covered_angles = detected_angles
        
        # Display angle coverage status
        st.markdown("### 📸 Photo Coverage Status")
        col1, col2 = st.columns(2)
        
        with col1:
            if covered_angles:
                st.markdown("**✅ Covered Angles:**")
                for angle in covered_angles:
                    st.markdown(f"  • {angle.title()}")
            else:
                st.info("No angles detected yet")
        
        with col2:
            if missing_angles:
                st.markdown("**❌ Missing Angles:**")
                for angle in missing_angles:
                    st.markdown(f"  • {angle.title()}")
            else:
                st.success("✅ All required angles covered!")
        
        # Add more photos section right after coverage status
        st.markdown("---")
        st.markdown("### ➕ Add More Photos")
        
        if len(photos) < 3:
            st.info(f"You can add up to **{3 - len(photos)} more photo(s)** to improve coverage.")
            
            uploaded_file = st.file_uploader(
                "📸 Select photo to upload",
                type=["jpg", "jpeg", "png", "heic", "heif"],
                accept_multiple_files=False,
                key=f"additional_photo_uploader_{appraisal_id}",
            )
            
            if uploaded_file is not None:
                with st.spinner(f"⬆️ Uploading {uploaded_file.name}..."):
                    files = [("photo", (uploaded_file.name, uploaded_file, normalize_file_content_type(uploaded_file, uploaded_file.type)))]
                    success, result = call_api(
                        "POST",
                        f"/api/appraisals/{appraisal_id}/photos/upload",
                        files=files
                    )
                
                if success:
                    st.success(f"✅ {uploaded_file.name} uploaded successfully!")
                    st.info("💡 Click 'Reanalyze' below to include this photo in the analysis.")
                    st.rerun()
                else:
                    st.error(f"❌ Upload failed: {result.get('error', 'Unknown error')}")
        else:
            st.success("✅ Maximum number of photos (3) already uploaded.")
            # Still allow reanalyze even at max photos
            uploaded_file = None
        
        # Reanalyze button - always show if we have photos
        if len(photos) > 0:
            reanalyze_clicked = st.button("🔄 Reanalyze with New Photos", type="primary", use_container_width=True, key=f"reanalyze_photos_{appraisal_id}")
            if reanalyze_clicked:
                with st.spinner("Starting reanalysis..."):
                    idempotency_key = str(uuid.uuid4())
                    success, result = call_api(
                        "POST",
                        f"/api/appraisals/{appraisal_id}/run",
                        headers={"Idempotency-Key": idempotency_key},
                    )
                
                if success:
                    # Since we're already on view page, just refresh to show processing status
                    st.session_state["last_appraisal_id"] = appraisal_id
                    st.rerun()
                else:
                    st.error(f"❌ Failed to start reanalysis: {result.get('error', 'Unknown error')}")
        
        # Display photos
        if photos:
            st.markdown("---")
            st.markdown(f"### 📷 Uploaded Photos ({len(photos)}/3)")
            cols = st.columns(3)
            for i, photo in enumerate(photos):
                with cols[i % 3]:
                    signed_url = photo.get("signed_url")
                    vision_output = photo.get("vision_output_json", {})
                    extraction = vision_output.get("extraction", {}) if vision_output else {}
                    photo_angle = extraction.get("photo_angle", {}) if extraction else {}
                    angle = photo_angle.get("angle", "unknown")
                    confidence = photo_angle.get("confidence", 0.0)
                    
                    caption = f"Photo {i+1}"
                    if angle != "unknown" and confidence >= 0.7:
                        caption += f" - {angle.title()}"
                    
                    if signed_url:
                        try:
                            st.image(signed_url, use_container_width=True, caption=caption)
                        except Exception:
                            st.write(f"📷 {caption} (preview unavailable)")
                    else:
                        st.write(f"📷 {caption}")
        else:
            st.info("No photos uploaded yet")
    
    with tab3:
        st.subheader("Vehicle Information")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Year", metadata.get("year", "N/A"))
            st.metric("Make", metadata.get("make", "N/A"))
        with col2:
            st.metric("Model", metadata.get("model", "N/A"))
            st.metric("Trim", metadata.get("trim", "N/A"))
        with col3:
            st.metric("Mileage", f"{metadata.get('mileage', 'N/A'):,}" if metadata.get("mileage") else "N/A")
            st.metric("Color", metadata.get("color", "N/A"))
        
        notes = appraisal.get("notes_raw", "")
        st.subheader("Appraiser Notes")
        if notes:
            st.write(notes)
        else:
            st.info("No notes provided")
    
    with tab4:
        st.subheader("Pipeline Execution Flow")
        st.caption("Visual representation of how the AI agent processed this appraisal")
        show_ledger_infographic(appraisal_id)
        
        st.markdown("---")
        st.subheader("Detailed Event Log")
        with st.expander("View Raw Event Data"):
            show_ledger_viewer(appraisal_id)


def show_analysis_progress(run: dict[str, Any], appraisal_id: str):
    """Display processing status for analysis."""
    st.markdown("---")
    
    # Show processing status banner
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%); border: 2px solid #0066cc; border-radius: 12px; padding: 2rem; text-align: center; margin: 2rem 0;">
        <h2 style="color: #0066cc; margin-bottom: 1rem;">🔄 Processing</h2>
        <p style="font-size: 1.1rem; color: #333; margin: 0;">
            Analysis is in progress. Results will appear here automatically when ready (typically within 2 minutes).
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show spinner
    with st.spinner("Analyzing your appraisal..."):
        # Auto-check every 2 seconds
        if "last_progress_check" not in st.session_state:
            st.session_state["last_progress_check"] = time.time()
        
        current_time = time.time()
        if current_time - st.session_state["last_progress_check"] >= 2:
            st.session_state["last_progress_check"] = current_time
            # Re-check status
            success, data = call_api("GET", f"/api/appraisals/{appraisal_id}")
            if success:
                latest_run_new = data.get("latest_run")
                if latest_run_new:
                    run_status_new = latest_run_new.get("status", "").upper()
                    if run_status_new not in ["PENDING", "RUNNING", "IN_PROGRESS"]:
                        st.rerun()
                        return
        
        time.sleep(2)
        st.rerun()


def display_run_results(run: dict[str, Any], appraisal_id: str, metadata: dict = None, appraisal: dict = None):
    """Display results for a pipeline run."""
    if metadata is None:
        metadata = {}
    if appraisal is None:
        appraisal = {}
    
    status = run.get("status", "unknown")
    outputs = run.get("outputs_json", {})
    
    if status.lower() != "completed":
        st.info("⏳ Analysis in progress... Please refresh to see results.")
        return
    
    decision = outputs.get("decision_readiness", {})
    if not decision:
        st.warning("No decision readiness data available")
        return
    
    score = decision.get("score", 0)
    decision_status = decision.get("status", "unknown")
    reasons = decision.get("reasons", [])
    evidence_completeness = outputs.get("evidence_completeness", {})
    missing_angles = evidence_completeness.get("missing_angles", [])
    
    st.markdown("---")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        score_color = "#28a745" if score >= 80 else ("#ffc107" if score >= 50 else "#dc3545")
        score_html = f'''
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, {score_color}22 0%, {score_color}11 100%); border-radius: 15px; border: 3px solid {score_color};">
            <div style="font-size: 64px; font-weight: bold; color: {score_color}; line-height: 1;">{score}</div>
            <div style="font-size: 24px; color: #666; margin-top: 5px;">/ 100</div>
            <div style="font-size: 14px; color: #888; margin-top: 10px; text-transform: uppercase; letter-spacing: 1px;">Readiness Score</div>
        </div>
        '''
        st.markdown(score_html, unsafe_allow_html=True)
        
        photo_count = evidence_completeness.get("photo_count", 0)
        covered_angles = evidence_completeness.get("covered_angles", [])
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Photos", f"{photo_count}")
        with col_b:
            st.metric("Angles", f"{len(covered_angles)}/8")
    
    with col2:
        if decision_status == "ready":
            st.success("### ✅ READY TO DECIDE")
            st.write("This appraisal has sufficient evidence to make a confident decision.")
        elif decision_status == "escalate":
            st.error("### ⚠️ ESCALATION REQUIRED")
            st.write("Significant issues detected. Senior review needed.")
        else:
            st.warning("### 📋 NEEDS MORE EVIDENCE")
            st.write("Additional information required for decision.")
        
        if reasons:
            st.markdown("**Action Items:**")
            for i, reason in enumerate(reasons, 1):
                st.markdown(f"• {reason}")
    
    breakdown = decision.get("breakdown", {})
    if breakdown:
        with st.expander("📋 **View Detailed Evidence Breakdown**", expanded=False):
            categories = [
                ("angle_coverage", "📸 Photo Coverage"),
                ("odometer_confidence", "⏲️ Odometer"),
                ("vin_presence", "🔑 VIN"),
                ("notes_consistency", "📝 Notes Quality"),
            ]
            
            for cat_key, cat_title in categories:
                if cat_key in breakdown:
                    details = breakdown[cat_key]
                    score_val = details.get("score", 0)
                    max_val = details.get("max_score", 1)
                    percentage = (score_val / max_val * 100) if max_val > 0 else 0
                    
                    if percentage >= 80:
                        status_icon = "✅"
                        status_color = "#28a745"
                    elif percentage >= 50:
                        status_icon = "⚠️"
                        status_color = "#ffc107"
                    else:
                        status_icon = "❌"
                        status_color = "#dc3545"
                    
                    col_title, col_bar = st.columns([1, 3])
                    with col_title:
                        st.markdown(f"**{status_icon} {cat_title.split(' ', 1)[1] if ' ' in cat_title else cat_title}**")
                    with col_bar:
                        progress_html = f'''
                        <div style="background: #e9ecef; height: 24px; border-radius: 12px; overflow: hidden; margin-top: 3px;">
                            <div style="background: {status_color}; width: {percentage}%; height: 100%; display: flex; align-items: center; justify-content: flex-start; padding-left: 10px; color: white; font-weight: 600; font-size: 12px;">
                                {score_val}/{max_val} ({percentage:.0f}%)
                            </div>
                        </div>
                        '''
                        st.markdown(progress_html, unsafe_allow_html=True)
                    
                    # Add detailed information for angle_coverage (similar to Photos tab)
                    if cat_key == "angle_coverage":
                        st.markdown("")
                        angle_details = details.get("angle_details", {})
                        covered_angles_list = evidence_completeness.get("covered_angles", [])
                        missing_angles_list = evidence_completeness.get("missing_angles", [])
                        
                        if covered_angles_list or missing_angles_list:
                            detail_col1, detail_col2 = st.columns(2)
                            with detail_col1:
                                if covered_angles_list:
                                    st.markdown("**✅ Covered Angles:**")
                                    for angle in covered_angles_list:
                                        confidence = angle_details.get(angle, {}).get("confidence", 0.0) if angle_details else 0.0
                                        conf_percent = int(confidence * 100)
                                        st.markdown(f"  • {angle.title()} ({conf_percent}% confidence)")
                                else:
                                    st.info("No angles covered")
                            
                            with detail_col2:
                                if missing_angles_list:
                                    st.markdown("**❌ Missing Angles:**")
                                    for angle in missing_angles_list:
                                        st.markdown(f"  • {angle.title()}")
                                else:
                                    st.success("All required angles covered!")
                    
                    # Add details for odometer
                    elif cat_key == "odometer_confidence":
                        st.markdown("")
                        odometer_info = outputs.get("vision_summary", {})
                        odometer_value = odometer_info.get("odometer_value")
                        odometer_unit = odometer_info.get("odometer_unit", "miles")
                        if odometer_value:
                            st.info(f"📊 Detected Odometer: **{odometer_value:,} {odometer_unit}**")
                        else:
                            st.warning("⚠️ No odometer reading detected in photos")
                    
                    # Add details for VIN
                    elif cat_key == "vin_presence":
                        st.markdown("")
                        vin_info = outputs.get("vision_summary", {})
                        vin_text = vin_info.get("vin_text")
                        if vin_text:
                            st.info(f"🔑 Detected VIN: **{vin_text}**")
                        else:
                            st.warning("⚠️ No VIN detected in photos")
                    
                    st.markdown("")
    
    risk_data = outputs.get("risk_and_consistency", {})
    risk_flags = risk_data.get("flags", [])
    if risk_flags:
        with st.expander(f"⚠️ **Risk Flags Detected ({len(risk_flags)})**", expanded=True):
            for flag in risk_flags:
                severity = flag.get("severity", "low").lower()
                code = flag.get("code", "unknown")
                message = flag.get("message", "")
                
                if severity == "high":
                    severity_icon = "🔴"
                    severity_color = "#dc3545"
                elif severity == "medium":
                    severity_icon = "🟡"
                    severity_color = "#ffc107"
                else:
                    severity_icon = "🟢"
                    severity_color = "#28a745"
                
                st.markdown(f"""
                <div style="padding: 10px; border-left: 3px solid {severity_color}; background: {severity_color}11; margin-bottom: 10px; border-radius: 4px;">
                    <div style="font-weight: 600; color: {severity_color};">{severity_icon} {code.replace('_', ' ').title()}</div>
                    <div style="color: #555; font-size: 13px; margin-top: 4px;">{message}</div>
                </div>
                """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(f"Analysis completed: {format_timestamp(run.get('completed_at'))}")
    
    # Add "Add More Photos" section in Analysis Results tab
    st.markdown("---")
    st.markdown("### ➕ Add More Photos to Improve Coverage")
    
    # Get current photo count
    with st.spinner("Loading photos..."):
        success_photos, photos_data = call_api("GET", f"/api/appraisals/{appraisal_id}/photos")
    
    if success_photos:
        photos = photos_data.get("photos", [])
        photo_count = len(photos)
        
        if photo_count < 3:
            st.info(f"You can add up to **{3 - photo_count} more photo(s)** to improve evidence coverage and potentially increase your readiness score.")
            
            uploaded_file = st.file_uploader(
                "📸 Select photo to upload",
                type=["jpg", "jpeg", "png", "heic", "heif"],
                accept_multiple_files=False,
                key=f"analysis_tab_photo_uploader_{appraisal_id}",
            )
            
            if uploaded_file is not None:
                with st.spinner(f"⬆️ Uploading {uploaded_file.name}..."):
                    files = [("photo", (uploaded_file.name, uploaded_file, normalize_file_content_type(uploaded_file, uploaded_file.type)))]
                    success, result = call_api(
                        "POST",
                        f"/api/appraisals/{appraisal_id}/photos/upload",
                        files=files
                    )
                
                if success:
                    st.success(f"✅ {uploaded_file.name} uploaded successfully!")
                    st.info("💡 Click 'Reanalyze' below to include this photo in a new analysis.")
                    st.rerun()
                else:
                    st.error(f"❌ Upload failed: {result.get('error', 'Unknown error')}")
            
            # Reanalyze button
            reanalyze_clicked = st.button("🔄 Reanalyze with New Photos", type="primary", use_container_width=True, key=f"reanalyze_from_results_{appraisal_id}")
            if reanalyze_clicked:
                with st.spinner("Starting reanalysis..."):
                    idempotency_key = str(uuid.uuid4())
                    success, result = call_api(
                        "POST",
                        f"/api/appraisals/{appraisal_id}/run",
                        headers={"Idempotency-Key": idempotency_key},
                    )
                
                if success:
                    # Since we're already on view page, just refresh to show processing status
                    st.session_state["last_appraisal_id"] = appraisal_id
                    st.rerun()
                else:
                    st.error(f"❌ Failed to start reanalysis: {result.get('error', 'Unknown error')}")
        else:
            st.success("✅ Maximum number of photos (3) already uploaded.")


def show_ledger_infographic(appraisal_id: str):
    """Display visual infographic of pipeline execution flow."""
    with st.spinner("Loading pipeline flow..."):
        success, data = call_api("GET", f"/api/appraisals/{appraisal_id}/ledger")
    
    if not success:
        st.error(f"Failed to load ledger: {data.get('error')}")
        return
    
    events = data.get("events", [])
    if not events:
        st.info("No pipeline events found")
        return
    
    node_info = {
        "agent_start": {"name": "🚀 Agent Started", "color": "#4CAF50"},
        "agent_tool_extract_vision_from_photo": {"name": "📸 Vision Analysis", "color": "#2196F3"},
        "agent_tool_check_evidence_completeness": {"name": "📋 Evidence Check", "color": "#FF9800"},
        "agent_tool_retrieve_similar_appraisals": {"name": "🔍 RAG Search", "color": "#9C27B0"},
        "agent_tool_scan_for_risks": {"name": "⚠️ Risk Assessment", "color": "#F44336"},
        "agent_tool_calculate_readiness_score": {"name": "🎯 Decision Score", "color": "#9C27B0"},
        "agent_complete": {"name": "✅ Analysis Complete", "color": "#4CAF50"},
    }
    
    st.markdown("### 📊 Agent Execution Flow")
    
    for i, event in enumerate(events, 1):
        node = event.get("node_name", "unknown")
        status = event.get("status", "ok")
        timestamp = event.get("timestamp", "")
        
        info = node_info.get(node, {
            "name": node.replace("_", " ").title(),
            "color": "#757575",
        })
        
        display_name = info["name"]
        color = info["color"]
        status_icon = "✅" if status == "ok" else "❌"
        
        card_html = f'''
        <div style="display: flex; align-items: stretch; margin-bottom: 12px;">
            <div style="flex-shrink: 0; width: 35px; height: 35px; border-radius: 50%; background: {color}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 14px; align-self: center;">
                {i}
            </div>
            <div style="flex-grow: 1; margin-left: 12px; padding: 10px 12px; background: white; border-radius: 6px; border-left: 3px solid {color}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 4px;">
                    <div style="font-weight: 600; font-size: 14px;">{status_icon} {display_name}</div>
                    <div style="font-size: 11px; color: #666; font-family: monospace; white-space: nowrap; margin-left: 12px;">{format_timestamp(timestamp, include_ms=True)}</div>
                </div>
            </div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)


def show_ledger_viewer(appraisal_id: str):
    """Display full ledger event log."""
    with st.spinner("Loading ledger..."):
        success, data = call_api("GET", f"/api/appraisals/{appraisal_id}/ledger")
    
    if not success:
        st.error(f"Failed to load ledger: {data.get('error')}")
        return
    
    events = data.get("events", [])
    if not events:
        st.info("No ledger events found")
        return
    
    st.write(f"**Total Events:** {len(events)}")
    
    for i, event in enumerate(events, 1):
        node_name = event.get("node_name", "unknown")
        timestamp = format_timestamp(event.get("timestamp"))
        output = event.get("output", {})
        status = event.get("status", "unknown")
        error = event.get("error")
        
        status_icon = "✅" if status == "ok" else "❌"
        
        st.markdown(f"**{status_icon} {node_name}** - `{timestamp}`")
        if output:
            with st.container():
                st.json(output)
        else:
            st.info("No output data available")
        
        if error:
            st.error(f"Error: {error}")
        
        if i < len(events):
            st.markdown("---")


if __name__ == "__main__":
    main()
