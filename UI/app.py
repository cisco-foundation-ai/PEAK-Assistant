#!/usr/bin/env python3
# filepath: /Users/dabianco/projects/SURGe/PEAK-Assistant/UI/app_flask.py
from flask import Flask, render_template, request, jsonify, Response, send_file, session
import tempfile
import os
import sys
import asyncio
import time
import io
import json
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from markdown_pdf import MarkdownPdf, Section
from flask_session import Session
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import timedelta

# --- Utility functions ---
def find_dotenv_file():
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / '.env'
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found

def load_env_defaults():
    dotenv_path = find_dotenv_file()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        print("Warning: No .env file found in current or parent directories")

# Flask async support
def async_action(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped

async def retry_api_call(func, *args, max_retries=3, **kwargs):
    """Retry an API call with exponential backoff on specific errors"""
    retry_delay = 2  # Start with 2 seconds
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_msg = str(e)
            # Check if this is an OpenAI API error that might be transient
            if "500" in error_msg and "Internal server error" in error_msg:
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
            # For other errors, or if we've exhausted retries, break out
            break
    
    # If we've exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception

def extract_report_md(messages):
    # Try to extract the research report markdown from agent output
    report_md = None
    if hasattr(messages, 'messages'):
        report_md = next((m.content for m in reversed(messages.messages) if getattr(m, 'source', None) == "summarizer"), None)
    if not report_md:
        if isinstance(messages, str):
            report_md = messages
        elif hasattr(messages, 'content'):
            report_md = messages.content
        else:
            report_md = str(messages)
    return report_md

def extract_accepted_hypothesis(refined):
    # Extract the accepted/refined hypothesis string from agent output
    accepted = None
    if hasattr(refined, 'messages'):
        for m in reversed(refined.messages):
            if isinstance(m.content, str) and 'YYY-HYPOTHESIS-ACCEPTED-YYY' in m.content:
                idx = refined.messages.index(m)
                if idx > 0:
                    accepted = refined.messages[idx-1].content.strip()
                break
    elif isinstance(refined, list):
        for i, m in enumerate(refined):
            if hasattr(m, 'content') and isinstance(m.content, str) and 'YYY-HYPOTHESIS-ACCEPTED-YYY' in m.content:
                if i > 0:
                    accepted = refined[i-1].content.strip()
                break
    if not accepted:
        if hasattr(refined, 'content'):
            accepted = refined.content
        else:
            accepted = str(refined)
    return accepted

# Load .env at app startup
load_env_defaults()

# Add the parent directory to sys.path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Suppress asyncio event loop closure warnings from background HTTP cleanup
import warnings
import logging

# Set up logging to suppress HTTP client cleanup errors
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)

# Suppress specific warnings about event loop closure
warnings.filterwarnings("ignore", message=".*Event loop is closed.*")
warnings.filterwarnings("ignore", message=".*Task exception was never retrieved.*")

from research_assistant.research_assistant_cli import researcher as async_researcher
from hypothesis_assistant.hypothesis_assistant_cli import hypothesizer as async_hypothesizer
from hypothesis_assistant.hypothesis_refiner_cli import refiner as async_refiner
from able_assistant.able_assistant_cli import able_table as async_able_table
from data_assistant.data_asssistant_cli import identify_data_sources as async_identify_data_sources
from planning_assistant.planning_assistant_cli import plan_hunt as async_plan_hunt

# Initialize Flask app
app = Flask(__name__)

# --- Load initial local context ---
INITIAL_LOCAL_CONTEXT = None
CONTEXT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'context.txt')
if os.path.exists(CONTEXT_FILE_PATH):
    try:
        with open(CONTEXT_FILE_PATH, 'r', encoding='utf-8') as f:
            INITIAL_LOCAL_CONTEXT = f.read()
        print(f"Successfully loaded initial context from {CONTEXT_FILE_PATH}")
    except Exception as e:
        print(f"Error loading initial context from {CONTEXT_FILE_PATH}: {e}")
# --- End load initial local context ---

app.secret_key = os.urandom(24)  # For session management

