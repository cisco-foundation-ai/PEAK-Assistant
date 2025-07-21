#!/usr/bin/env python3

import os
import argparse
import asyncio
import re
import sys
from pathlib import Path
import warnings
from dotenv import load_dotenv
import traceback
from markdown_pdf import MarkdownPdf, Section

from tavily import TavilyClient

from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.assistant_auth import PEAKAssistantAuthManager
from utils.azure_client import PEAKAssistantAzureOpenAIClient

def find_dotenv_file():
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / '.env'
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found

def generate_unique_filename(title, extension):
    """Generate a unique filename based on the title and extension."""
    sanitized_title = re.sub(r'[^a-zA-Z0-9_]', '_', title.lower().strip())
    base_filename = f"{sanitized_title}{extension}"
    counter = 0

    while os.path.exists(base_filename):
        counter += 1
        base_filename = f"{sanitized_title} ({counter}){extension}"

    return base_filename

async def tavily_search(
    query: str,
    max_results: int = 15,
    raw_content: bool = False
):
    tavily_client = TavilyClient(
        api_key=os.getenv("TAVILY_API_KEY")
    )

    search_results = tavily_client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_raw_content=raw_content
    )

    return search_results

async def websocket_input():
    return

def get_input_function():
    if os.getenv("FLASK_RUN_FROM_CLI") or os.getenv("WERKZEUG_RUN_MAIN"):
        return websocket_input
    else:
        return input

