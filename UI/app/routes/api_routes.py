"""
API routes for PEAK Assistant - AI-powered threat hunting operations
"""
import os
import re
import logging
from flask import Blueprint, request, jsonify
from autogen_agentchat.messages import TextMessage, UserMessage

from ..utils.decorators import async_action, handle_async_api_errors
from ..utils.helpers import (
    retry_api_call, 
    extract_report_md, 
    extract_accepted_hypothesis,
    get_session_value,
    set_session_value,
    clear_session_key
)

# Create API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Global variables for initial context
INITIAL_LOCAL_CONTEXT = None


@api_bp.route('/research', methods=['POST'])
@async_action
@handle_async_api_errors
async def research():
    """Generate or refine research report using AI agents"""
    data = request.get_json()
    topic = data.get('topic')
    previous_report = data.get('previous_report')
    feedback = data.get('feedback')
    verbose_mode = data.get('verbose', False)
    
    # Get local context from session
    local_context = get_session_value('local_context', INITIAL_LOCAL_CONTEXT)
    
    # Import the researcher function and TextMessage
    from research_assistant.research_assistant_cli import researcher as async_researcher
    from autogen_agentchat.messages import TextMessage

    previous_run = None
    if previous_report and feedback:
        # Construct the conversation history for refinement
        previous_run = [
            TextMessage(content=f"The current report draft is: {previous_report}\n", source="user"),
            TextMessage(content=f"User feedback: {feedback}\n", source="user")
        ]

    # Run the researcher
    result = await retry_api_call(
        async_researcher, 
        technique=topic, 
        local_context=local_context, 
        verbose=verbose_mode,
        previous_run=previous_run
    )
    
    # Extract the report markdown
    report_md = extract_report_md(result)
    
    # Store in session
    set_session_value('report_md', report_md)
    return jsonify({'success': True, 'report': report_md})


@api_bp.route('/hypothesize', methods=['POST'])
@async_action
@handle_async_api_errors
async def hypothesize():
    """Generate threat hunting hypotheses"""
    data = request.json
    report_md = data.get('report_md') or get_session_value('report_md', '')
    retry_count = int(data.get('retry_count', 3))
    # verbose_mode is ignored for hypothesizer, as it is not supported
    
    if not report_md:
        return jsonify({'success': False, 'error': 'No research report available'}), 400

    local_context = get_session_value('local-context', '')  # Get local context from session
    
    # Import hypothesizer
    from hypothesis_assistant.hypothesis_assistant_cli import hypothesizer as async_hypothesizer
    
    hypos = await retry_api_call(
        async_hypothesizer, 
        report_md, 
        report_md,  # This seems to be duplicated, raw_text is the second param
        local_context=local_context,  # Pass local context
        max_retries=retry_count
    )
    
    if isinstance(hypos, str):
        # Split into lines first
        lines = hypos.splitlines()
        cleaned_hypos = []
        for line in lines:
            # Remove leading numbers, dots, dashes, or asterisks followed by a space
            cleaned_line = re.sub(r'^\s*\d+\.\s*|^\s*[-*]\s*', '', line).strip()
            if cleaned_line:
                cleaned_hypos.append(cleaned_line)
        hypos = cleaned_hypos
    
    # Store in session
    set_session_value('hypotheses', hypos)
    
    return jsonify({'success': True, 'hypotheses': hypos})


@api_bp.route('/save-hypothesis', methods=['POST'])
def save_hypothesis():
    """Save a hypothesis to the session without refinement"""
    data = request.json
    hypothesis = data.get('hypothesis')
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400
    prev_hypo = get_session_value('hypothesis')
    # Store in session
    set_session_value('hypothesis', hypothesis)
    # Only clear refined_hypothesis if the hypothesis actually changed
    if prev_hypo != hypothesis:
        clear_session_key('refined_hypothesis')
    return jsonify({'success': True})


@api_bp.route('/refine', methods=['POST'])
@async_action
@handle_async_api_errors
async def refine():
    """Refine a threat hunting hypothesis using AI agents"""
    data = request.get_json()
    hypothesis = data.get('hypothesis')
    feedback = data.get('feedback')
    verbose_mode = data.get('verbose', False)
    
    # Get research report from session
    research_report = get_session_value('report_md', '')
    if not research_report:
        return jsonify({'success': False, 'error': 'No research report found in session. Please complete the research phase first.'}), 400
    
    # Get local context from session
    local_context = get_session_value('local_context', INITIAL_LOCAL_CONTEXT)
    
    from autogen_agentchat.messages import TextMessage
    from hypothesis_assistant.hypothesis_refiner_cli import refiner as async_refiner

    previous_run = None
    if feedback:
        # Construct the conversation history for refinement
        previous_run = [
            TextMessage(content=f"The current refined hypothesis is: {hypothesis}\n", source="user"),
            TextMessage(content=f"User feedback: {feedback}\n", source="user")
        ]

    # Log the hypothesis being sent to the refiner for debugging
    logging.warning(f"Calling async_refiner with hypothesis: {hypothesis[:100]}...")

    # Explicitly pass keyword arguments to the refiner function
    result = await retry_api_call(
        async_refiner, 
        hypothesis=hypothesis, 
        local_context=local_context, 
        research_document=research_report,
        verbose=verbose_mode,
        previous_run=previous_run
    )
    
    # Extract the refined hypothesis
    refined_hypothesis = extract_accepted_hypothesis(result)
    
    # Store in session under the correct key
    set_session_value('refined_hypothesis', refined_hypothesis)
    return jsonify({'success': True, 'refined_hypothesis': refined_hypothesis})


