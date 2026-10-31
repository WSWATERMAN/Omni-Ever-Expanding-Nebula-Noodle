from abc import ABC, abstractmethod

class AIProvider(ABC):

    @abstractmethod
    def generate_command(self, prompt: str) -> str:
        pass
