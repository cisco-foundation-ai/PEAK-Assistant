"""
Decorators for PEAK Assistant Flask application
"""
import asyncio
from functools import wraps
from flask import jsonify
import openai


def async_action(f):
    """Flask async support decorator"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped


def handle_async_api_errors(f):
    """Unified error handling decorator for async API routes"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            # Universally handle any exception. The autogen library often wraps exceptions
            # and includes the traceback in the error message string itself. We must parse it.
            error_message = str(e)
            
            # Find the start of the traceback and truncate the message there.
            traceback_start = error_message.find('Traceback (most recent call last):')
            if traceback_start != -1:
                error_message = error_message[:traceback_start].strip()

            # Try to get a specific status code from the exception, default to 500.
            status_code = 500
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status_code = e.response.status_code
            elif isinstance(e, openai.RateLimitError):
                status_code = 429

            return jsonify({'success': False, 'error': error_message}), status_code
    return decorated_function
