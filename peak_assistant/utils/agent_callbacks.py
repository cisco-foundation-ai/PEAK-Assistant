# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

"""
Logging callbacks for the PEAK Assistant agents
"""

from autogen_agentchat.messages import TextMessage
from autogen_agentchat.base import TaskResult

def preprocess_messages_logging(
    msgs: list[TextMessage], 
    agent_id: str = "[UNIDENTIFIED]",
    logfile: str = "msgs.txt"
) -> list[TextMessage]:
    with open(logfile, 'a') as f:
        for msg in msgs:
            log_msg = f"""
-----------BEGIN TextMessage----------------------------
Agent ID: {agent_id}
Timestamp: {msg.created_at}
Source:{msg.source}
Content length:{len(msg.content)}
Content:{msg.content}
-----------END TextMessage------------------------------
"""
            f.write(log_msg)
    return msgs

def postprocess_messages_logging(
    result: TaskResult, 
    agent_id: str = "[UNIDENTIFIED]",
    logfile: str = "results.txt"
) -> TaskResult:

    prompt_tokens = 0
    completion_tokens = 0
    first_message_timestamp = None 
    last_message_timestamp = None
    with open(logfile, 'a') as f:
        for msg in result.messages:
            log_msg = f"""
-----------BEGIN TaskResult----------------------------
Agent ID: {agent_id}
Timestamp: {msg.created_at}
Source:{msg.source}
Content length:{len(msg.content)}
Content:{msg.content}
Model usage:{msg.models_usage}
-----------END TaskResult------------------------------
"""
            f.write(log_msg)

            if msg.models_usage:    
                prompt_tokens += msg.models_usage.prompt_tokens
                completion_tokens += msg.models_usage.completion_tokens

            if (first_message_timestamp is None) or (msg.created_at < first_message_timestamp):
                first_message_timestamp = msg.created_at

            last_message_timestamp = msg.created_at

        summary_msg = f"""
-----------BEGIN TaskResult Summary--------------------
Agent ID: {agent_id}
First message timestamp: {first_message_timestamp}
Last message timestamp: {last_message_timestamp}
Duration: {last_message_timestamp - first_message_timestamp}
Stop reason: {result.stop_reason}
Prompt tokens: {prompt_tokens}
Completion tokens: {completion_tokens}
Total tokens: {prompt_tokens + completion_tokens}
-----------END TaskResult Summary----------------------
"""
        f.write(summary_msg)
    
    return result