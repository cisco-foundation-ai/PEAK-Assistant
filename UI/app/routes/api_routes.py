"""
API routes for PEAK Assistant - AI-powered threat hunting operations
"""

import re
import logging
from flask import Blueprint, request, jsonify, session
from autogen_agentchat.messages import TextMessage, UserMessage

from research_assistant import researcher as async_researcher

from able_assistant import able_table as async_able_table

# Import data discovery function
from data_assistant import (
    identify_data_sources as async_identify_data_sources,
)

from ..utils.decorators import async_action, handle_async_api_errors
from ..utils.helpers import (
    extract_report_md,
    extract_accepted_hypothesis,
    get_session_value,
    set_session_value,
    clear_session_key,
)

# Import callback functions for message tracing
from utils.agent_callbacks import preprocess_messages_logging, postprocess_messages_logging

# Create API blueprint
api_bp = Blueprint("api", __name__, url_prefix="/api")

# Global variables for initial context
INITIAL_LOCAL_CONTEXT = None


@api_bp.route("/research", methods=["POST"])
@async_action
@handle_async_api_errors
async def research():
    """Generate or refine research report using AI agents"""
    data = request.get_json()
    topic = data.get("topic")
    previous_report = data.get("previous_report")
    feedback = data.get("feedback")
    verbose_mode = data.get("verbose", False)

    # Get local context from session
    local_context = get_session_value("local_context", INITIAL_LOCAL_CONTEXT)

    # Import the researcher function and TextMessage

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

    # Get authenticated user context for OAuth-enabled MCP servers
    user_id = session.get("user_id")
    
    # Check if callback tracing is enabled
    callback_tracing_enabled = session.get("callback_tracing_enabled", False)
    
    # Prepare callback parameters
    callback_kwargs = {}
    if callback_tracing_enabled:
        callback_kwargs.update({
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "researcher"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "researcher"},
        })

    # Run the researcher with user context
    result = await async_researcher(
        technique=topic,
        local_context=local_context,
        verbose=verbose_mode,
        previous_run=previous_run,
        user_id=user_id,
        **callback_kwargs
    )

    # Extract the report markdown
    report_md = extract_report_md(result)

    # Store in session
    set_session_value("report_md", report_md)
    return jsonify({"success": True, "report": report_md})


