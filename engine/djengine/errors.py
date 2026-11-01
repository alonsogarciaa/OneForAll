class UserError(Exception):
    """Failure the user can understand; `message` is shown in the UI as-is."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class JobCancelled(Exception):
    pass


ERROR_MESSAGES: dict[str, str] = {
    "unavailable": "Este vídeo ya no está disponible",
    "blocked": "YouTube bloquea este vídeo (edad/región)",
    "offline": "Sin conexión",
    "extractor_outdated": "YouTube ha cambiado; actualiza yt-dlp",
    "disk": "No se puede escribir en la carpeta de destino",
}


def user_error(code: str) -> UserError:
    return UserError(code, ERROR_MESSAGES[code])
