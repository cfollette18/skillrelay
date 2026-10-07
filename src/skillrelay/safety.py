"""Best-effort screening. This is not a complete secret, PII, or injection detector."""

import re

SECRETS = [
    re.compile(
        r"(?i)\b(?:api[_ -]?key|password|secret|access[_ -]?token)"
        r"[\"\']?\s*[:=]\s*[\"\']?[^\s,;\"\']+"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{15,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"),
]
INJECTION = re.compile(
    r"(?i)(ignore (?:all |any )?(?:previous|prior|system) instructions"
    r"|reveal (?:the |your )?(?:system prompt|api key|secrets)"
    r"|disable (?:all )?(?:safety|security|authorization)"
    r"|bypass (?:the )?(?:permission|authorization|approval))"
)


def redact(text: str) -> str:
    for pattern in SECRETS:
        text = pattern.sub("[REDACTED]", text)
    return text


def clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [clean(x) for x in value]
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"(?i)(password|secret|api[_-]?key|access[_-]?token|authorization)", k)
            else clean(v)
            for k, v in value.items()
        }
    return value


def flags(text: str) -> list[str]:
    return ["possible_instruction_override"] if INJECTION.search(text) else []
