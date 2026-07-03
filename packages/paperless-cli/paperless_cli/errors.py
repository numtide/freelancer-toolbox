"""Custom exceptions for paperless-cli."""


class PaperlessCliError(Exception):
    """Base exception for paperless-cli."""

    pass


class TagNotFoundError(PaperlessCliError):
    """Raised when one or more tags are not found."""

    def __init__(self, invalid_tags: list[str], available_tags: list[str]) -> None:
        self.invalid_tags = invalid_tags
        self.available_tags = available_tags
        message = f"Tags not found: {', '.join(f"'{tag}'" for tag in invalid_tags)}"
        super().__init__(message)
