"""Skip this package unless the live golden eval was explicitly opted into."""

import pytest
from evals.multi_llm.gate import NOT_RUN_REASON, model_evals_enabled


def pytest_collection_modifyitems(config, items) -> None:
    del config
    if model_evals_enabled():
        return
    skip = pytest.mark.skip(reason=NOT_RUN_REASON)
    for item in items:
        path = str(getattr(item, "path", "")).replace("\\", "/")
        if "/multi_llm/" not in path:
            continue
        item.add_marker(skip)