# Configure sessions to be temporary (don't persist across app restarts)
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # Short lifetime for temporary sessions

# Configure SQLAlchemy for session storage
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///peak_sessions.db'
app.config['SESSION_SQLALCHEMY_TABLE'] = 'sessions'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'peak_assistant_'

db = SQLAlchemy(app)
app.config['SESSION_SQLALCHEMY'] = db
Session(app)  # Initialize Flask-Session

@app.before_request
def load_initial_context_into_session():
    if INITIAL_LOCAL_CONTEXT is not None and 'local-context' not in session:
        session['local-context'] = INITIAL_LOCAL_CONTEXT

# Create the session table if it doesn't exist
with app.app_context():
    db.create_all()

ALLOWED_UPLOAD_EXTENSIONS = {'.md', '.txt'}
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'peak_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ===== API Routes =====

@app.route('/api/research', methods=['POST'])
@async_action
async def research():
    data = request.json
    topic = data.get('topic')
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    
    if not topic:
        return jsonify({'success': False, 'error': 'No topic provided'}), 400
    
    local_context = session.get('local-context', '')  # Get local context from session

    try:
        # Use the agent framework
        messages = await retry_api_call(
            async_researcher, 
            topic, 
            local_context=local_context,  # Pass local context
            verbose=verbose_mode,
            max_retries=retry_count
        )
        report_md = extract_report_md(messages)
        
        # Store in session
        session['report_md'] = report_md
        session['last_topic'] = topic
        
        return jsonify({'success': True, 'report': report_md})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hypothesize', methods=['POST'])
@async_action
async def hypothesize():
    data = request.json
    report_md = data.get('report_md') or session.get('report_md', '')
    retry_count = int(data.get('retry_count', 3))
    # verbose_mode is ignored for hypothesizer, as it is not supported
    
    if not report_md:
        return jsonify({'success': False, 'error': 'No research report available'}), 400

    local_context = session.get('local-context', '')  # Get local context from session
    
    try:
        hypos = await retry_api_call(
            async_hypothesizer, 
            report_md, 
            report_md,  # This seems to be duplicated, raw_text is the second param
            local_context=local_context,  # Pass local context
            max_retries=retry_count
        )
        
        if isinstance(hypos, str):
            hypos = hypos.splitlines()
        
        # Store in session
        session['hypotheses'] = hypos
        
        return jsonify({'success': True, 'hypotheses': hypos})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save-hypothesis', methods=['POST'])
def save_hypothesis():
    """Save a hypothesis to the session without refinement"""
    data = request.json
    hypothesis = data.get('hypothesis')
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400
    prev_hypo = session.get('hypothesis')
    # Store in session
    session['hypothesis'] = hypothesis
    # Only clear refined_hypothesis if the hypothesis actually changed
    if prev_hypo != hypothesis:
        session.pop('refined_hypothesis', None)
    return jsonify({'success': True})

@app.route('/api/refine', methods=['POST'])
@async_action
async def refine():
    data = request.json
    hypothesis = data.get('hypothesis') or session.get('hypothesis', '')
    report_md = data.get('report_md') or session.get('report_md', '')
    retry_count = int(data.get('retry_count', 3))
    refine_option = data.get('refine', True)  # Default to true to maintain backward compatibility
    
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400
    
    # If refine is False, just save the hypothesis and return
    if not refine_option:
        session['hypothesis'] = hypothesis
        session.pop('refined_hypothesis', None)
        return jsonify({'success': True, 'refined_hypothesis': hypothesis})
    
    verbose_mode = data.get('verbose_mode', False)
    local_context = session.get('local-context', '')  # Get local context from session

    try:
        refined = await retry_api_call(
            async_refiner, 
            hypothesis, 
            local_context,  # Pass local context as positional argument
            report_md, 
            automated=True,
            verbose=verbose_mode,
            max_retries=retry_count
        )
        # Extract the final message from the critic agent
        accepted = None
        if hasattr(refined, 'messages'):
            accepted = next((m.content for m in reversed(refined.messages) if getattr(m, 'source', None) == "critic"), None)
            if accepted:
                accepted = accepted.replace("YYY-HYPOTHESIS-ACCEPTED-YYY", "").strip()
        if not accepted:
            if hasattr(refined, 'content'):
                accepted = refined.content
            else:
                accepted = str(refined)
        session['refined_hypothesis'] = accepted  # Store separately
        return jsonify({'success': True, 'refined_hypothesis': accepted})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/able-table', methods=['POST'])
