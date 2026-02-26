from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

load_dotenv()


# initialize model via OpenRouter
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
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

    response = llm.invoke(
        prompt.format(
            joint=event.joint,
            target=event.target_torque_nm,
            actual=event.actual_torque_nm,
            tolerance=event.tolerance_nm,
            validation=validation,
            safety=event.safety_critical,
            context="\n".join(context),
        )
    )

    return response.content