@api_bp.route("/hypothesize", methods=["POST"])
@async_action
@handle_async_api_errors
async def hypothesize():
    """Generate threat hunting hypotheses"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=== HYPOTHESIS GENERATION DEBUG START ===")
    
    # Get research report from session (no request data needed)
    report_md = get_session_value("report_md", "")
    logger.info(f"report_md length: {len(report_md) if report_md else 0}")

    if not report_md:
        logger.error("No research report available - this should be the 400 cause")
        return jsonify({"success": False, "error": "No research report available"}), 400

    local_context = get_session_value(
        "local-context", ""
    )  # Get local context from session
    logger.info(f"local_context length: {len(local_context) if local_context else 0}")

    # Import hypothesizer
    from hypothesis_assistant.hypothesis_assistant_cli import (
        hypothesizer as async_hypothesizer,
    )
    
    logger.info("About to call async_hypothesizer")
    logger.info(f"Parameters - user_input: None, research_document length: {len(report_md)}, local_context length: {len(local_context)}")

    hypos = await async_hypothesizer(
        user_input=None,  # No specific user input for auto-generation
        research_document=report_md,  # Pass the research report as the document
        local_context=local_context,  # Pass local context
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
    set_session_value("hypotheses", hypos)

    return jsonify({"success": True, "hypotheses": hypos})


@api_bp.route("/save-hypothesis", methods=["POST"])
def save_hypothesis():
    """Save a hypothesis to the session without refinement"""
    data = request.json
    hypothesis = data.get("hypothesis")
    if not hypothesis:
        return jsonify({"success": False, "error": "No hypothesis provided"}), 400
    prev_hypo = get_session_value("hypothesis")
    # Store in session
    set_session_value("hypothesis", hypothesis)
    # Only clear refined_hypothesis if the hypothesis actually changed
    if prev_hypo != hypothesis:
        clear_session_key("refined_hypothesis")
    return jsonify({"success": True})


@api_bp.route("/refine", methods=["POST"])
@async_action
@handle_async_api_errors
async def refine():
    """Refine a threat hunting hypothesis using AI agents"""
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    hypothesis = data.get("hypothesis")
    feedback = data.get("feedback")
    _verbose_mode = data.get("verbose", False)

    # Get research report from session
    research_report = get_session_value("report_md", "")
    if not research_report:
        return jsonify(
            {
                "success": False,
                "error": "No research report found in session. Please complete the research phase first.",
            }
        ), 400

    # Get local context from session
    local_context = get_session_value("local_context", INITIAL_LOCAL_CONTEXT)

    from autogen_agentchat.messages import TextMessage
    from hypothesis_assistant.hypothesis_refiner_cli import refiner as async_refiner

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
    
    # Check if callback tracing is enabled
    callback_tracing_enabled = session.get("callback_tracing_enabled", False)
    
    # Prepare callback parameters
    callback_kwargs = {}
    if callback_tracing_enabled:
        callback_kwargs.update({
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "refiner"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "refiner"},
        })

    # Explicitly pass keyword arguments to the refiner function
    result = await async_refiner(
        hypothesis=hypothesis,
        local_context=local_context,
        research_document=research_report,
        previous_run=previous_run,
        **callback_kwargs
    )

    # Extract the refined hypothesis
    refined_hypothesis = extract_accepted_hypothesis(result)

    # Store in session under the correct key
    set_session_value("refined_hypothesis", refined_hypothesis)
    return jsonify({"success": True, "refined_hypothesis": refined_hypothesis})


@api_bp.route("/able-table", methods=["POST"])
@async_action
@handle_async_api_errors
async def able_table():
    """Generate ABLE (Adversary Behavior Learning Exercise) table"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    # Get hypothesis, falling back through the session states
    hypothesis = (
        data.get("hypothesis")
        or get_session_value("refined_hypothesis")
        or get_session_value("hypothesis")
    )
    if not hypothesis:
        return jsonify(
            {"success": False, "error": "No hypothesis found in request or session."}
        ), 400

    # Get other data from request and session
    feedback = data.get("feedback")
    current_able_table = data.get("current_able_table")
    report_md = get_session_value("report_md", "")
    local_context = get_session_value("local_context", INITIAL_LOCAL_CONTEXT)

    # Import necessary modules

    # Construct the message history for feedback
    previous_run = []
    if feedback and current_able_table:
        previous_run = [
            UserMessage(
                content=f"The current ABLE draft is: {current_able_table}\n",
                source="user",
            ),
            UserMessage(content=f"User feedback: {feedback}\n", source="user"),
        ]

    # Call the able_table function from the CLI module
    able_md = await async_able_table(
        hypothesis=hypothesis,
        research_document=report_md,
        local_context=local_context,
        previous_run=previous_run,
    )
    # Store result in session
    set_session_value("able_table_md", able_md)
    return jsonify({"success": True, "able_table": able_md})


