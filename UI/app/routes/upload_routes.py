"""
File upload and download routes for PEAK Assistant
"""
import os
import io
from flask import Blueprint, request, jsonify, session, Response, send_file, current_app
from werkzeug.utils import secure_filename
from markdown_pdf import MarkdownPdf, Section

# Create upload blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/api')

# Global constants
ALLOWED_UPLOAD_EXTENSIONS = {'.md', '.txt'}


@upload_bp.route('/upload-report', methods=['POST'])
def upload_report():
    """Upload research report file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    session['report_md'] = content
    session['last_topic'] = '[Uploaded]'
    return jsonify({'success': True, 'content': content})


@upload_bp.route('/upload-able-table', methods=['POST'])
def upload_able_table():
    """Upload ABLE table file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    try:
        content = file.read().decode('utf-8')
        session['able_table_md'] = content
        return jsonify({'success': True, 'able_table': content})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error reading file: {e}'}), 500


@upload_bp.route('/upload-data-sources', methods=['POST'])
def upload_data_sources():
    """Upload data sources file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    try:
        content = file.read().decode('utf-8')
        session['data_sources_md'] = content
        return jsonify({'success': True, 'data_sources': content})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error reading file: {e}'}), 500


@upload_bp.route('/upload-hypothesis', methods=['POST'])
def upload_hypothesis():
    """Upload hypothesis file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part in the request.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected for uploading.'}), 400
    if file:
        try:
            content = file.read().decode('utf-8')
            # Save to session
            session['hypothesis'] = content
            # Clear any old refined hypothesis
            session.pop('refined_hypothesis', None)
            return jsonify({'success': True, 'hypothesis': content})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error reading file: {e}'}), 500
    return jsonify({'success': False, 'error': 'An unknown error occurred.'}), 500


@upload_bp.route('/download/markdown', methods=['POST', 'GET'])
def download_markdown():
    """Download content as markdown file"""
    if request.method == 'POST':
        data = request.json
        content = data.get('content', '')
        filename = data.get('filename', 'download.md')
    else:
        # GET method - use session data
        content = session.get('report_md', '')
        filename = 'research_report.md'
    
    if not content:
        return jsonify({'success': False, 'error': 'No content to download'}), 400
    
    # Create file-like object
    file_obj = io.BytesIO(content.encode('utf-8'))
    file_obj.seek(0)
    
    return send_file(
        file_obj,
        as_attachment=True,
        download_name=filename,
        mimetype='text/markdown'
    )


@upload_bp.route('/download/pdf', methods=['POST', 'GET'])
def download_pdf():
    """Download content as PDF file"""
    if request.method == 'POST':
        data = request.json
        content = data.get('content', '')
        filename = data.get('filename', 'download.pdf')
    else:
        # GET method - use session data
        content = session.get('report_md', '')
        filename = 'research_report.pdf'
    
    if not content:
        return jsonify({'success': False, 'error': 'No content to download'}), 400
    
    try:
        import tempfile
        
        # Create PDF from markdown using temporary file
        pdf = MarkdownPdf(toc_level=2)
        pdf.add_section(Section(content, toc=False))
        
        # Create temporary file for PDF generation
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_filename = temp_file.name
        
        # Generate PDF to temporary file
        pdf.save(temp_filename)
        
        # Read PDF content from temporary file
        with open(temp_filename, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
        
        # Clean up temporary file
        os.unlink(temp_filename)
        
        # Create file-like object
        file_obj = io.BytesIO(pdf_content)
        file_obj.seek(0)
        
        return send_file(
            file_obj,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'PDF generation failed: {str(e)}'}), 500


@upload_bp.route('/save-selected-hypothesis', methods=['POST'])
def save_selected_hypothesis():
    """Save a selected hypothesis to the session directly."""
    data = request.json
    if not data or 'hypothesis' not in data:
        return jsonify({'success': False, 'error': 'No hypothesis provided in request data.'}), 400
        
    hypothesis = data['hypothesis']
    session['hypothesis'] = hypothesis
    # When a new base hypothesis is selected, any previous refinement is invalid.
    session.pop('refined_hypothesis', None)
    print(f"Saved selected hypothesis to session: {hypothesis[:50]}...")
    
    return jsonify({'success': True})


@upload_bp.route('/clear-session', methods=['POST'])
def clear_session():
    """Clear the session data from the server's storage."""
    session.clear()
    # The client-side code will handle the redirect after this is successful.
    return jsonify({'success': True})