@async_action
async def able_table():
    data = request.json
    # Use refined hypothesis if available, else fallback to original
    hypothesis = data.get('hypothesis') or session.get('refined_hypothesis') or session.get('hypothesis', '')
    report_md = data.get('report_md') or session.get('report_md', '')
    retry_count = int(data.get('retry_count', 3))
    # verbose_mode is ignored for able_table, as it is not supported
    
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400

    local_context = session.get('local-context', '')  # Get local context from session
    
    try:
        able_md = await retry_api_call(
            async_able_table, 
            hypothesis, 
            report_md,
            local_context=local_context,  # Pass local context
            max_retries=retry_count
        )
        # Store in session
        session['able_table_md'] = able_md
        return jsonify({'success': True, 'able_table': able_md})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data-discovery', methods=['GET', 'POST'])
@async_action
async def data_discovery():
    if request.method == 'GET':
        # Return existing data sources from session
        return jsonify({
            'data_sources_md': session.get('data_sources_md', ''),
            'success': True
        })
    
    data = request.json
    # Use refined hypothesis if available, else fallback to original
    hypothesis = data.get('hypothesis') or session.get('refined_hypothesis') or session.get('hypothesis', '')
    report_md = data.get('report_md') or session.get('report_md', '')
    able_table_md = data.get('able_table_md') or session.get('able_table_md', '')
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    local_context = session.get('local-context', '')  # Get local context from session
    
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400
    
    if not report_md:
        return jsonify({'success': False, 'error': 'No research report available'}), 400
    
    # Get MCP configuration from environment variables
    mcp_command = os.getenv('SPLUNK_MCP_COMMAND')
    mcp_args = os.getenv('SPLUNK_MCP_ARGS')
    
    if not mcp_command or not mcp_args:
        return jsonify({
            'success': False, 
            'error': 'Splunk MCP configuration missing. Please ensure SPLUNK_MCP_COMMAND and SPLUNK_MCP_ARGS environment variables are set.'
        }), 500
    
    try:
        result = await retry_api_call(
            async_identify_data_sources, 
            hypothesis, 
            report_md,
            able_info=able_table_md,
            local_context=local_context,  # Pass local context to the function
            mcp_command=mcp_command,
            mcp_args=mcp_args,
            verbose=verbose_mode,
            max_retries=retry_count
        )
        # Extract the final message from the "Data_Discovery_Agent" similar to CLI version
        data_sources_md = None
        if hasattr(result, 'messages'):
            data_sources_md = next(
                (message.content for message in reversed(result.messages) if getattr(message, 'source', None) == "Data_Discovery_Agent"),
                None
            )
        if not data_sources_md:
            if hasattr(result, 'content'):
                data_sources_md = result.content
            else:
                data_sources_md = str(result)
        
        # Store in session
        session['data_sources_md'] = data_sources_md
        return jsonify({'success': True, 'data_sources': data_sources_md})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-report', methods=['POST'])
def upload_report():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    session['report_md'] = content
    session['last_topic'] = '[Uploaded]'
    return jsonify({'success': True, 'content': content})

@app.route('/api/upload-able-table', methods=['POST'])
def upload_able_table():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    session['able_table_md'] = content
    return jsonify({'success': True, 'able_table': content})

@app.route('/api/upload-data-sources', methods=['POST'])
def upload_data_sources():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    session['data_sources_md'] = content
    return jsonify({'success': True, 'data_sources': content})

