"""Django MAILERS adapter for the application EmailGateway port."""

from collections.abc import Callable

from django.core.mail import send_mail


class DjangoEmailGateway:
    def __init__(self, *, sender_func: Callable = send_mail):
        self.sender_func = sender_func

    def send(self, *, recipient: str, subject: str, body: str, sender: str) -> int:
        return self.sender_func(
            subject, body, sender, [recipient], using="default"
        )
