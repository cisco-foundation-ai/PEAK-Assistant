"""
Decorators for PEAK Assistant Flask application
"""
import asyncio
from functools import wraps
from flask import jsonify


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
            error_msg = str(e)
            if "500" in error_msg and "Internal server error" in error_msg:
                return jsonify({
                    'success': False, 
                    'error': 'OpenAI API internal server error. Maximum retry attempts reached.',
                    'detail': str(e)
                }), 500
            else:
                return jsonify({'success': False, 'error': str(e)}), 500
    return decorated_function
