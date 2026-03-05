import os
from dotenv import load_dotenv
from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from core.tools import create_escalation_ticket, log_rework, close_incident

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY not set")


# wrap tools for LLM
@tool
def escalation_tool(event_id: str, reason: str):
    """Create an escalation ticket for a critical incident."""
    return create_escalation_ticket(event_id, reason)


@tool
def rework_tool(event_id: str, note: str):
    """Log a rework action for a non-critical deviation."""
    return log_rework(event_id, note)


@tool
def close_tool(event_id: str):
    """Close the incident when no action is required."""
    return close_incident(event_id)


llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(api_key),
    temperature=0,
)

tools = [escalation_tool, rework_tool, close_tool]

llm_with_tools = llm.bind_tools(tools)


prompt = ChatPromptTemplate.from_template(
    """
You are a manufacturing decision agent.

Event ID: {event_id}
Joint: {joint}
Validation: {validation}
Safety Critical: {safety}

Relevant SOP:
{context}

Decide which tool to call.

If validation is OK and not safety critical → close_tool  
If minor issue → rework_tool  
If safety critical issue → escalation_tool  

Call exactly one tool.
"""
)


def run_decision_agent(event, validation, context):

    print("\n--- AGENT STEP 1 ---")
    print(f"Event ID: {event.event_id}")
    print(f"Joint: {event.joint}")
    print(f"Validation: {validation}")
    print(f"Safety Critical: {event.safety_critical}")

    print("\nRetrieved SOP Context:")
    for c in context:
        print("  -", c)

    formatted_prompt = prompt.format(
        event_id=event.event_id,
        joint=event.joint,
        validation=validation,
        safety=event.safety_critical,
        context="\n".join(context),
    )

    print("\n[AGENT] Sending prompt to model...\n")

    response = llm_with_tools.invoke(formatted_prompt)

    finish_reason = response.response_metadata["finish_reason"]
    print(f"[AGENT] Finish reason → {finish_reason}")

    if response.tool_calls:

        tool_call = response.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        print("\nAgent Decision:")
        print(f"  Tool selected → {tool_name}")
        print(f"  Arguments → {tool_args}")

        print("\nExecuting tool...\n")

        for t in tools:
            if t.name == tool_name:
                result = t.invoke(tool_args)
                return result

    print("\n[AGENT] No tool selected")
    return None
