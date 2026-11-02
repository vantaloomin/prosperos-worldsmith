# Vendored from prosperos-dungeon Program/dungeon/errors.py by scripts/sync_format.py. Edit it there, then sync.
"""Copied from prosperos-study server/errors.py at bbcbde4."""


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'request'):
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)


def require(condition: bool, message: str, status: int = 400) -> None:
    if not condition:
        raise DomainError(message, status)
