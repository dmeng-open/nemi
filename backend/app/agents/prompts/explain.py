EXPLAIN_SYSTEM = """You write short reasons Nemi picked a plan.

Rules:
- Use only the facts in the payload.
- Write exactly two sentences for each candidate.
- Do not mention scores, rankings, or hidden reasoning.
- Do not add options that are not in the payload.
- Do not change which candidate is which.
- Keep each explanation under 320 characters.
"""


def explain_user_message(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2)
