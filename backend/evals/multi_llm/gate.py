"""Opt-in gate for the live golden set.

Ordinary pytest does not set these variables and must not call OpenAI.
"""

import os

NOT_RUN_REASON = (
    "Live multi-LLM golden eval was not run. "
    "It runs only when OPENAI_API_KEY is non-empty and NEMI_RUN_MODEL_EVALS=1. "
    "This skip is not a pass or fail score."
)

PORT_NOT_RUN_REASON = (
    "Live multi-LLM golden eval was not run. "
    "The structured-output port is not available, so the baseline was not compared "
    "with a live model. This skip is not a pass or fail score."
)


def model_evals_enabled() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "")
    flag = os.environ.get("NEMI_RUN_MODEL_EVALS", "")
    return bool(key.strip()) and flag == "1"
