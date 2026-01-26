"""
Header and navigation component for Vehicle Appraisal UI.
"""
import streamlit as st


def render_header(current_page: str = None):
    """Render the header with navigation."""
    header_html = '''
    <div class="autograb-header">
        <div class="autograb-header-container">
            <div class="autograb-logo">Vehicle Appraisal Pre-Check</div>
        </div>
    </div>
    '''
    st.markdown(header_html, unsafe_allow_html=True)
    
    pages = {
        "Home": "home",
        "Submit Appraisal": "submit",
        "View Appraisal": "view"
    }
    
    nav_cols = st.columns([1] + [1] * len(pages) + [1])
    with nav_cols[0]:
        st.markdown("")
    
    for i, (page_name, page_key) in enumerate(pages.items(), 1):
        with nav_cols[i]:
            button_type = "primary" if current_page == page_key else "secondary"
            if st.button(page_name, key=f"nav_{page_key}", use_container_width=True, type=button_type):
                st.session_state["page_transition"] = True
                st.session_state["target_page"] = page_key
                st.rerun()
    
    with nav_cols[-1]:
        st.markdown("")
    
    st.markdown("<br>", unsafe_allow_html=True)


def render_hero_section():
    """Render the hero section for the landing page."""
    hero_html = '''
    <div class="autograb-hero">
        <h1>Automated Appraisal Pre-Processing</h1>
        <p class="autograb-hero-subtitle">
            Ensure sufficient evidence is collected <strong>before</strong> actual appraisal begins.
            <br>AI-powered validation that saves time and prevents incomplete submissions.
        </p>
        <div class="autograb-hero-cta">
        </div>
    '''
    st.markdown(hero_html, unsafe_allow_html=True)
    
    cta_cols = st.columns(2)
    with cta_cols[0]:
        if st.button("Start New Appraisal", type="primary", use_container_width=True, key="hero_submit"):
            st.session_state["page_transition"] = True
            st.session_state["target_page"] = "submit"
            st.rerun()
    with cta_cols[1]:
        if st.button("View Existing Appraisals", use_container_width=True, key="hero_view"):
            st.session_state["page_transition"] = True
            st.session_state["target_page"] = "view"
            st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)


def render_feature_cards():
    """Render feature cards highlighting key capabilities."""
    features = [
        {
            "icon": "📸",
            "title": "AI Vision Extraction",
            "description": "GPT-4 Vision analyzes photos to extract angles, odometer, VIN, and damage"
        },
        {
            "icon": "🔍",
            "title": "RAG-Enhanced Analysis",
            "description": "Vector search finds similar historical appraisals for context-aware risk assessment"
        },
        {
            "icon": "🤖",
            "title": "Agentic Orchestration",
            "description": "LangChain agent adaptively processes evidence and determines readiness"
        },
        {
            "icon": "📊",
            "title": "Decision Readiness",
            "description": "Confidence-aware routing with safe escalation paths for uncertain cases"
        }
    ]
    
    cols = st.columns(4)
    for i, feature in enumerate(features):
        with cols[i]:
            card_html = f'''
            <div class="autograb-feature-card">
                <div class="autograb-feature-icon">{feature["icon"]}</div>
                <div class="autograb-feature-title">{feature["title"]}</div>
                <div class="autograb-feature-description">{feature["description"]}</div>
            </div>
            '''
            st.markdown(card_html, unsafe_allow_html=True)
