from dataclasses import dataclass


@dataclass(frozen=True)
class Pass:
    role: str
    model: str
    authoritative: bool


_RISK_TERMS = ("auth", "webhook", "secret", "payment", "sql", "migration", "queue", "lock", "api", "schema")


def plan_passes(paths: list[str], untrusted_text: str) -> list[Pass]:
    del untrusted_text  # content is data, never policy
    passes = [Pass("primary", "gemini-rotativo", True),
              Pass("adversarial", "OpenCode-Free", True)]
    if any(term in path.lower() for path in paths for term in _RISK_TERMS):
        passes.append(Pass("security-specialist", "OpenRoute-Free", True))
    passes.append(Pass("editor", "Ollama", False))
    return passes
