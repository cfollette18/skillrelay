"""Optional observability and behavioral-evaluation extension interfaces."""

from typing import Protocol


class TraceExporter(Protocol):
    def export(self, snapshot: dict) -> int: ...


class BehavioralEvaluator(Protocol):
    """Reserved extension. No built-in behavior benchmark or performance claim."""

    def evaluate(self, skill: dict, held_out_cases: list[dict]) -> dict: ...


class OpenTelemetryExporter:
    """Export identifiers and outcomes only to a caller-configured OTel tracer.

    Configure the OTel SDK/exporter in your host application. No backend is bundled.
    Tool output and prompts are deliberately omitted from exported attributes.
    """

    def __init__(self, tracer):
        self.tracer = tracer

    def export(self, snapshot: dict) -> int:
        count = 0
        for run in snapshot["run"]:
            with self.tracer.start_as_current_span("skillrelay.run") as span:
                for key in ("id", "task", "agent", "workflow_id", "status", "outcome"):
                    span.set_attribute(f"skillrelay.{key}", run[key])
                for event in snapshot["event"]:
                    if event["run_id"] == run["id"]:
                        span.add_event(
                            event["kind"],
                            {"skillrelay.event_id": event["id"], "skillrelay.tool": event["tool"]},
                        )
                count += 1
        return count