async def researcher(
    technique: str = None, 
    local_context: str = None,
    verbose: bool = False,
    previous_run: list = None
) -> str:
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
    
    search_system_prompt = """
        You are a world-class research assistant specializing in deep, high-quality 
        technical research to assist cybersecurity threat hunters. Given a threat actor
        behavior or technique, your primary goal is to uncover authoritative, comprehensive, 
        and up-to-date information using the google_search tool.

        Decompose broad or complex queries into precise, targeted search terms to 
        maximize result relevance. Critically evaluate sources for credibility, 
        technical depth, and originality—prioritize peer-reviewed papers, 
        official documentation, and reputable industry publications.

        Synthesize findings from multiple independent sources, cross-verifying 
        facts and highlighting consensus or discrepancies. Since you are researching
        threat actor behaviors, be sure to include relevant samples of log entries, code,
        or detection rules that can be used to identify the behavior if available. 

        For each piece of information, clearly explain its relevance, technical 
        significance, and how it addresses the research query. Provide detailed, 
        nuanced explanations suitable for expert and highly-technical audiences.

        When receiving feedback from a verifier agent, use your tools to 
        iteratively refine your research, address gaps, and ensure the highest 
        standard of accuracy and completeness.

        Always cite your sources and include links for further reading.
    """

    research_critic_system_prompt = """
        You are an expert research verification specialist and expert cybersecurity 
        threat hunter. Your job is to critically evaluate the research findings
        provided by the research assistant. Your goal is to ensure that the
        research is accurate, comprehensive, and technically sound. You will
        review the research findings and provide feedback to the research assistant
        to improve the quality of its research. 
        
        You are not responsible for summarizing the research or providing a final 
        report. NEVER do either of these. Your only focus is on evaluating the
        research and ensuring that it meets the highest standards of quality so that the 
        summarizer agent can create a high-quality report.

        You should provide only the minimal amount of output necessary to provide clear 
        feedback. Do not mention or provide evidence for research items that 
        meet the criteria. Only provide feedback for the items which do not.

        When critiqueing the research findings, be sure to:
        1. Assess the effectiveness and precision of search queries, suggesting 
           improvements if needed.
        2. Identify opportunities for deeper investigation (e.g., recommend 
           following promising links or sources, propose additional research questions 
           relevant to the topic).
        3. Propose additional research angles or perspectives only when they are 
           likely to add significant value—avoid unnecessary scope expansion. 
        4. Track and clearly communicate progress toward fully answering the original 
           research question.
        5. When research is incomplete, end your message with "CONTINUE RESEARCH". 
           When all requirements are met, end with "APPROVED" and provide a 
           comprehensive, well-structured summary in markdown format.

        Ensure the research results answer ALL of the following:
        1. What is the short, commonly-accepted name for the technique (not just 
           the ATT&CK ID)?
        2. What are the relevant MITRE ATT&CK IDs and their URLs, if applicable?
        3. Why do threat actors use this technique or behavior?
        4. How is this technique or behavior performed? Provide detailed, technical 
           instructions suitable for experienced threat hunters.
        5. How can this technique or behavior be detected?
        6. What datasets or types of data are typically required to detect or hunt 
           for this activity?
        7. Are there any published threat hunting methodologies for this technique 
           or behavior?
        8. What tools are commonly used by threat actors to perform this technique 
           or behavior?
        9. Are there specific threat actors known to use this technique or is 
           it widely used by many threat actors?

        Remember that the research assistant does not know the list of your evaluation
        criteria. If it fails to meet any of them, you must point it out and specify how 
        it can improve. If the research assistant does not provide enough information
        to answer one or more of the questions, you must point that out and specify what
        information is missing. 
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
          "Kerberoasting", "Lateral Movement via SMB", "Credential Dumping")
        - The relevant MITRE ATT&CK ids & URLs. If there are multiple ATT&CK ids, list 
          them in the order they are most commonly used in the attack lifecycle.
        - A brief description of why this technique is used. Call this section "Overview".
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
          rules if you found any, giving priority to Splunk/SPL rules. Call this 
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
        - A brief list of published threat hunt methodologies for this technique. For each, 
          include a short description of exactly what their looking for and how they 
          look for it. Call this section "Published Hunts".
        - A brief list of tools threat actors commonly use to perform this technique. 
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

        Your should summarize the key details in the results found in natural an 
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
        8. What tools are commonly used by threat actors to perform this technique 
           or behavior?
        9. Are there specific threat actors known to use this technique or is 
           it widely used by many threat actors?        

        Remember that we are providing a report to an expert audence of threat hunters
        and researchers. The report should be comprehensive, well-structured, and
        technically rigorous, with a high level of detail. Don't hesitate to ask for 
        more detail if you think it is needed. If necessary, you may also ask for additional
        research to be performed to fill in gaps in the report.

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
            - The search agent should search for and analyze information from
            the Internet.
            - The research critic should evaluate progress and guide the research 
            (select this role when there is a need to verify/evaluate progress 
            of the research). 
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

        You should always follow the call to the summarizer critic with a request for 
        user feedback. You may have to iterate the research process multiple times to ensure the 
        resulting report is the best it can be. Based on the user feedback, you may need to 
        revisit one or more of the preceeding roles. 

        Continue the conversation until the user feedback agent has provided 
        approval of the report. At that point, you should select the termination 
        agent as the next speaker.

        Base your selection on:
            1. Current stage of research
            2. Last speaker's findings or suggestions
            3. Need for verification vs need for new information
            4. The need for addtional detail in the research or the report, if necessary
            5. The need for additional research or more detail in the report
            6. The user's feedback
        Read the following conversation. 
        Then select the next role to speak Only return the role name.

        {history}
    """

    auth_mgr = PEAKAssistantAuthManager()
    az_model_client = await PEAKAssistantAzureOpenAIClient().get_client(auth_mgr=auth_mgr)
    az_model_reasoning_client = await PEAKAssistantAzureOpenAIClient().get_client(auth_mgr=auth_mgr, model_type="reasoning")

    search_agent = AssistantAgent(
        "search_agent",
        description="Performs web searches and analyzes information.",
        model_client=az_model_client,
        tools=[tavily_search],
        system_message=search_system_prompt
    )

    research_critic_agent = AssistantAgent(
        "research_critic",
        description="Evaluates progress, ensures completeness, and suggests new research avenues.",
        model_client=az_model_reasoning_client,
        system_message=research_critic_system_prompt
    )

    summarizer_agent = AssistantAgent(
        "summarizer_agent",
        description="Provides a detailed markdown summary of the research as a report to the user.",
        model_client=az_model_client,
        system_message=summarizer_system_prompt
    )

    summary_critic_agent = AssistantAgent(
        "summary_critic",
        description="Evaluates the summary and ensures it meets the user's needs.",
        model_client=az_model_reasoning_client,
        system_message=summary_critic_system_prompt
    )

    # Define a termination condition that stops the task once the report 
    # has been approved
    text_termination = TextMentionTermination("YYY-TERMINATE-YYY")

    # Create a team 
    team = SelectorGroupChat(
        participants=[
                        search_agent, 
                        research_critic_agent, 
                        summarizer_agent, 
                        summary_critic_agent, 
                    ],
        model_client=az_model_client,
        termination_condition=text_termination,
        selector_prompt=selector_prompt
    )

    # Always add these, no matter if it's the first run or a subsequent one
    messages = [
        TextMessage(content=f"Research this technique: {technique}\n", source="user"),
        TextMessage(content=f"Additional local context: {local_context}\n", source="user"),
    ]

    # If we have messages from a previous run, add them so we can continue the research
    if previous_run:
        messages = messages + previous_run 

    try:
        # Run the team asynchronously
        if verbose:
            result = await Console(team.run_stream(task=messages), output_stats=True)
        else:
            result = await team.run(task=messages)

        return result  
    except Exception as e:
        print(f"Error while preparing report: {e}\n{traceback.format_exc()}")
        return "An error occurred while preparing the report."