@api_bp.route('/able-table', methods=['POST'])
@async_action
@handle_async_api_errors
async def able_table():
    """Generate ABLE (Adversary Behavior Learning Exercise) table"""
    data = request.json

    # Get hypothesis, falling back through the session states
    hypothesis = data.get('hypothesis') or get_session_value('refined_hypothesis') or get_session_value('hypothesis')
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis found in request or session.'}), 400

    # Get other data from request and session
    feedback = data.get('feedback')
    current_able_table = data.get('current_able_table')
    report_md = get_session_value('report_md', '')
    local_context = get_session_value('local_context', INITIAL_LOCAL_CONTEXT)
    
    # Import necessary modules
    from able_assistant.able_assistant_cli import able_table
    from autogen_agentchat.messages import UserMessage

    # Construct the message history for feedback
    previous_run = None
    if feedback and current_able_table:
        previous_run = [
            UserMessage(content=f"The current ABLE draft is: {current_able_table}\n", source="user"),
            UserMessage(content=f"User feedback: {feedback}\n", source="user")
        ]

    # Call the able_table function from the CLI module
    able_md = await retry_api_call(
        able_table,
        hypothesis=hypothesis,
        research_document=report_md,
        local_context=local_context,
        previous_run=previous_run
    )
    # Store result in session
    set_session_value('able_table_md', able_md)
    return jsonify({'success': True, 'able_table': able_md})


@api_bp.route('/data-discovery', methods=['GET', 'POST'])
@async_action
@handle_async_api_errors
async def data_discovery():
    """Analyze available data sources for hunting"""
    if request.method == 'GET':
        # Return existing data sources from session
        return jsonify({
            'data_sources_md': get_session_value('data_sources_md', ''),
            'success': True
        })
    
    data = request.json
    # Use refined hypothesis if available, else fallback to original
    hypothesis = data.get('hypothesis') or get_session_value('refined_hypothesis') or get_session_value('hypothesis', '')
    report_md = data.get('report_md') or get_session_value('report_md', '')
    able_table_md = data.get('able_table_md') or get_session_value('able_table_md', '')
    feedback = data.get('feedback')
    current_data_sources = data.get('current_data_sources')
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    local_context = get_session_value('local-context', '')  # Get local context from session

    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis provided'}), 400

    if not report_md:
        return jsonify({'success': False, 'error': 'No research report available'}), 400

    # MCP configuration now handled by configuration file system

    # Set up the conversation history
    messages = []
    if feedback and current_data_sources:
        messages.append(TextMessage(content=f"The current data sources draft is: {current_data_sources}\n", source="user"))
        messages.append(TextMessage(content=f"User feedback: {feedback}\n", source="user"))

    # Import data discovery function
    from data_assistant.data_asssistant_cli import identify_data_sources as async_identify_data_sources
    
    result = await retry_api_call(
        async_identify_data_sources, 
        hypothesis, 
        report_md,
        able_info=able_table_md,
        local_context=local_context,  # Pass local context to the function
        verbose=verbose_mode,
        previous_run=messages,
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
    set_session_value('data_sources_md', data_sources_md)
    return jsonify({'success': True, 'data_sources': data_sources_md})


@api_bp.route('/hunt-plan', methods=['POST'])
@async_action
@handle_async_api_errors
async def hunt_plan():
    """Generate comprehensive hunt plan using AI agents"""
    data = request.json
    
    # Get hypothesis, falling back through the session states
    hypothesis = data.get('hypothesis') or get_session_value('refined_hypothesis') or get_session_value('hypothesis')
    if not hypothesis:
        return jsonify({'success': False, 'error': 'No hypothesis found in request or session.'}), 400
    
    # Get other required data
    report_md = data.get('report_md') or get_session_value('report_md', '')
    able_table_md = data.get('able_table_md') or get_session_value('able_table_md', '')
    data_sources_md = data.get('data_sources_md') or get_session_value('data_sources_md', '')
    feedback = data.get('feedback')
    current_hunt_plan = data.get('current_hunt_plan')
    retry_count = int(data.get('retry_count', 3))
    verbose_mode = data.get('verbose_mode', False)
    local_context = get_session_value('local_context', INITIAL_LOCAL_CONTEXT)
    
    if not report_md:
        return jsonify({'success': False, 'error': 'No research report available'}), 400
    
    if not able_table_md:
        return jsonify({'success': False, 'error': 'No ABLE table available'}), 400
    
    if not data_sources_md:
        return jsonify({'success': False, 'error': 'No data sources information available'}), 400
    
    # Set up the conversation history for feedback
    messages = []
    if feedback and current_hunt_plan:
        messages.append(TextMessage(content=f"The current hunt plan draft is: {current_hunt_plan}\n", source="user"))
        messages.append(TextMessage(content=f"User feedback: {feedback}\n", source="user"))
    
    # Import hunt planning function
    from planning_assistant.planning_assistant_cli import plan_hunt as async_hunt_planner
    
    result = await retry_api_call(
        async_hunt_planner,
        hypothesis=hypothesis,
        research_document=report_md,
        able_info=able_table_md,
        data_discovery=data_sources_md,
        local_context=local_context,
        verbose=verbose_mode,
        previous_run=messages,
        max_retries=retry_count
    )
    
    # Extract the hunt plan from the result
    hunt_plan_md = None
    if hasattr(result, 'messages'):
        hunt_plan_md = next(
            (message.content for message in reversed(result.messages) if getattr(message, 'source', None) == "hunt_planner"),
            None
        )
    if not hunt_plan_md:
        if hasattr(result, 'content'):
            hunt_plan_md = result.content
        else:
            hunt_plan_md = str(result)
    
    # Store in session
    set_session_value('hunt_plan_md', hunt_plan_md)
    return jsonify({'success': True, 'hunt_plan': hunt_plan_md})
