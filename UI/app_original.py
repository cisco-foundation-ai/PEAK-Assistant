#!/usr/bin/env python3
from datetime import timedelta
import tempfile
import os
import re
import sys
import asyncio
import io
import warnings
import logging
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from markdown_pdf import MarkdownPdf, Section
from flask_session import Session  # type: ignore[import-untyped]
from autogen_agentchat.messages import TextMessage
from flask_sqlalchemy import SQLAlchemy


from hypothesis_assistant import (
    hypothesizer,
)
from hypothesis_assistant.hypothesis_refiner_cli import refiner
from data_assistant import (
    identify_data_sources as async_identify_data_sources,
)
from planning_assistant import plan_hunt as async_plan_hunt
from utils import load_env_defaults


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
    if hasattr(messages, "messages"):
        report_md = next(
            (
                m.content
                for m in reversed(messages.messages)
                if getattr(m, "source", None) == "summarizer"
            ),
            None,
        )
    if not report_md:
        if isinstance(messages, str):
            report_md = messages
        elif hasattr(messages, "content"):
            report_md = messages.content
        else:
            report_md = str(messages)
    return report_md


def extract_accepted_hypothesis(task_result):
    # Find the last message from the 'critic' agent and extract the hypothesis.
    if hasattr(task_result, "messages"):
        for message in reversed(task_result.messages):
            # Check for source attribute for newer AutoGen versions
            source = getattr(message, "source", None)
            if source == "critic" and isinstance(message.content, str):
                # Clean the hypothesis by removing the acceptance marker
                cleaned_hypothesis = message.content.replace(
                    "YYY-HYPOTHESIS-ACCEPTED-YYY", ""
                ).strip()
                if cleaned_hypothesis:
                    return cleaned_hypothesis

    # Fallback for older formats or if the critic message isn't found as expected
    if hasattr(task_result, "messages") and task_result.messages:
        # A less specific fallback: find the last message with the marker
        for message in reversed(task_result.messages):
            if (
                isinstance(message.content, str)
                and "YYY-HYPOTHESIS-ACCEPTED-YYY" in message.content
            ):
                cleaned_hypothesis = message.content.replace(
                    "YYY-HYPOTHESIS-ACCEPTED-YYY", ""
                ).strip()
                if cleaned_hypothesis:
                    return cleaned_hypothesis

    # Final fallback - return the raw content if available
    if hasattr(task_result, "content"):
        return task_result.content
    elif hasattr(task_result, "messages") and task_result.messages:
        return (
            task_result.messages[-1].content
            if task_result.messages[-1].content
            else str(task_result)
        )
    else:
        return str(task_result)


def handle_async_api_errors(f):
    """Unified error handling decorator for async API routes"""

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            if "500" in error_msg and "Internal server error" in error_msg:
                return jsonify(
                    {
                        "success": False,
                        "error": "OpenAI API internal server error. Maximum retry attempts reached.",
                        "detail": str(e),
                    }
                ), 500
            else:
                return jsonify({"success": False, "error": str(e)}), 500

    return decorated_function


# Load .env at app startup
load_env_defaults()

# Add the parent directory to sys.path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Set up logging to suppress HTTP client cleanup errors
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)

# Suppress specific warnings about event loop closure
warnings.filterwarnings("ignore", message=".*Event loop is closed.*")
warnings.filterwarnings("ignore", message=".*Task exception was never retrieved.*")


# Initialize Flask app
app = Flask(__name__)

# --- Load initial local context ---
INITIAL_LOCAL_CONTEXT = None
CONTEXT_FILE_PATH = os.path.join(os.path.dirname(__file__), "context.txt")
if os.path.exists(CONTEXT_FILE_PATH):
    try:
        with open(CONTEXT_FILE_PATH, "r", encoding="utf-8") as f:
            INITIAL_LOCAL_CONTEXT = f.read()
        print(f"Successfully loaded initial context from {CONTEXT_FILE_PATH}")
    except Exception as e:
        print(f"Error loading initial context from {CONTEXT_FILE_PATH}: {e}")
