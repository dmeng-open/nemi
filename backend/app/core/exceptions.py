class AppError(Exception):
    code = "error"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ApprovalRequired(AppError):
    code = "approval_required"
    status_code = 409

    def __init__(
        self,
        message: str = "Approve the plan before it is added to your schedule.",
    ) -> None:
        super().__init__(message)


class ScheduleConflictError(AppError):
    code = "schedule_conflict"
    status_code = 409

    def __init__(
        self,
        message: str = "Your selected option conflicts with another calendar event.",
    ) -> None:
        super().__init__(message)


class PlanNotFound(AppError):
    code = "plan_not_found"
    status_code = 404

    def __init__(self, message: str = "That plan could not be found.") -> None:
        super().__init__(message)


class PlanStateError(AppError):
    code = "plan_not_ready"
    status_code = 409

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidSelection(AppError):
    code = "invalid_selection"
    status_code = 400

    def __init__(self, message: str = "Choose one of the recommended options.") -> None:
        super().__init__(message)


class LLMTimeoutError(AppError):
    code = "openai_timeout"
    status_code = 504

    def __init__(self, message: str = "OpenAI request timed out.") -> None:
        super().__init__(message)


class LLMValidationError(AppError):
    code = "date_unclear"
    status_code = 422

    def __init__(self, message: str = "Could not understand the requested date.") -> None:
        super().__init__(message)


class ProviderError(AppError):
    code = "provider_failed"
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code=code or "provider_failed", status_code=status_code)
        self.retryable = retryable


class ProviderNotConfigured(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            retryable=False,
            code="provider_not_configured",
            status_code=409,
        )


class CalendarNotConnected(Exception):
    """Google Calendar cannot be written. The plan stays awaiting approval."""


class CalendarReadFailed(Exception):
    """Busy time could not be read, so the event was not created."""


class CalendarCreateUnconfirmed(Exception):
    """The provider did not confirm that the event exists."""
