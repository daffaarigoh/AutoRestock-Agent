import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TraceSpan(BaseModel):
    span_id: str
    node_name: str
    model_name: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    input_payload: Optional[Dict[str, Any]] = None
    output_payload: Optional[Dict[str, Any]] = None
    status: str = "RUNNING" # RUNNING | SUCCESS | FAILED
    error_message: Optional[str] = None


class AgentTrace(BaseModel):
    trace_id: str
    workflow_name: str = "Autonomous-AutoRestock-Cycle"
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    total_duration_ms: float = 0.0
    spans: List[TraceSpan] = []
    total_tokens_estimated: int = 0
    compliance_verdict: Optional[str] = None


class ObservabilityTracer:
    """
    In-memory and structured LLM tracer for monitoring agent execution latency,
    token usage, and compliance verdicts (compatible with Langfuse / OpenTelemetry specs).
    """

    def __init__(self):
        self._traces: List[AgentTrace] = []
        self._active_trace: Optional[AgentTrace] = None

    def start_trace(self, trace_id: str, workflow_name: str = "Autonomous-AutoRestock-Cycle") -> AgentTrace:
        trace = AgentTrace(trace_id=trace_id, workflow_name=workflow_name)
        self._active_trace = trace
        self._traces.append(trace)
        return trace

    def start_span(self, span_id: str, node_name: str, model_name: Optional[str] = None, input_payload: Optional[Dict] = None) -> TraceSpan:
        span = TraceSpan(
            span_id=span_id,
            node_name=node_name,
            model_name=model_name,
            started_at=datetime.now().isoformat(),
            input_payload=input_payload or {},
        )
        if self._active_trace:
            self._active_trace.spans.append(span)
        return span

    def end_span(self, span: TraceSpan, output_payload: Optional[Dict] = None, status: str = "SUCCESS", error: Optional[str] = None, tokens: int = 0):
        span.completed_at = datetime.now().isoformat()
        span.output_payload = output_payload or {}
        span.status = status
        span.error_message = error
        
        # Calculate duration
        start_time = datetime.fromisoformat(span.started_at)
        end_time = datetime.fromisoformat(span.completed_at)
        span.duration_ms = (end_time - start_time).total_seconds() * 1000.0

        if self._active_trace:
            self._active_trace.total_tokens_estimated += tokens

    def end_trace(self, trace: Optional[AgentTrace] = None, verdict: Optional[str] = None) -> AgentTrace:
        active = trace or self._active_trace
        if active:
            active.completed_at = datetime.now().isoformat()
            active.compliance_verdict = verdict
            start_time = datetime.fromisoformat(active.started_at)
            end_time = datetime.fromisoformat(active.completed_at)
            active.total_duration_ms = (end_time - start_time).total_seconds() * 1000.0
        return active

    def get_recent_traces(self, limit: int = 10) -> List[AgentTrace]:
        return self._traces[-limit:]


tracer = ObservabilityTracer()