# --- End load initial local context ---

app.secret_key = os.urandom(24)  # For session management

# Configure sessions to be temporary (don't persist across app restarts)
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    hours=1
)  # Short lifetime for temporary sessions

# Configure SQLAlchemy for session storage
app.config["SESSION_TYPE"] = "sqlalchemy"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///peak_sessions.db"
app.config["SESSION_SQLALCHEMY_TABLE"] = "sessions"
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_KEY_PREFIX"] = "peak_assistant_"

db = SQLAlchemy(app)
app.config["SESSION_SQLALCHEMY"] = db
Session(app)  # Initialize Flask-Session


@app.before_request
def load_initial_context_into_session():
    if INITIAL_LOCAL_CONTEXT is not None and "local-context" not in session:
        session["local-context"] = INITIAL_LOCAL_CONTEXT


# Create the session table if it doesn't exist
with app.app_context():
    db.create_all()

ALLOWED_UPLOAD_EXTENSIONS = {".md", ".txt"}
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "peak_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ===== API Routes =====


@app.route("/api/research", methods=["POST"])
@async_action
@handle_async_api_errors
async def research():
    # Generate or refine research report using AI agents
    data = request.get_json()
    topic = data.get("topic")
    previous_report = data.get("previous_report")
    feedback = data.get("feedback")
    verbose_mode = data.get("verbose", False)

    # Get local context from session
    local_context = session.get("local_context", INITIAL_LOCAL_CONTEXT)

    # Import the researcher function and TextMessage
    from research_assistant import researcher as async_researcher

    previous_run = None
    if previous_report and feedback:
        # Construct the conversation history for refinement
        previous_run = [
            TextMessage(
                content=f"The current report draft is: {previous_report}\n",
                source="user",
            ),
            TextMessage(content=f"User feedback: {feedback}\n", source="user"),
        ]

    # Run the researcher
    result = await retry_api_call(
        async_researcher,
        technique=topic,
        local_context=local_context,
        verbose=verbose_mode,
        previous_run=previous_run,
    )

    # Extract the report markdown
    report_md = extract_report_md(result)

    # Store in session
    session["report_md"] = report_md
    return jsonify({"success": True, "report": report_md})


@app.route("/api/hypothesize", methods=["POST"])
@async_action
@handle_async_api_errors
async def hypothesize():
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    report_md = data.get("report_md") or session.get("report_md", "")
    retry_count = int(data.get("retry_count", 3))
    # verbose_mode is ignored for hypothesizer, as it is not supported

    if not report_md:
        return jsonify({"success": False, "error": "No research report available"}), 400

    local_context = session.get("local-context", "")  # Get local context from session

    hypos = await retry_api_call(
        hypothesizer,
        report_md,
        report_md,  # This seems to be duplicated, raw_text is the second param
        local_context=local_context,  # Pass local context
        max_retries=retry_count,
    )

    if isinstance(hypos, str):
        # Split into lines first
        lines = hypos.splitlines()
        cleaned_hypos = []
        for line in lines:
            # Remove leading numbers, dots, dashes, or asterisks followed by a space
            cleaned_line = re.sub(r"^\s*\d+\.\s*|^\s*[-*]\s*", "", line).strip()
            if cleaned_line:
                cleaned_hypos.append(cleaned_line)
        hypos = cleaned_hypos

    # Store in session
    session["hypotheses"] = hypos

    return jsonify({"success": True, "hypotheses": hypos})


