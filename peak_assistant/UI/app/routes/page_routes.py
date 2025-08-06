"""
Page rendering routes for PEAK Assistant UI
"""

import os
import sys
import logging
from flask import Blueprint, render_template, jsonify, request, session, g

from ..utils.helpers import (
    get_session_value,
    clear_all_session_data,
    get_all_session_data,
)

# Create page blueprint
page_bp = Blueprint("pages", __name__)


@page_bp.route("/")
def index():
    """Main dashboard page"""
    return render_template("index.html")


@page_bp.route("/research")
def research_page():
    """Topic research interface"""
    return render_template("research.html")


@page_bp.route("/hypothesis")
def hypothesis_page():
    """Hypothesis generation interface"""
    # Only use the current (editable) hypothesis, never the refined one
    hypo = get_session_value("hypothesis", "")
    return render_template("hypothesis.html", current_hypothesis=hypo)


@page_bp.route("/refinement")
def refinement_page():
    """Hypothesis refinement interface"""
    return render_template("refinement.html")


@page_bp.route("/able-table")
def able_table_page():
    """ABLE table generation interface"""
    return render_template("able_table.html")


@page_bp.route("/data-discovery")
def data_discovery_page():
    """Data discovery interface"""
    return render_template("data_discovery.html")


@page_bp.route("/hunt-planning")
def hunt_planning_page():
    """Hunt planning interface"""
    return render_template("hunt_planning.html")


@page_bp.route("/help")
def help_page():
    """Help and documentation page"""
    return render_template("help.html")


@page_bp.route("/debug")
def debug_page():
    """Debug information page"""
    return render_template("debug.html", context={"context":g.context})


@page_bp.route("/api/debug-info", methods=["GET", "POST"])
def debug_info():
    """Debug information and session management endpoint"""
    if request.method == "POST":
        # Clear session (used in debug page)
        clear_all_session_data()
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
            "session_data": get_all_session_data(),
            "callback_tracing_enabled": session.get("callback_tracing_enabled", False),
        }
    )


@page_bp.route("/api/set-callback-tracing", methods=["POST"])
def set_callback_tracing():
    """Set callback tracing state in session"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    enabled = data.get("enabled", False)
    session["callback_tracing_enabled"] = enabled

    return jsonify({"success": True, "enabled": enabled})


@page_bp.route("/api/prerequisite-check", methods=["GET"])
def prerequisite_check():
    """Check all prerequisites for the hunt plan phase."""
    logging.info("--- Running Prerequisite Check ---")
    prerequisites = {
        "report_md": "Research Report",
        "hypothesis": "Hypothesis",
        "able_table_md": "ABLE Table",
        "data_sources_md": "Data Sources",
    }

    missing_items = []
    for key, name in prerequisites.items():
        if key == "hypothesis":
            content = get_session_value("refined_hypothesis") or get_session_value(
                "hypothesis"
            )
            logging.info(
                f"Checking for {name}: Found content = {'True' if content else 'False'}"
            )
        else:
            content = get_session_value(key)
            logging.info(
                f"Checking for {name} ('{key}'): Found content = {'True' if content else 'False'}"
            )

        if not content or not str(content).strip():
            missing_items.append(name)

    all_met = len(missing_items) == 0
    logging.info(
        f"Prerequisite check complete. All met: {all_met}. Missing: {missing_items}"
    )
    logging.info("-------------------------------------")

    return jsonify({"all_met": all_met, "missing": missing_items})
