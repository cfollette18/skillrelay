from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(Strict):
    event_id: str = Field(min_length=1, max_length=100)
    kind: Literal[
        "step",
        "failure",
        "verification",
        "handoff",
        "message",
        "selection",
        "join",
        "termination",
        "skill_use",
    ] = "step"
    action: str = Field(min_length=1, max_length=4000)
    result: str = Field(default="", max_length=4000)
    tool: str = Field(default="", max_length=200)
    success: bool | None = None
    causes: list[str] = Field(default_factory=list, max_length=50)
    recipient: str = Field(default="", max_length=200)
    skill_version: str = Field(default="", max_length=200)


class Step(Strict):
    instruction: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(min_length=1, max_length=30)


class Proposal(Strict):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    applicability: list[str] = Field(min_length=1, max_length=30)
    steps: list[Step] = Field(min_length=1, max_length=50)
    checks: list[str] = Field(min_length=1, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    dependencies: dict[str, str] = Field(default_factory=dict)
    decision: Literal["create", "revise", "merge"] = "create"
    skill_id: str | None = None


class Assessment(Strict):
    """Rubric levels, not an agent-supplied probability."""

    support: int = Field(ge=0, le=4)
    applicability: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    contradictions: int = Field(ge=0, le=4)
    verdict: Literal["pass", "fail", "unknown"]
    rationale: str = Field(min_length=1, max_length=4000)
    evidence: list[str] = Field(min_length=1, max_length=50)
    evaluator_version: str = Field(min_length=1, max_length=100)
