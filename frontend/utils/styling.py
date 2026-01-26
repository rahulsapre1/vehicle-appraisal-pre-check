"""
Styling utilities for Vehicle Appraisal UI.
Handles CSS injection and styling helpers.
"""
import streamlit as st


def inject_custom_css(css_file_path: str = "assets/style.css"):
    """Inject custom CSS into Streamlit app."""
    try:
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(current_dir)
        css_path = os.path.join(app_dir, css_file_path)
        
        if os.path.exists(css_path):
            with open(css_path, 'r') as f:
                css = f.read()
            st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
        else:
            # Fallback: basic styles
            st.markdown("""
            <style>
            :root {
                --primary-blue: #0066cc;
                --primary-dark: #0d1b2a;
            }
            </style>
            """, unsafe_allow_html=True)
    except Exception:
        pass


def render_status_badge(status: str, text: str = None) -> str:
    """Render a status badge HTML."""
    if text is None:
        text = status.upper()
    
    badge_class = f"autograb-badge-{status}"
    return f'<span class="autograb-badge {badge_class}">{text}</span>'


def render_card(html_content: str, title: str = None) -> str:
    """Render content in a card container."""
    title_html = f'<div class="autograb-card-header"><h3 class="autograb-card-title">{title}</h3></div>' if title else ''
    return f'''
    <div class="autograb-card">
        {title_html}
        {html_content}
    </div>
    '''