@app.route("/api/save-hypothesis", methods=["POST"])
def save_hypothesis():
    """Save a hypothesis to the session without refinement"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    hypothesis = data.get("hypothesis")
    if not hypothesis:
        return jsonify({"success": False, "error": "No hypothesis provided"}), 400
    prev_hypo = session.get("hypothesis")
    # Store in session
    session["hypothesis"] = hypothesis
    # Only clear refined_hypothesis if the hypothesis actually changed
    if prev_hypo != hypothesis:
        session.pop("refined_hypothesis", None)
    return jsonify({"success": True})


@app.route("/api/refine", methods=["POST"])
@async_action
@handle_async_api_errors
async def refine():
    # Refine a threat hunting hypothesis using AI agents
    data = request.get_json()
    hypothesis = data.get("hypothesis")
    feedback = data.get("feedback")
    verbose_mode = data.get("verbose", False)

    # Get research report from session
    research_report = session.get("report_md", "")
    if not research_report:
        return jsonify(
            {
                "success": False,
                "error": "No research report found in session. Please complete the research phase first.",
            }
        ), 400

    # Get local context from session
    local_context = session.get("local_context", INITIAL_LOCAL_CONTEXT)

    from autogen_agentchat.messages import TextMessage

    previous_run = None
    if feedback:
        # Construct the conversation history for refinement
        previous_run = [
            TextMessage(
                content=f"The current refined hypothesis is: {hypothesis}\n",
                source="user",
            ),
            TextMessage(content=f"User feedback: {feedback}\n", source="user"),
        ]

    # Log the hypothesis being sent to the refiner for debugging
    logging.warning(f"Calling async_refiner with hypothesis: {hypothesis[:100]}...")

    # Explicitly pass keyword arguments to the refiner function
    result = await retry_api_call(
        refiner,
        hypothesis=hypothesis,
        local_context=local_context,
        research_document=research_report,
        verbose=verbose_mode,
        previous_run=previous_run,
    )

    # Extract the refined hypothesis
    refined_hypothesis = extract_accepted_hypothesis(result)

    # Store in session under the correct key
    session["refined_hypothesis"] = refined_hypothesis
    return jsonify({"success": True, "refined_hypothesis": refined_hypothesis})


@app.route("/api/able-table", methods=["POST"])
@async_action
@handle_async_api_errors
async def able_table():
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    # Get hypothesis, falling back through the session states
    hypothesis = (
        data.get("hypothesis")
        or session.get("refined_hypothesis")
        or session.get("hypothesis")
    )
    if not hypothesis:
        return jsonify(
            {"success": False, "error": "No hypothesis found in request or session."}
        ), 400

    # Get other data from request and session
    feedback = data.get("feedback")
    current_able_table = data.get("current_able_table")
    report_md = session.get("report_md", "")
    local_context = session.get("local_context", INITIAL_LOCAL_CONTEXT)

    # Import necessary modules
    from able_assistant import able_table
    from autogen_core.models import UserMessage

    # Construct the message history for feedback
    previous_run = None
    if feedback and current_able_table:
        previous_run = [
            UserMessage(
                content=f"The current ABLE draft is: {current_able_table}\n",
                source="user",
            ),
            UserMessage(content=f"User feedback: {feedback}\n", source="user"),
        ]

    # Call the able_table function from the CLI module
    able_md = await retry_api_call(
        able_table,
        hypothesis=hypothesis,
        research_document=report_md,
        local_context=local_context,
        previous_run=previous_run,
    )
    # Store result in session
    session["able_table_md"] = able_md
    return jsonify({"success": True, "able_table": able_md})


@app.route("/api/data-discovery", methods=["GET", "POST"])
@async_action
@handle_async_api_errors
async def data_discovery():
    if request.method == "GET":
        # Return existing data sources from session
        return jsonify(
            {"data_sources_md": session.get("data_sources_md", ""), "success": True}
        )

    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    # Use refined hypothesis if available, else fallback to original
    hypothesis = (
        data.get("hypothesis")
        or session.get("refined_hypothesis")
        or session.get("hypothesis", "")
    )
    report_md = data.get("report_md") or session.get("report_md", "")
    able_table_md = data.get("able_table_md") or session.get("able_table_md", "")
    feedback = data.get("feedback")
    current_data_sources = data.get("current_data_sources")
    retry_count = int(data.get("retry_count", 3))
    verbose_mode = data.get("verbose_mode", False)
    local_context = session.get("local-context", "")  # Get local context from session

    if not hypothesis:
        return jsonify({"success": False, "error": "No hypothesis provided"}), 400

    if not report_md:
        return jsonify({"success": False, "error": "No research report available"}), 400

    # Get MCP configuration from environment variables
    mcp_command = os.getenv("SPLUNK_MCP_COMMAND")
    mcp_args = os.getenv("SPLUNK_MCP_ARGS").split()

    if not mcp_command or not mcp_args:
        return jsonify(
            {
                "success": False,
                "error": "Splunk MCP configuration missing. Please ensure SPLUNK_MCP_COMMAND and SPLUNK_MCP_ARGS environment variables are set.",
            }
        ), 500

    # Set up the conversation history
    messages = []
    if feedback and current_data_sources:
        messages.append(
            TextMessage(
                content=f"The current data sources draft is: {current_data_sources}\n",
                source="user",
            )
        )
        messages.append(
            TextMessage(content=f"User feedback: {feedback}\n", source="user")
        )

    result = await retry_api_call(
        async_identify_data_sources,
        hypothesis,
        report_md,
        able_info=able_table_md,
        local_context=local_context,  # Pass local context to the function
        mcp_command=mcp_command,
        mcp_args=mcp_args,
        verbose=verbose_mode,
        previous_run=messages,
        max_retries=retry_count,
    )
    if not result:
        return jsonify(
            {"success": False, "error": "No data sources information found"}
        ), 400
    # Extract the final message from the "Data_Discovery_Agent" similar to CLI version
    data_sources_md = None
    if hasattr(result, "messages"):
        data_sources_md = next(
            (
                message.content
                for message in reversed(result.messages)
                if getattr(message, "source", None) == "Data_Discovery_Agent"
            ),
            None,
        )
    if not data_sources_md:
        if hasattr(result, "content"):
            data_sources_md = result.content
        else:
            data_sources_md = str(result)

    # Store in session
    session["data_sources_md"] = data_sources_md
    return jsonify({"success": True, "data_sources": data_sources_md})


@app.route("/api/upload-report", methods=["POST"])
def upload_report():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "No selected file"}), 400
    else:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            return jsonify({"success": False, "error": "Invalid file type"}), 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        session["report_md"] = content
        session["last_topic"] = "[Uploaded]"
        return jsonify({"success": True, "content": content})


@app.route("/api/upload-able-table", methods=["POST"])
def upload_able_table():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "No selected file"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"success": False, "error": "Invalid file type"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    session["able_table_md"] = content
    return jsonify({"success": True, "able_table": content})


@app.route("/api/upload-data-sources", methods=["POST"])
def upload_data_sources():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "No selected file"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"success": False, "error": "Invalid file type"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    session["data_sources_md"] = content
    return jsonify({"success": True, "data_sources": content})


@app.route("/api/download/markdown", methods=["POST", "GET"])
def download_markdown():
    if request.method == "GET":
        return jsonify({"success": False, "error": "GET not supported. Use POST."}), 405
    data = request.json or request.form
    content = data.get("content")
    filename = data.get("filename", "download.md")
    if not content:
        return jsonify({"success": False, "error": "No content provided"}), 400
    buffer = io.BytesIO(content.encode("utf-8"))
    buffer.seek(0)
    return send_file(
        buffer, mimetype="text/markdown", as_attachment=True, download_name=filename
    )


@app.route("/api/download/pdf", methods=["POST", "GET"])
def download_pdf():
    if request.method == "GET":
        return jsonify({"success": False, "error": "GET not supported. Use POST."}), 405
    data = request.json or request.form
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    content = data.get("content")
    if not content:
        return jsonify({"success": False, "error": "No content provided"}), 400

    filename = data.get("filename", "download.pdf")
    if not content:
        return jsonify({"success": False, "error": "No content provided"}), 400
    pdf = MarkdownPdf()
    pdf.add_section(Section(content, toc=False))
    with tempfile.NamedTemporaryFile(mode="wb") as pdf_tmpfile:
        pdf.save(pdf_tmpfile.name)
        return send_file(
            pdf_tmpfile.name,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )


@app.route("/api/hunt-plan", methods=["POST"])
@async_action
async def hunt_plan():
    """Generate hunt plan using AI agents"""
    data = request.json or {}
    retry_count = int(data.get("retry_count", 3))
    verbose_mode = data.get("verbose_mode", False)
    feedback = data.get("feedback", "")
    current_hunt_plan = data.get("current_hunt_plan", "")

    # Get required data from the request body, falling back to session
    research_document = data.get("report_md") or session.get("report_md", "")
    hypothesis = (
        data.get("hypothesis")
        or session.get("refined_hypothesis")
        or session.get("hypothesis", "")
    )
    able_info = data.get("able_table_md") or session.get("able_table_md", "")
    data_discovery = data.get("data_sources_md") or session.get("data_sources_md", "")
    local_context = session.get("local-context", "")

    # Get conversation history or initialize if this is the first call
    previous_messages = session.get("hunt_plan_messages", [])
    # If there's feedback, add messages for the feedback loop
    if feedback and current_hunt_plan:
        previous_messages = [
            TextMessage(
                content=f"The current plan draft is: {current_hunt_plan}\n",
                source="user",
            ),
            TextMessage(content=f"User feedback: {feedback}\n", source="user"),
        ]

    # Convert previous_messages to TextMessage objects if they're stored as dictionaries
    textmessage_list = []
    for msg in previous_messages:
        if isinstance(msg, dict) and "content" in msg and "source" in msg:
            textmessage_list.append(
                TextMessage(content=msg["content"], source=msg["source"])
            )
        elif hasattr(msg, "content") and hasattr(msg, "source"):
            textmessage_list.append(msg)

    # Check prerequisites
    missing_items = []
    if not research_document.strip():
        missing_items.append("research document")
    if not hypothesis.strip():
        missing_items.append("hypothesis")
    if not able_info.strip():
        missing_items.append("ABLE table")
    if not data_discovery.strip():
        missing_items.append("data discovery information")

    if missing_items:
        error_msg = f"Missing required information: {', '.join(missing_items)}. Please complete previous steps."
        return jsonify({"success": False, "error": error_msg}), 400

    try:
        result = await retry_api_call(
            async_plan_hunt,
            research_document=research_document,
            hypothesis=hypothesis,
            able_info=able_info,
            data_discovery=data_discovery,
            local_context=local_context,
            verbose=verbose_mode,
            max_retries=retry_count,
            previous_run=textmessage_list,
        )

        # Extract the final message from the "hunt_planner" agent
        hunt_plan = None
        if hasattr(result, "messages"):
            hunt_plan = next(
                (
                    getattr(message, "content", None)
                    for message in reversed(getattr(result, "messages", []))
                    if getattr(message, "source", None) == "hunt_planner"
                ),
                None,
            )
        if not hunt_plan:
            hunt_plan = getattr(result, "content", str(result))

        # Convert result messages to serializable format
        result_messages = []
        for msg in getattr(result, "messages", []):
            if hasattr(msg, "content") and hasattr(msg, "source"):
                result_messages.append({"content": msg.content, "source": msg.source})

        # Store in session
        session["hunt_plan"] = hunt_plan
        # Store serialized messages (dictionaries) in the session
        serialized_messages = []
        for msg in textmessage_list:
            if hasattr(msg, "content") and hasattr(msg, "source"):
                serialized_messages.append(
                    {"content": msg.content, "source": msg.source}
                )

        session["hunt_plan_messages"] = serialized_messages + result_messages
        return jsonify({"success": True, "hunt_plan": hunt_plan})
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg and "Internal server error" in error_msg:
            return jsonify(
                {
                    "success": False,
                    "error": "OpenAI API internal server error. Maximum retry attempts reached.",
                    "detail": str(e),
                }
            ), 500
        else:
            return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/save-selected-hypothesis", methods=["POST"])
def save_selected_hypothesis():
    """Save a selected hypothesis to the session directly."""
    data = request.json
    if not data or "hypothesis" not in data:
        return jsonify({"success": False, "error": "No hypothesis provided"}), 400

    hypothesis = data["hypothesis"]
    session["hypothesis"] = hypothesis
    # When a new base hypothesis is selected, any previous refinement is invalid.
    session.pop("refined_hypothesis", None)
    print(f"Saved selected hypothesis to session: {hypothesis[:50]}...")

    return jsonify({"success": True})


@app.route("/api/upload-hypothesis", methods=["POST"])
def upload_hypothesis():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in the request."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify(
            {"success": False, "error": "No file selected for uploading."}
        ), 400
    if file:
        try:
            content = file.read().decode("utf-8")
            # Save to session
            session["hypothesis"] = content
            # Clear any old refined hypothesis
            session.pop("refined_hypothesis", None)
            return jsonify({"success": True, "hypothesis": content})
        except Exception as e:
            return jsonify({"success": False, "error": f"Error reading file: {e}"}), 500
    return jsonify({"success": False, "error": "An unknown error occurred."}), 500


@app.route("/api/clear-session", methods=["POST"])
def clear_session():
    # Clear the session data from the server's storage.
    session.clear()
    # The client-side code will handle the redirect after this is successful.
    return jsonify({"success": True})


# ===== Page Routes =====


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/research")
def research_page():
    return render_template("research.html")


@app.route("/hypothesis")
def hypothesis_page():
    # Only use the current (editable) hypothesis, never the refined one
    hypo = session.get("hypothesis", "")
    return render_template("hypothesis.html", current_hypothesis=hypo)


@app.route("/refinement")
def refinement_page():
    return render_template("refinement.html")


@app.route("/able-table")
def able_table_page():
    return render_template("able_table.html")


@app.route("/data-discovery")
def data_discovery_page():
    return render_template("data_discovery.html")


@app.route("/hunt-planning")
def hunt_planning_page():
    return render_template("hunt_planning.html")


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.route("/debug")
def debug_page():
    return render_template("debug.html")


# Debug information endpoint
@app.route("/api/debug-info", methods=["GET", "POST"])
def debug_info():
    if request.method == "POST":
        # Clear session (used in debug page)
        session.clear()
        return jsonify({"success": True})

    # Get environment variables (with redaction for sensitive ones)
    env_vars = {}
    sensitive_keywords = [
        "KEY",
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PASSWD",
        "API_KEY",
        "CONN_STR",
    ]
    for key, value in os.environ.items():
        is_sensitive = any(keyword in key.upper() for keyword in sensitive_keywords)
        env_vars[key] = "[REDACTED]" if is_sensitive and value else value

    # System info
    sys_info = {
        "platform": sys.platform,
        "python_version": sys.version,
    }

    return jsonify(
        {
            "environment": env_vars,
            "system_info": sys_info,
            "session_data": {
                k: session[k] for k in session if k not in ["_permanent", "csrf_token"]
            }
            if session
            else {},
        }
    )


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    context = (
        os.path.join(os.path.dirname(__file__), "cert.pem"),
        os.path.join(os.path.dirname(__file__), "key.pem"),
    )

    print(
        "Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup."
    )
    print("These are harmless and don't affect the application functionality.")
    print("")

    app.run(debug=True, port=8000, ssl_context=context)
