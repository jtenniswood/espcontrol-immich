class ImmichApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NoMatchingPhotos(ImmichApiError):
    """The source query completed but returned no eligible photos."""
