import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def safe_error_text(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    redacted = text.replace("sk-", "sk-REDACTED")
    return redacted[:300]
