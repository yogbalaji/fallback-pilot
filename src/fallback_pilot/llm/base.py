from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: str


class Backend(ABC):
    """One interface, several engines.

    Keeping this abstraction from day one is what lets us add the Phi Silica
    NPU path later without touching a single line of the brief-generation code.
    """

    name: str = "backend"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete(self, messages: list[Message], *, max_tokens: int, temperature: float) -> str: ...
