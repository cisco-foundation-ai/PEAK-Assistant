#!/usr/bin/env python3

import os
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from markdown_pdf import MarkdownPdf, Section

def find_dotenv_file():
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / '.env'
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found

# Set up argument parser
parser = argparse.ArgumentParser(description='Generate a threat hunting report for a specific technique')
parser.add_argument('-t', '--technique', required=True, help='The cybersecurity technique to research')
parser.add_argument('-e', '--environment', help='Path to specific .env file to use')
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

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  
)

# The original prompt template
prompt_template = """
Please research the following cybersecurity threat actor behavior or technique 
compile a summary of everything a threat hunter needs to know to identify this 
activity. 

<technique>%TECHNIQUE%</technique>

Format the output as a simple Markdown report. Be sure to include the sections:
- A brief descriptive title. This should just be the name of the technique, if 
  there is one in common use. Otherwise, make up something short.
- The relevant MITRE ATT&CK ids & URLs. If there are multiple ATT&CK ids, list them
  in the order they are most commonly used in the attack lifecycle. 
- A brief description of why this technique is used. Call this section "Overview".
- A detailed description of how the technqique is performed, including example 
  commands or code, as appropriate. Explain things in enough detail that a technically
  knowledgable threat hunter or red teamer could replicate the process step-by-step. 
  Include details about what each step does and why. Call this section "Technique Details".
- A description of how to detect this technique. Include published detection
  rules if you found any, giving priority to Splunk/SPL rules. Call this section 
  "Detection".
- A detailed description of the typical datasets that would be required to hunt for this 
  activity. Include details about what each dataset contains and how it can be used to
  identify this activity. It's OK if there are more than one datasets that could be used, 
  or if multiple datasets must be used in conjuction with each (if this is the case, be 
  sure to mention it). When feasible, include sample log entries and details about the fields 
  and what they mean, especially the fields that are most important for identifying this 
  activity. The sample log entries are important, so please try hard to find good ones to
  include. For every dataset you mention, include a link to a page that documents that
  dataset and it's fields, if you can find one. Prefer pages from official documentation 
  for that data, but if they are not available, select the most comprehensive and 
  understandable page you can find. Call this section "Typical Datasets".
- A brief list of published threat hunt methodologies for this technique. Call this 
  section "Published Hunts".
- A brief list of tools threat actors commonly use to perform this technique. Call 
  this section "Commonly-Used Tools".
- A list of references to the URLs you found most helpful, 
  including a sentence about why each was included on the list. If a MITRE ATT&CK entry
  is included, be sure to list it first. If a MITRE CAPEC entry is included, list it second.
  For all entries in this section, YOU MUST INCLUDE A URL. If you do not have a URL, do not 
  include the entry. Include at least 5 entries if feasible. Call this section "References".
- A section listing any other information that would be helpful to a threat hunter 
  but that did not fall under any other section. Call this section "Other Information".

Always include each of these sections, even if the section is blank. Just write 
"N/A" if you don't have anything to put in that section.

Do not include any type of conclusion or summary at the end of the report. Just 
end one the final section.
"""

# Replace the placeholder with the actual technique from command line
prompt = prompt_template.replace('%TECHNIQUE%', args.technique)

response = client.responses.create(
    model=os.getenv("OPENAI_MODEL"), 
    tools=[ {
        "type": "web_search_preview",
        "search_context_size": os.getenv("OPENAI_SEARCH_CONTEXT_SIZE")
    } ],  
    tool_choice={
        "type": "web_search_preview"
    },
    input=prompt
)

print(response)
print("\n*************\n")
print(response.output_text)

pdf = MarkdownPdf(toc_level=2, optimize=True)
pdf.add_section(Section(response.output_text))
pdf.save("huntreport.pdf")
