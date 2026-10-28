from dataclasses import dataclass


@dataclass(frozen=True)
class Pass:
    role: str
    model: str
    authoritative: bool


def plan_passes(paths: list[str], untrusted_text: str) -> list[Pass]:
    del paths, untrusted_text  # repository content is data, never policy
    return [Pass("primary", "gemini-rotativo", True),
            Pass("adversarial", "OpenRoute-Free", True),
            Pass("editor", "Ollama", False)]
