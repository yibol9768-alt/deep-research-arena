from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class ExecutionStep(BaseModel):
    """A single step in task execution"""
    step_id: int
    tool_used: str
    action: str
    input_data: Dict[str, Any]
    output: Dict[str, Any]
    timestamp: datetime
    duration_ms: float
    tokens_used: int = 0
    error: Optional[str] = None


class SuccessResult(BaseModel):
    """Result when task succeeds"""
    status: str = "SUCCESS"
    final_output: Dict[str, Any]
    step_count: int
    total_tokens: int
    total_duration_seconds: float
    tools_used: List[str]
    error_codes_triggered: List[str] = []
    recovered_errors: int = 0


class ErrorResult(BaseModel):
    """Result when task fails"""
    status: str
    error_code: str
    error_message: str
    step_count: int
    total_tokens: int
    total_duration_seconds: float
    tools_used: List[str]
    final_output: Optional[Dict[str, Any]] = None


class ExecutionTrace(BaseModel):
    """Complete execution record for a task"""
    execution_id: str
    task_id: str
    execution_timestamp: datetime
    noise_profile_applied: str

    # Execution metrics
    step_count: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    total_duration_seconds: float = 0.0

    # Tool tracking
    tools_used: List[str] = Field(default_factory=list)
    unique_tools_count: int = 0

    # Error tracking
    total_errors: int = 0
    recovered_errors: int = 0
    error_codes: Dict[str, int] = Field(default_factory=dict)

    # Output and success
    final_output: Optional[Dict[str, Any]] = None
    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # Execution steps
    steps: List[ExecutionStep] = Field(default_factory=list)

    # Context management
    context_tokens_max: int = 128000
    context_tokens_used: int = 0

    # Robustness data
    is_clean_execution: bool = True  # True if no noise applied


class ExecutionComparison(BaseModel):
    """Comparison between clean and noisy executions"""
    clean_execution: ExecutionTrace
    noisy_execution: ExecutionTrace
    success_degradation: float  # 0-1, where 1 = total failure
    output_similarity: float  # 0-1, where 1 = identical
    is_graceful_degradation: bool  # True if agent detects and recovers from errors


class EvaluationResult(BaseModel):
    """Complete evaluation result for a single execution"""
    execution_id: str
    task_id: str
    evaluation_timestamp: datetime

    # Individual dimension scores (0-1)
    outcome_score: float
    efficiency_score: float
    robustness_score: float
    complexity_score: float

    # Composite score
    composite_score: float  # 0-1
    grade: str  # A+, A, A-, B+, B, B-, C, D, F

    # Score breakdown
    breakdown: Dict[str, float]  # Shows weighted contribution of each dimension

    # Detailed analysis
    primary_criteria_met: bool
    secondary_criteria_scores: Optional[Dict[str, float]] = None

    # Schema validation
    output_schema_valid: bool
    schema_validation_errors: Optional[List[str]] = None

    # Pass@1 and Pass@2 metrics
    pass_1: bool  # Did it succeed on first try?
    pass_2: bool  # Did it eventually succeed within 2 attempts?

    # Metadata
    evaluator_version: str = "1.0.0"


class AggregateResults(BaseModel):
    """Aggregated results across multiple task executions"""
    domain: str
    difficulty_level: int
    task_count: int

    # Success metrics
    success_rate: float  # % tasks completed successfully
    pass_1_rate: float
    pass_2_rate: float

    # Score distributions
    avg_outcome_score: float
    avg_efficiency_score: float
    avg_robustness_score: float
    avg_complexity_score: float
    avg_composite_score: float

    # Grade distribution
    grade_distribution: Dict[str, int]  # {grade: count}

    # Error analysis
    common_error_codes: Dict[str, int]  # {error_code: frequency}

    # Efficiency metrics
    avg_steps_per_task: float
    avg_tokens_per_task: float
    avg_duration_seconds: float

    # Robustness across noise levels
    robustness_by_noise_level: Optional[Dict[str, float]] = None  # {noise_name: avg_score}
