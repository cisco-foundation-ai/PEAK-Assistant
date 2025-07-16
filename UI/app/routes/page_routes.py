"""
Page rendering routes for PEAK Assistant UI
"""
import os
import sys
from flask import Blueprint, render_template, jsonify, session, request

# Create page blueprint
page_bp = Blueprint('pages', __name__)


@page_bp.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@page_bp.route('/research')
def research_page():
    """Topic research interface"""
    return render_template('research.html')


@page_bp.route('/hypothesis')
def hypothesis_page():
    """Hypothesis generation interface"""
    # Only use the current (editable) hypothesis, never the refined one
    hypo = session.get('hypothesis', '')
    return render_template('hypothesis.html', current_hypothesis=hypo)


@page_bp.route('/refinement')
def refinement_page():
    """Hypothesis refinement interface"""
    return render_template('refinement.html')


@page_bp.route('/able-table')
def able_table_page():
    """ABLE table generation interface"""
    return render_template('able_table.html')


@page_bp.route('/data-discovery')
def data_discovery_page():
    """Data discovery interface"""
    return render_template('data_discovery.html')


@page_bp.route('/hunt-planning')
def hunt_planning_page():
    """Hunt planning interface"""
    return render_template('hunt_planning.html')


@page_bp.route('/help')
def help_page():
    """Help and documentation page"""
    return render_template('help.html')


@page_bp.route('/debug')
def debug_page():
    """Debug information page"""
    return render_template('debug.html')


@page_bp.route('/api/debug-info', methods=['GET', 'POST'])
def debug_info():
    """Debug information and session management endpoint"""
    if request.method == 'POST':
        # Clear session (used in debug page)
        session.clear()
        return jsonify({'success': True})
    
    # Get environment variables (with redaction for sensitive ones)
    env_vars = {}
    sensitive_keywords = ["KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "CONN_STR"]
    for key, value in os.environ.items():
        is_sensitive = any(keyword in key.upper() for keyword in sensitive_keywords)
        env_vars[key] = "[REDACTED]" if is_sensitive and value else value
    
    # System info
    sys_info = {
        'platform': sys.platform,
        'python_version': sys.version,
    }
    
    return jsonify({
        'environment': env_vars,
        'system_info': sys_info,
        'session_data': {k: session[k] for k in session if k not in ['_permanent', 'csrf_token']} if session else {}
    })