@api_bp.route("/data-discovery", methods=["GET", "POST"])
@async_action
@handle_async_api_errors
async def data_discovery():
    """Analyze available data sources for hunting"""
    if request.method == "GET":
        # Return existing data sources from session
        return jsonify(
            {
                "data_sources_md": get_session_value("data_sources_md", ""),
                "success": True,
            }
        )

    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    # Use refined hypothesis if available, else fallback to original
    hypothesis = (
        data.get("hypothesis")
        or get_session_value("refined_hypothesis")
        or get_session_value("hypothesis", "")
    )
    report_md = data.get("report_md") or get_session_value("report_md", "")
    able_table_md = data.get("able_table_md") or get_session_value("able_table_md", "")
    feedback = data.get("feedback")
    current_data_sources = data.get("current_data_sources")
    _retry_count = int(data.get("retry_count", 3))
    verbose_mode = data.get("verbose_mode", False)
    local_context = get_session_value(
        "local-context", ""
    )  # Get local context from session

    if not hypothesis:
        return jsonify({"success": False, "error": "No hypothesis provided"}), 400

    if not report_md:
        return jsonify({"success": False, "error": "No research report available"}), 400

    # MCP configuration now handled by configuration file system

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

    # Check if callback tracing is enabled
    callback_tracing_enabled = session.get("callback_tracing_enabled", False)
    
    # Prepare callback parameters
    callback_kwargs = {}
    if callback_tracing_enabled:
        callback_kwargs.update({
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "data_discovery"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "data_discovery"},
        })
    
    result = await async_identify_data_sources(
        hypothesis=hypothesis,
        research_document=report_md,
        able_info=able_table_md,
        local_context=local_context,  # Pass local context to the function
        verbose=verbose_mode,
        previous_run=messages,
        **callback_kwargs
        # Note: max_retries parameter removed as it's not supported by this function
    )
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
    set_session_value("data_sources_md", data_sources_md)
    return jsonify({"success": True, "data_sources": data_sources_md})


@api_bp.route("/hunt-plan", methods=["POST"])
@async_action
@handle_async_api_errors
async def hunt_plan():
    """Generate comprehensive hunt plan using AI agents"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    # Get hypothesis, falling back through the session states
    hypothesis = (
        data.get("hypothesis")
        or get_session_value("refined_hypothesis")
        or get_session_value("hypothesis")
    )
    if not hypothesis:
        return jsonify(
            {"success": False, "error": "No hypothesis found in request or session."}
        ), 400

    # Get other required data
    report_md = data.get("report_md") or get_session_value("report_md", "")
    able_table_md = data.get("able_table_md") or get_session_value("able_table_md", "")
    data_sources_md = data.get("data_sources_md") or get_session_value(
        "data_sources_md", ""
    )
    feedback = data.get("feedback")
    current_hunt_plan = data.get("current_hunt_plan")
    _retry_count = int(data.get("retry_count", 3))
    verbose_mode = data.get("verbose_mode", False)
    local_context = get_session_value("local_context", INITIAL_LOCAL_CONTEXT)

    if not report_md:
        return jsonify({"success": False, "error": "No research report available"}), 400

    if not able_table_md:
        return jsonify({"success": False, "error": "No ABLE table available"}), 400

    if not data_sources_md:
        return jsonify(
            {"success": False, "error": "No data sources information available"}
        ), 400

    # Set up the conversation history for feedback
    messages = []
    if feedback and current_hunt_plan:
        messages.append(
            TextMessage(
                content=f"The current hunt plan draft is: {current_hunt_plan}\n",
                source="user",
            )
        )
        messages.append(
            TextMessage(content=f"User feedback: {feedback}\n", source="user")
        )

    # Import hunt planning function
    from planning_assistant import (
        plan_hunt as async_hunt_planner,
    )
    
    # Check if callback tracing is enabled
    callback_tracing_enabled = session.get("callback_tracing_enabled", False)
    
    # Prepare callback parameters
    callback_kwargs = {}
    if callback_tracing_enabled:
        callback_kwargs.update({
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "hunt_planner"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "hunt_planner"},
        })

    result = await async_hunt_planner(
        hypothesis=hypothesis,
        research_document=report_md,
        able_info=able_table_md,
        data_discovery=data_sources_md,
        local_context=local_context,
        verbose=verbose_mode,
        previous_run=messages,
        **callback_kwargs
        # Note: max_retries parameter removed as it's not supported by this function
    )

    # Extract the hunt plan from the result
    hunt_plan_md = None
    if hasattr(result, "messages"):
        hunt_plan_md = next(
            (
                message.content
                for message in reversed(result.messages)
                if getattr(message, "source", None) == "hunt_planner"
            ),
            None,
        )
    if not hunt_plan_md:
        if hasattr(result, "content"):
            hunt_plan_md = result.content
        else:
            hunt_plan_md = str(result)

    # Store in session
    set_session_value("hunt_plan_md", hunt_plan_md)
    return jsonify({"success": True, "hunt_plan": hunt_plan_md})