if __name__ == "__main__":

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Generate a threat hunting report for a specific technique')
    parser.add_argument('-t', '--technique', required=True, help='The cybersecurity technique to research')
    parser.add_argument('-c', '--local_context', help='Additional local context to consider', required=False, default=None)
    parser.add_argument('-e', '--environment', help='Path to specific .env file to use')
    parser.add_argument('-f', '--format', choices=['pdf', 'markdown'], default='markdown', help='Output report format: pdf or markdown')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()

    # Load environment variables
    if args.environment:
        # Use the specified .env file
        dotenv_path = args.environment
        if not os.path.exists(dotenv_path):
            print(f"Error: Specified environment file '{dotenv_path}' not found")
            exit(1)
        load_dotenv(dotenv_path)
    else:
        # Search for .env file
        dotenv_path = find_dotenv_file()
        if dotenv_path:
            load_dotenv(dotenv_path)
        else:
            print("Warning: No .env file found in current or parent directories")

    # Read the contents of the local context if provided
    local_context = None
    if args.local_context:
        try:
            with open(args.local_context, 'r', encoding='utf-8') as file:
                local_context = file.read()
        except FileNotFoundError:
            print(f"Error: Local context file '{args.local_context}' not found")
            exit(1)
        except Exception as e:
            print(f"Error reading local context: {e}")
            exit(1)

    messages = list()
    while True:
        # Run the researcher asynchronously
        task_result = asyncio.run(
            researcher(
                technique=args.technique,
                local_context=local_context,
                verbose=args.verbose,
                previous_run=messages
            )
        )

        # Find the final message from the "summarizer_agent" using next() and a generator expression
        report = next(
            (message.content for message in reversed(task_result.messages) if message.source == "summarizer_agent"),
            None  # Default value if no "summarizer_agent" message is found
        )

        # Display the report and ask for user feedback
        print(report)
        feedback = input("Please provide your feedback on the report (or press Enter to approve it): ")   

        if feedback.strip():
            # If feedback is provided, add it to the messages and loop back to
            # the research team for further refinement
            messages = [
                TextMessage(content=f"The current report draft is: {report}\n", source="user"),
                TextMessage(content=f"User feedback: {feedback}\n", source="user")
            ]
        else:
            break

    # Extract the title from the report (assuming the first line is the title)
    title = report.splitlines()[0] if report else "untitled_report"

    # Remove any markdown or extraneous whitespace from the title
    title = re.sub(r'^[#\s]+', '', title).strip()  # Sanitize the title

    # Determine the file extension based on the selected format
    if args.format == 'pdf':
        extension = '.pdf'
    elif args.format == 'markdown':
        extension = '.md'

    filename = generate_unique_filename(title, extension)

    # Save the report in the selected format
    if args.format == 'pdf':
        pdf = MarkdownPdf(toc_level=1)
        pdf.add_section(Section(report))
        pdf.save(filename)
    else:
        with open(filename, 'w') as file:
            file.write(report)

    print(f"Report saved as {filename}")

