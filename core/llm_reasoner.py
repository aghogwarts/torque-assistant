from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pydantic import SecretStr
import os

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY not set")

# initialize model via OpenRouter
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(api_key),
    temperature=0,
)


# reasoning prompt
prompt = ChatPromptTemplate.from_template(
    """
You are a manufacturing quality assistant.

Event Details:
Joint: {joint}
Target Torque: {target}
Actual Torque: {actual}
Tolerance: ±{tolerance}
Validation Result: {validation}
Safety Critical: {safety}

Relevant SOP Context:
{context}

Tasks:
1. Classify severity: LOW, MEDIUM, HIGH
2. Recommend action: NO_ACTION, REWORK, ESCALATE
3. Provide short explanation

Respond in JSON format:
{{
  "severity": "...",
  "action": "...",
  "explanation": "..."
}}
"""
)


def reason_with_llm(event, validation, context):

    formatted_prompt = prompt.format(
        joint=event.joint,
        target=event.target_torque_nm,
        actual=event.actual_torque_nm,
        tolerance=event.tolerance_nm,
        validation=validation,
        safety=event.safety_critical,
        context="\n".join(context),
    )

    print("\n[LLM PROMPT]")
    print(formatted_prompt)

    response = llm.invoke(formatted_prompt)

    print("\n[LLM RAW RESPONSE]")
    print(response.content)

    return response.content
