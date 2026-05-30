class TokenError(NameError):
    """Исключение при отсутствии токенов."""

    def __str__(self) -> str:
        """Сообщение исключения."""
        return 'Отсутствует токен(ы)'
