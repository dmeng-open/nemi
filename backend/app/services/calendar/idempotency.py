import hashlib


def make_idempotency_key(plan_id: str, candidate_id: str, action_type: str) -> str:
    raw = f"{plan_id}:{candidate_id}:{action_type}"
    return hashlib.sha256(raw.encode()).hexdigest()
