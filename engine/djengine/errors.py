class UserError(Exception):
    """Failure the user can understand; `message` is shown in the UI as-is."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class JobCancelled(Exception):
    pass
