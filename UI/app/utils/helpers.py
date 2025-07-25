"""
Helper utility functions for PEAK Assistant
"""
import os
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv


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
    """Load environment variables from .env file"""
    dotenv_path = find_dotenv_file()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        print("Warning: No .env file found in current or parent directories")


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
    """Try to extract the research report markdown from agent output"""
    import logging
    logger = logging.getLogger(__name__)
    
    report_md = None
    
    # Log the message structure for debugging
    logger.info(f"extract_report_md: Input type: {type(messages)}")
    
    if hasattr(messages, 'messages'):
        # Get all sources for debugging
        sources = [getattr(m, 'source', 'no_source') for m in messages.messages]
        logger.info(f"extract_report_md: Available sources: {sources}")
        
        # Try to find summarizer_agent message
        report_md = next((m.content for m in reversed(messages.messages) if getattr(m, 'source', None) == "summarizer_agent"), None)
        
        if not report_md:
            # Try alternative sources as fallback
            logger.info("extract_report_md: No summarizer_agent found, trying fallbacks...")
            
            # Try summarizer (without _agent suffix)
            report_md = next((m.content for m in reversed(messages.messages) if getattr(m, 'source', None) == "summarizer"), None)
            
            if not report_md:
                # Try any message that looks like a report (contains markdown headers)
                for m in reversed(messages.messages):
                    content = getattr(m, 'content', '')
                    if content and ('# ' in content or '## ' in content) and len(content) > 200:
                        logger.info(f"extract_report_md: Found report-like content from source: {getattr(m, 'source', 'unknown')}")
                        report_md = content
                        break
                        
            if not report_md:
                # Last resort - get the longest message content
                longest_msg = max(messages.messages, key=lambda m: len(getattr(m, 'content', '')), default=None)
                if longest_msg and hasattr(longest_msg, 'content'):
                    logger.info(f"extract_report_md: Using longest message from source: {getattr(longest_msg, 'source', 'unknown')}")
                    report_md = longest_msg.content
    
    # Additional fallback strategies
    if not report_md:
        if isinstance(messages, str):
            report_md = messages
        elif hasattr(messages, 'content'):
            report_md = messages.content
        else:
            logger.warning("extract_report_md: No suitable content found, falling back to string representation")
            # Instead of str(messages), try to extract any readable content
            if hasattr(messages, '__dict__'):
                logger.info(f"extract_report_md: Message attributes: {list(messages.__dict__.keys())}")
            report_md = "Error: Could not extract report content from agent response. Please try again."
    
    logger.info(f"extract_report_md: Extracted report length: {len(report_md) if report_md else 0}")
    return report_md


def extract_accepted_hypothesis(task_result):
    """Find the last message from the 'critic' agent and extract the hypothesis."""
    if hasattr(task_result, 'messages'):
        for message in reversed(task_result.messages):
            # Check for source attribute for newer AutoGen versions
            source = getattr(message, 'source', None)
            if source == "critic" and isinstance(message.content, str):
                # Clean the hypothesis by removing the acceptance marker
                cleaned_hypothesis = message.content.replace('YYY-HYPOTHESIS-ACCEPTED-YYY', '').strip()
                if cleaned_hypothesis:
                    return cleaned_hypothesis
    
    # Fallback for older formats or if the critic message isn't found as expected
    if hasattr(task_result, 'messages') and task_result.messages:
        # A less specific fallback: find the last message with the marker
        for message in reversed(task_result.messages):
            if isinstance(message.content, str) and 'YYY-HYPOTHESIS-ACCEPTED-YYY' in message.content:
                cleaned_hypothesis = message.content.replace('YYY-HYPOTHESIS-ACCEPTED-YYY', '').strip()
                if cleaned_hypothesis:
                    return cleaned_hypothesis
    
    # Final fallback - return the raw content if available
    if hasattr(task_result, 'content'):
        return task_result.content
    elif hasattr(task_result, 'messages') and task_result.messages:
        return task_result.messages[-1].content if task_result.messages[-1].content else str(task_result)
    else:
        return str(task_result)

# ==============================================================================
# Session Management Utilities
# ==============================================================================

from flask import session

def get_session_value(key, default=None):
    """Safely get a value from the session."""
    return session.get(key, default)

def set_session_value(key, value):
    """Set a value in the session."""
    session[key] = value

def clear_session_key(key):
    """Remove a specific key from the session."""
    session.pop(key, None)

def get_all_session_data():
    """Get a dictionary of all session data, excluding internal keys."""
    if not session:
        return {}
    return {k: v for k, v in session.items() if not k.startswith('_')}

def clear_all_session_data():
    """Clear all data from the session."""
    session.clear()
