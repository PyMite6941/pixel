from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    def auto_triggers(self) -> list[str]:
        return []

    @property
    def requires_subprocess(self) -> bool:
        return False

    @abstractmethod
    def execute(self, **params: Any) -> Any:
        ...
