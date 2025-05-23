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

async def async_test_connection():
    """Test if we can connect to Azure OpenAI API and get a response"""
    # Import necessary libraries here to avoid circular imports
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    from autogen_core.models import SystemMessage, UserMessage
    
    # Create a fresh client for testing
    client = AzureOpenAIChatCompletionClient(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        model=os.getenv("AZURE_OPENAI_MODEL"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY")
    )
    
    # In newer version of autogen, UserMessage requires a 'source' field
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Hello, please respond with a very short message if you're working.", source="user")
    ]
    
    response = await client.create(messages)
    return response.content

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
from research_assistant.research_assistant_cli import researcher as async_researcher
from hypothesis_assistant.hypothesis_assistant_cli import hypothesizer as async_hypothesizer
from hypothesis_assistant.hypothesis_refiner_cli import refiner as async_refiner
from able_assistant.able_assistant_cli import able_table as async_able_table

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Configure server-side session storage
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(tempfile.gettempdir(), 'flask_session')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'peak_assistant_'
Session(app)  # Initialize Flask-Session

# ===== API Routes =====

@app.route('/api/test-connection', methods=['POST'])
@async_action
async def test_connection():
    try:
        response = await async_test_connection()
        return jsonify({'success': True, 'message': response})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/research', methods=['POST'])
@async_action
async def research():
    data = request.json
    topic = data.get('topic')
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    
    if not topic:
        return jsonify({'success': False, 'error': 'No topic provided'}), 400
    
    try:
        # Use the agent framework
        messages = await retry_api_call(
            async_researcher, 
            topic, 
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
    
    try:
        hypos = await retry_api_call(
            async_hypothesizer, 
            report_md, 
            report_md,
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
    
    # Store in session
    session['hypothesis'] = hypothesis
    session.pop('refined_hypothesis', None)  # Clear any previous refinement
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
    
    try:
        refined = await retry_api_call(
            async_refiner, 
            hypothesis, 
            '', 
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
    hypothesis = data.get('hypothesis') or session.get('hypothesis', '')
    report_md = data.get('report_md') or session.get('report_md', '')
    retry_count = int(data.get('retry_count', 3))
    # verbose_mode is ignored for able_table, as it is not supported
    
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400
    
    try:
        able_md = await retry_api_call(
            async_able_table, 
            hypothesis, 
            report_md,
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

@app.route('/api/download/markdown', methods=['POST'])
def download_markdown():
    data = request.json
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

@app.route('/api/download/pdf', methods=['POST'])
def download_pdf():
    data = request.json
    content = data.get('content')
    filename = data.get('filename', 'download.pdf')
    
    if not content:
        return jsonify({'success': False, 'error': 'No content provided'}), 400
    
    # Convert markdown to PDF
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

# ===== Page Routes =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/research')
def research_page():
    return render_template('research.html')

@app.route('/hypothesis')
def hypothesis_page():
    return render_template('hypothesis.html')

@app.route('/refinement')
def refinement_page():
    return render_template('refinement.html')

@app.route('/able-table')
def able_table_page():
    return render_template('able_table.html')

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
    
    # Get environment variables (without sensitive values)
    env_vars = {
        'AZURE_OPENAI_DEPLOYMENT': os.getenv('AZURE_OPENAI_DEPLOYMENT', 'Not set'),
        'AZURE_OPENAI_MODEL': os.getenv('AZURE_OPENAI_MODEL', 'Not set'),
        'AZURE_OPENAI_API_VERSION': os.getenv('AZURE_OPENAI_API_VERSION', 'Not set'),
        'AZURE_OPENAI_ENDPOINT': 'REDACTED' if os.getenv('AZURE_OPENAI_ENDPOINT') else 'Not set',
        'AZURE_OPENAI_API_KEY': 'REDACTED' if os.getenv('AZURE_OPENAI_API_KEY') else 'Not set',
        'TAVILY_API_KEY': 'REDACTED' if os.getenv('TAVILY_API_KEY') else 'Not set',
    }
    
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
    app.run(debug=True, port=8000, ssl_context=context)
