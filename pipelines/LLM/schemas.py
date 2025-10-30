from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# Controlled set of bottleneck categories
BottleneckType = Literal[
    "algorithmic_inefficiency",
    "caching_memoization",
    "object_churn",
    "vectorization",
    "io_batching",
    "parallelization",
    "inefficient_data_structure",
    "repeated_regex_compile",
    "other",
]


class FunctionCodeRequest(BaseModel):
    """
    Structured way for the LLM to request code for a function.
    """

    type: Literal["function_source"] = "function_source"
    fqn: str
    reason: str


class BottleneckHypothesis(BaseModel):
    """
    A metrics-first hypothesis before seeing code (optional).
    """

    fqn: str
    bottleneck_type: BottleneckType
    confidence: float = Field(ge=0.0, le=1.0)
    issue_description: str
    # Optional at triage; numeric for easier later analysis (0..100)
    estimated_impact: Optional[float]


class TriageReply(BaseModel):
    """
    Triage response schema (metrics-only stage).
    """

    status: Literal["continue", "done"]
    code_requests: List[FunctionCodeRequest] = []
    hypotheses: List[BottleneckHypothesis] = []


class BottleneckFinding(BaseModel):
    """
    Final bottleneck finding after inspecting code (or confident from metrics).
    """

    fqn: str
    bottleneck_type: BottleneckType
    confidence: float = Field(ge=0.0, le=1.0)
    issue_description: str
    suggested_fix_summary: str
    # Required at finding time; numeric (0..100)
    estimated_impact: float


class InspectionReply(BaseModel):
    """
    Inspection response schema (after providing requested code).
    """

    status: Literal["continue", "done"]
    code_requests: List[FunctionCodeRequest] = []
    bottlenecks: List[BottleneckFinding] = []
