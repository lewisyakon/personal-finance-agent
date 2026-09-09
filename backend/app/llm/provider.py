from dataclasses import dataclass


@dataclass(frozen=True)
class ModelHealth:
    provider: str
    model: str
    available: bool
    message: str


class MockModelProvider:
    """Deterministic provider for stage 0 and automated tests."""

    provider = "mock"

    def __init__(self, model: str = "mock-model") -> None:
        self.model = model

    def health(self) -> ModelHealth:
        return ModelHealth(
            provider=self.provider,
            model=self.model,
            available=True,
            message="mock provider ready",
        )

    def complete(self, *_args, **_kwargs) -> dict:
        return {"content": "", "tool_calls": [], "provider": self.provider, "model": self.model}

