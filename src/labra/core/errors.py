"""Exceptions the domain raises. Routes turn them into HTTP responses in one place."""


class LabraError(Exception):
    """Base class. `public_message` is safe to show to staff; it never carries personal data."""

    status_code = 500
    public_message = "Something went wrong."

    def __init__(self, public_message: str | None = None) -> None:
        if public_message is not None:
            self.public_message = public_message
        super().__init__(self.public_message)


class ConfigError(LabraError):
    """Startup configuration is invalid. The app refuses to start."""


class NotFoundError(LabraError):
    status_code = 404
    public_message = "Not found."


class PermissionDeniedError(LabraError):
    status_code = 403
    public_message = "You don't have permission to do that."


class AuthenticationError(LabraError):
    status_code = 401
    public_message = "Please sign in."


class ValidationFailedError(LabraError):
    status_code = 422
    public_message = "Please correct the highlighted fields."

    def __init__(self, errors: dict[str, str], public_message: str | None = None) -> None:
        self.errors = errors
        super().__init__(public_message)


class ConflictError(LabraError):
    status_code = 409
    public_message = "Someone else changed this record. Reload and try again."
