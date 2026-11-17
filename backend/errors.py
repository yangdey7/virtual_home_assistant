class CommandError(Exception):
    """An actionable error that is safe to display to the user."""

    def __init__(self, message, code="invalid_command", status=422):
        super().__init__(message)
        self.code = code
        self.status = status