@app.route('/api/download/markdown', methods=['POST', 'GET'])
def download_markdown():
    if request.method == 'GET':
        return jsonify({'success': False, 'error': 'GET not supported. Use POST.'}), 405
    data = request.json or request.form
    content = data.get('content')
    filename = data.get('filename', 'download.md')
    if not content:
        return jsonify({'success': False, 'error': 'No content provided'}), 400
    buffer = io.BytesIO(content.encode('utf-8'))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='text/markdown',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/download/pdf', methods=['POST', 'GET'])
def download_pdf():
    if request.method == 'GET':
        return jsonify({'success': False, 'error': 'GET not supported. Use POST.'}), 405
    data = request.json or request.form
    content = data.get('content')
    filename = data.get('filename', 'download.pdf')
    if not content:
        return jsonify({'success': False, 'error': 'No content provided'}), 400
    pdf = MarkdownPdf()
    pdf.add_section(Section(content, toc=False))
    pdf_buffer = io.BytesIO()
    pdf.save(pdf_buffer)
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/hunt-plan', methods=['POST'])
@async_action
async def hunt_plan():
    """Generate hunt plan using AI agents"""
    data = request.json or {}
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    
    # Get required data from session
    research_document = session.get('report_md', '')
    hypothesis = session.get('refined_hypothesis') or session.get('hypothesis', '')
    able_info = session.get('able_table_md', '')
    data_discovery = session.get('data_sources_md', '')
    local_context = session.get('local-context', '')
    
    # Check prerequisites
    missing_items = []
    if not research_document.strip():
        missing_items.append('research document')
    if not hypothesis.strip():
        missing_items.append('hypothesis')
    if not able_info.strip():
        missing_items.append('ABLE table')
    if not data_discovery.strip():
        missing_items.append('data discovery information')
    
    if missing_items:
        error_msg = f'Missing required information: {", ".join(missing_items)}. Please complete previous steps.'
        return jsonify({
            'success': False, 
            'error': error_msg
        }), 400
    
    try:
        result = await retry_api_call(
            async_plan_hunt,
            research_document=research_document,
            hypothesis=hypothesis, 
            able_info=able_info,
            data_discovery=data_discovery,
            local_context=local_context,
            verbose=verbose_mode,
            max_retries=retry_count
        )
        
        # Extract the final message from the "hunt_planner" agent
        hunt_plan = None
        if hasattr(result, 'messages'):
            hunt_plan = next(
                (message.content for message in reversed(result.messages) if getattr(message, 'source', None) == "hunt_planner"),
                None
            )
        if not hunt_plan:
            if hasattr(result, 'content'):
                hunt_plan = result.content
            else:
                hunt_plan = str(result)
        
        # Store in session
        session['hunt_plan'] = hunt_plan
        return jsonify({
            'success': True, 
            'hunt_plan': hunt_plan
        })
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify({
                'success': False, 
                'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                'detail': str(e)
            }), 500
        else:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/clear-session', methods=['POST'])
def clear_session():
    session.clear()
    return jsonify({'success': True})

# ===== Page Routes =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/research')
def research_page():
    return render_template('research.html')

@app.route('/hypothesis')
def hypothesis_page():
    # Only use the current (editable) hypothesis, never the refined one
    hypo = session.get('hypothesis', '')
    return render_template('hypothesis.html', current_hypothesis=hypo)

@app.route('/refinement')
def refinement_page():
    return render_template('refinement.html')

@app.route('/able-table')
def able_table_page():
    return render_template('able_table.html')

@app.route('/data-discovery')
def data_discovery_page():
    return render_template('data_discovery.html')

@app.route('/hunt-planning')
def hunt_planning_page():
    return render_template('hunt_planning.html')

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/debug')
def debug_page():
    return render_template('debug.html')

# Debug information endpoint
@app.route('/api/debug-info', methods=['GET', 'POST'])
def debug_info():
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

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    
    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    context = (os.path.join(os.path.dirname(__file__), 'cert.pem'),
               os.path.join(os.path.dirname(__file__), 'key.pem'))
    
    print("Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup.")
    print("These are harmless and don't affect the application functionality.")
    print("")
    
    app.run(debug=True, port=8000, ssl_context=context)
