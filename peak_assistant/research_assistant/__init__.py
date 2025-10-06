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

from typing import Optional

import traceback

from autogen_agentchat.messages import TextMessage
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_agentchat.base import TaskResult

from ..utils.llm_factory import get_model_client
from ..utils.mcp_config import get_client_manager, setup_mcp_servers


async def researcher(
    technique: str,
    local_context: str,
    verbose: bool = False,
    previous_run: list = list(),
    mcp_server_group_external: str = "research-external",
    mcp_server_group_internal: str = "research-internal",
    user_id: Optional[str] = None,
    msg_preprocess_callback=None,
    msg_preprocess_kwargs=None,
    msg_postprocess_callback=None,
    msg_postprocess_kwargs=None,
) -> TaskResult:
    """
    Orchestrates a multi-agent, multi-stage research workflow to generate a
    comprehensive cybersecurity threat hunting report for a specified
    technique or behavior.

    This function coordinates a team of specialized agents—search, research
    critic, summarizer, and summary critic—each with distinct roles in
    researching, verifying, summarizing, and validating information about a
    cybersecurity technique. The process is iterative and continues until a
    high-quality, expert-level markdown report is produced and approved.

    Args:
        technique (str, optional): The name or description of the threat actor technique or behavior to research.
        local_context (str, optional): Additional context or constraints to guide the research (e.g., environment, use case).
        verbose (bool, optional): If True, streams detailed output to the console; otherwise, runs silently. Defaults to False.
        previous_run (list, optional): List of conversation messages used to continue or resume a prior research session.

    Returns:
        A TaskResult object containing all the agent messages, including the final
        report, or a string error message if the process fails.

    Raises:
        Exception: If an error occurs during the research or report generation process.
    """

    # NOTE: This prompt is used for both the external and internal search agents.
    # They're basically the same, just with different MCP tools.
    search_system_prompt = """
        You are a world-class research assistant specializing in deep, high-quality
        technical research to assist cybersecurity threat hunters. Given a threat actor
        behavior or technique, your primary goal is to uncover authoritative, comprehensive,
        and up-to-date information using the provided search tool.

        Decompose broad or complex queries into precise, targeted search terms to
        maximize result relevance. Critically evaluate sources for credibility,
        technical depth, and originality. Prioritize peer-reviewed papers,
        official documentation, and reputable industry publications.

        Always use your tools to gather information. Never provide information
        without using your tools.         

        Synthesize findings from multiple independent sources, cross-verifying
        facts and highlighting consensus or discrepancies. Since you are researching
        threat actor behaviors, be sure to include relevant samples of log entries, code,
        or detection rules that can be used to identify the behavior if available.

        For each piece of information, clearly explain its relevance, technical
        significance, and how it addresses the research query. Provide detailed,
        nuanced explanations suitable for expert and highly-technical audiences.

        You may need to make multiple calls to your tools to gather all the
        information you need to answer the research question.

        When receiving feedback from a verifier agent, use your tools to
        iteratively refine your research, address gaps, and ensure the highest
        standard of accuracy and completeness.

        Always cite your sources and include links for further reading.
"""
    summarizer_system_prompt = """
        You are cybersecurity threat hunting report creator. Your role is to provide a
        detailed markdown summary of the research as a report to the user. Remember
        that your audience is composed of expert cybersecurity threat hunters and
        researchers. Your summary should be comprehensive, well-structured, and
        technically rigorous, with a high level of detail. The report should contain
        everything a threat huntert would need in order to begin planning their hunt
        for this technique.

        Format the output as a simple Markdown report. Be sure to include these sections:
        - A brief descriptive title. This should just be the name of the technique,
          if there is one in common use. Otherwise, make up something short. (e.g.,
          "Kerberoasting", "Lateral Movement via SMB", "Credential Dumping from Memory")
        - The relevant MITRE ATT&CK ids & URLs. If there are multiple ATT&CK ids, list
          them in the order they are most commonly used in the attack lifecycle.
        - A description of why this technique is used. Call this section "Overview".
        - A description of any known threat actors that use this technique, and how they
          use it. If there are multiple threat actors, list them in the order they are
          most commonly associated with this technique. If this technique is in wide
          use by many threat actors, just note that instead. Call this section "Threat Actors".
        - A detailed description of how the technqique is performed, written for a
          knowledgable technical audience. Include example log entries, commands, or code, as
          appropriate. Explain things in enough detail that a technically knowledgable
          threat hunter or red teamer could replicate the process step-by-step.
          Include details about what each step does and why. Call this section
          "Technique Details".
        - A description of how to detect this technique. Include published detection
          rules or signatures if you found any, giving priority to content for
          detection platforms or SIEMs the user is using. Call this
          section "Detection".
        - A detailed description of the typical datasets that would be required to
          hunt for this activity. Include details about what each dataset contains
          and how it can be used to identify this activity. It's OK if there are
          more than one datasets that could be used, or if multiple datasets must
          be used in conjuction with each (if this is the case, be sure to mention
          it). When feasible, include sample log entries and details about the
          fields and what they mean, especially the fields that are most important   
          for identifying this activity. The sample log entries are important,
          so please try hard to find good ones to include. For every dataset you
          mention, include a link to a page that documents that dataset and its
          fields, if you can find one. Prefer pages from official documentation
          for that data, but if they are not available, select the most comprehensive
          and understandable page you can find. Call this section "Typical Datasets".
        - A list of externally published threat hunt methodologies for this technique. 
          Do not include local hunts. For each, include a short description of exactly 
          what they're looking for and how they look for it. Call this section "Published Hunts".
        - A summary of any local information about previous times you have hunted this
          topic or it has been found in security incidents. Begin with a table that groups
          each item that pertains to the same hunt together (e.g., all tickets and all wiki
          pages for the same hunt), summarizes the data used, data analysis technique(s),
          and key findings for each hunt. Column headings should be "Hunt" (include links here), 
          "Summary", and "Key Findings". Concentrate on hunts that focus on the current 
          topic or that feature the topic in some way. Be sure to include links to all 
          relevant sources. If there is no relevant local information, write "No local
          hunt information available." Call this section "Previous Hunting Information".
        - A list of tools threat actors commonly use to perform this technique.
          Call this section "Commonly-Used Tools".
        - A numbered list of references to all the sourcesq you consulted, including a
          sentence summarizing the notable information or reason why hunters
          might want to consult the reference. If a MITRE ATT&CK entry
          is included, be sure to list it first. If a MITRE CAPEC entry is included,
          list it second. For everything else, list them in the order of helpfulness,
          most helpful or most relevant first. For all entries in this section,
          YOU MUST INCLUDE A URL. If you do not have a URL, do not include the entry.
          Call this section "References".
        - A section listing any other information that would be helpful to a
          threat hunter but that did not fall under any other section. Call this section
          "Other Information".

        Always include each of these sections, even if the section is blank.
        Just write "N/A" if you don't have anything to put in that section. The title
        should be a first-level header (i.e., # Title). The sections should be second-level
        headers (i.e., ## Section Title).

        Do not include any type of conclusion or summary at the end of the report.
        Just end after the final section.

        Summarize the key details in the results found in a natural and
        actionable manner. Where reasonable, your report should have clear comparison
        tables that drive critical insights. Always cite the key sources (where available)
        for facts obtained INSIDE THE MAIN REPORT. Also, where appropriate, you may add
        images if available that illustrate concepts needed for the summary.

        Cite all sources with links. Be concise, technically rigorous, and ensure
        completeness. Remember that your audience is highly technical and needs a
        lot of detail. Include code snippets, log entries, or detection rules where
        applicable. 
"""

    summary_critic_system_prompt = """
         You are a world class cybersecurity threat hunter. Your job is to evaluate
        the summary research report provided by the summarizer agent. Your goal is to
        ensure that the report is complete, accurate, and provides everything necessary
        for a threat hunter to begin planning their hunt for this technique.

        If the user has provided feedback (marked with "User Feedback:"), focus on the
        specific feedback provided and use it to improve the report. If the user has not
        provided feedback, continue to improve the report until it is complete and
        accurate.

        Ensure the report answers ALL of the following questions (not necessarily
        in this order):
        1. What is the short, commonly-accepted name for the technique (not just
           the ATT&CK ID)?
        2. What are the relevant MITRE ATT&CK IDs and their URLs, if applicable?
        3. Why do threat actors use this technique or behavior?
        4. How is this technique or behavior performed? Provide extremely detailed, technical
           instructions suitable for experienced threat hunters. As for more detail if
           necessary.
        5. How can this technique or behavior be detected?
        6. What datasets or types of data are typically required to detect or hunt
           for this activity?
        7. Are there any published threat hunting methodologies for this technique
           or behavior?
        8. Has this technique or behavior been found in previous incidents or threat
           hunts?
        9. What tools are commonly used by threat actors to perform this technique
           or behavior?
        10. Are there specific threat actors known to use this technique or is
           it widely used by many threat actors?

        Remember that we are providing a report to an audence of threat hunters
        and researchers. The report should be comprehensive, well-structured, and
        technically rigorous, with a high level of detail. Don't hesitate to ask for
        more detail if you think it is needed. If necessary, you may also ask for additional
        research to be performed to fill in gaps in the report. Not all threat hunters
        are experts in every aspect of security, so request explanations or examples where
        needed to be sure the report is clear to both experienced and new threat hunters.

        If the report is not complete or does not meet the
        quality standards, you should provide feedback to the summarizer agent and
        ask it to revise the report. You should also provide a list of the specific
        criteria that the report does not meet, and ask the summarizer agent to revise
        the report to meet those criteria.

        You should provide only the minimal amount of output necessary to provide clear
        feedback. Do not mention or provide evidence for report items that
        meet the criteria. Only provide feedback for the items which do not.

        If the report meets all of the criteria, return the string "YYY-TERMINATE-YYY"
        on a line by itself. Do not include any other text.    
"""

    selector_prompt = """
        You are coordinating a cybersecurity research team by selecting the team 
        member to speak/act next. 
        The following team member roles are available:

            {roles}

        Given the current context, select the most appropriate next speaker.
            - The externalsearch agent should search for and analyze information from
              the Internet.
            - The internalsearch agent should search for and analyze information from
              local information sources (e.g., wikis, ticket systems, threat intel databases, etc).
            - The summarizer agent should summarize the research findings (select 
              this role when the research is complete and approved by the research critic).
            - The summary critic agent should evaluate the report from the summarizer
              and ensure it meets the user's needs. 
            - The user feedback agent should request user feedback or approval of the summarizer's 
              report AFTER the summary critic has approved it. 
            - The termination agent should stop the conversation after the user has approved the report.

        You should ONLY select the summarizer agent role if the research is complete and 
        it has been approved by the research critic agent. NEVER call the summarizer agent directly 
        after the search agent. The summary critic agent CAN ask for more research, in
        which case you should select the search agent role. 

        Base your selection on:
            1. Current stage of research
            2. Last speaker's findings or suggestions
            3. Need for verification vs need for new information
            4. The need for addtional detail in the research or the report, if necessary
            5. The need for additional research or more detail in the report
            6. The user's feedback

        For new reports, a typical workflow is:

            1. Internal search agent (multiple calls)
            2. External search agent (multiple calls)
            4. Summarizer agent
            5. Summary critic agent (repeat steps 1-4 as directed by critic)

        If there is already a draft of the report, only call the agent(s) necessary to incorporate
        the user feedback into the report. 

        Read the following conversation, then select the next role to speak Only return the role name.

        {history}
    """

    # Set up MCP servers for research
    mcp_client_manager = get_client_manager()
    connected_servers_external = await setup_mcp_servers(
        mcp_server_group_external, user_id=user_id
    )
    connected_servers_internal = await setup_mcp_servers(
        mcp_server_group_internal, user_id=user_id
    )

    # Get workbenches only from the external research server group
    group_workbenches_external = []
    for server_name in connected_servers_external:
        workbench = mcp_client_manager.get_workbench(server_name, user_id=user_id)
        if workbench:
            group_workbenches_external.append(workbench)

    if not group_workbenches_external:
        error_msg = f"No MCP workbenches available for external research group '{mcp_server_group_external}'. Check your MCP configuration."
        if verbose:
            print(error_msg)
        raise RuntimeError(error_msg)

    # Get workbenches only from the internal research server group
    group_workbenches_internal = []
    for server_name in connected_servers_internal:
        workbench = mcp_client_manager.get_workbench(server_name, user_id=user_id)
        if workbench:
            group_workbenches_internal.append(workbench)

    if not group_workbenches_internal:
        error_msg = f"No MCP workbenches available for internal research group '{mcp_server_group_internal}'. Skipping local research."
        if verbose:
            print(error_msg)

    # Create model clients for all agents
    external_search_client = await get_model_client(agent_name="external_search_agent")
    summarizer_client = await get_model_client(agent_name="summarizer_agent")
    summary_critic_client = await get_model_client(agent_name="summary_critic")
    research_team_lead_client = await get_model_client(agent_name="research_team_lead")

    participants = [
        AssistantAgent(
            "external_search_agent",
            description="Performs searches and analyzes information using external research tools (i.e. web search)",
            model_client=external_search_client,
            workbench=group_workbenches_external,
            system_message=search_system_prompt,
        ),
        AssistantAgent(
            "summarizer_agent",
            description="Provides a detailed markdown summary of the research as a report to the user.",
            model_client=summarizer_client,
            system_message=summarizer_system_prompt,
        ),
        AssistantAgent(
            "summary_critic",
            description="Evaluates the summary and ensures it meets the user's needs.",
            model_client=summary_critic_client,
            system_message=summary_critic_system_prompt,
        ),
    ]

    if group_workbenches_internal:
        internal_search_client = await get_model_client(agent_name="internal_search_agent")
        participants.append(
            AssistantAgent(
                "internal_search_agent",
                description="Performs searches and analyzes information using local information sources (e.g., wikis, ticket systems, etc)",
                model_client=internal_search_client,
                workbench=group_workbenches_internal,
                system_message=search_system_prompt,
            )
        )

    # Define a termination condition that stops the task once the report
    # has been approved
    text_termination = TextMentionTermination("YYY-TERMINATE-YYY")

    # Create a team
    team = SelectorGroupChat(
        participants=participants,
        model_client=research_team_lead_client,
        termination_condition=text_termination,
        selector_prompt=selector_prompt,
    )

    # Always add these, no matter if it's the first run or a subsequent one
    messages = [
        TextMessage(content=f"Research this technique: {technique}\n", source="user"),
        TextMessage(
            content=f"Additional local context: {local_context}\n", source="user"
        ),
    ]

    # If we have messages from a previous run, add them so we can continue the research
    if previous_run:
        messages = messages + previous_run

    # Preprocess the messages
    if msg_preprocess_callback:
        messages = msg_preprocess_callback(
            msgs=messages, **(msg_preprocess_kwargs or {})
        )

    try:
        # Run the team asynchronously
        if verbose:
            result = await Console(team.run_stream(task=messages), output_stats=True)
        else:
            result = await team.run(task=messages)

        # Postprocess the result
        if msg_postprocess_callback:
            result = msg_postprocess_callback(
                result=result, **(msg_postprocess_kwargs or {})
            )

        return result
    except Exception as e:
        # Catch any other unexpected errors and wrap them
        print(
            f"An unexpected error occurred in the researcher: {e}\n{traceback.format_exc()}"
        )
        raise Exception(
            "An unexpected error occurred while preparing the report."
        ) from e
