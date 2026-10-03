def merge_tasks(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for item in [*(left or []), *(right or [])]:
        task_id = str(item["task_id"])
        if task_id not in merged:
            order.append(task_id)
            merged[task_id] = dict(item)
        else:
            merged[task_id] = {**merged[task_id], **item}
    return [merged[task_id] for task_id in order]


def merge_unique(left: list[str] | None, right: list[str] | None) -> list[str]:
    seen: list[str] = []
    for item in [*(left or []), *(right or [])]:
        if item not in seen:
            seen.append(item)
    return seen
