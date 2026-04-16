from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class Difficulty(int, Enum):
    """Task difficulty levels"""
    EASY = 1
    MEDIUM = 2
    HARD = 3


class TaskStatus(str, Enum):
    """Task publication status"""
    DRAFT = "draft"
    PILOT = "pilot"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Domain(str, Enum):
    """Task domains"""
    ECOMMERCE = "ecommerce"
    DEVELOPMENT = "development"
    CMS = "cms"
    FORUM = "forum"
    KNOWLEDGE = "knowledge"


class SuccessCriteriaType(str, Enum):
    """Primary success criteria types"""
    DETERMINISTIC_MATCH = "deterministic_match"
    SCHEMA_VALIDATION = "schema_validation"
    CONTAINS_REQUIRED_FIELDS = "contains_required_fields"
    NUMERICAL_ACCURACY = "numerical_accuracy"


class SecondaryType(str, Enum):
    """Secondary criteria types"""
    FORMAT_CHECK = "format_check"
    PROCESS_QUALITY = "process_quality"
    VISUAL_SIMILARITY = "visual_similarity"
    EFFICIENCY = "efficiency"


class Goal(BaseModel):
    """A single goal within a task"""
    id: str = Field(..., pattern="^goal_[a-z0-9]+$")
    description: str
    constraints: Optional[Dict[str, Any]] = None
    priority: str = Field(default="must", pattern="^(must|should|nice_to_have)$")


class StructuredInstruction(BaseModel):
    """Structured task instruction"""
    goals: List[Goal] = Field(..., min_items=1, max_items=5)
    required_tools: Optional[List[str]] = None
    preconditions: Optional[List[str]] = None


class Instruction(BaseModel):
    """Task instruction with natural language and structure"""
    natural_language: str = Field(..., min_length=50, max_length=500)
    structured: StructuredInstruction


class OutputFormatSpec(BaseModel):
    """Output format specification using JSON Schema"""
    type: str = Field(..., pattern="^(object|array|string|number)$")
    properties: Dict[str, Any]
    required: List[str]
    examples: List[Any] = Field(..., min_items=1)
    counterexamples: Optional[List[Any]] = None


class PrimaryCriteria(BaseModel):
    """Primary success criteria"""
    type: SuccessCriteriaType
    weight: float = Field(..., ge=0, le=1)
    verification_function: Optional[str] = None
    acceptance_criteria: Optional[Dict[str, Any]] = None


class SecondaryCriteria(BaseModel):
    """Secondary success criteria"""
    type: SecondaryType
    weight: float = Field(..., ge=0, le=0.3)
    metric: Optional[str] = None
    target: Optional[Any] = None
    tolerance: Optional[Any] = None


class SuccessCriteria(BaseModel):
    """Complete success criteria specification"""
    primary: PrimaryCriteria
    secondary: Optional[List[SecondaryCriteria]] = None


class NoiseProfile(BaseModel):
    """Noise configuration for a task"""
    name: str = Field(..., pattern="^(clean|realistic|adversarial|degraded)$")
    network_latency_ms: List[int] = Field(..., min_items=2, max_items=2)
    request_timeout_probability: float = Field(..., ge=0, le=1)
    image_load_failure_rate: float = Field(default=0, ge=0, le=1)
    visual_noise_level: float = Field(default=0, ge=0, le=1)
    ocr_error_rate: float = Field(default=0, ge=0, le=1)
    ad_injection_rate: float = Field(default=0, ge=0, le=1)
    content_change_rate: float = Field(default=0, ge=0, le=1)


class EstimatedComplexity(BaseModel):
    """Estimated complexity metrics"""
    expected_steps: int = Field(..., ge=1, le=30)
    expected_tokens: int
    expected_duration_seconds: int
    unique_tools_required: int
    information_integration_level: str = Field(
        ..., pattern="^(single_source|few_sources|many_sources)$"
    )


class Annotations(BaseModel):
    """Annotation metadata"""
    created_by: str
    created_date: datetime
    annotators: List[str]
    inter_annotator_agreement: Optional[float] = Field(None, ge=0, le=1)
    revision: int = 1
    revision_notes: Optional[str] = None
    status: TaskStatus = TaskStatus.DRAFT


class DifficultyEvidence(BaseModel):
    """Evidence supporting difficulty rating"""
    human_baseline_success_rate: Optional[float] = Field(None, ge=0, le=1)
    sota_baseline_success_rate: Optional[float] = Field(None, ge=0, le=1)
    difficulty_score: Optional[float] = Field(None, ge=0, le=1)
    human_target_success_rate: Optional[float] = None


class Dependencies(BaseModel):
    """Task dependencies"""
    prerequisite_tasks: Optional[List[str]] = None
    domain_prerequisites: Optional[Dict[str, Any]] = None
    knowledge_prerequisites: Optional[List[str]] = None


class InitialState(BaseModel):
    """Initial environment state for task execution"""
    start_url: str
    environment: Domain
    logged_in: bool = False
    user_account: Optional[Dict[str, Any]] = None
    environment_seed: Optional[int] = None
    cache_state: str = Field(default="warm", pattern="^(empty|warm|stale)$")


class Task(BaseModel):
    """Complete task specification"""
    task_id: str = Field(..., pattern="^(ec|dev|cms|forum|kb)_[0-9]{4,6}$")
    version: str = Field(default="1.0.0", pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")
    domain: Domain
    difficulty: Difficulty
    instruction: Instruction
    output_format_specification: OutputFormatSpec
    success_criteria: SuccessCriteria
    error_codes: Dict[str, str]
    initial_state: InitialState
    noise_profile: NoiseProfile
    estimated_complexity: EstimatedComplexity
    annotations: Optional[Annotations] = None
    dependencies: Optional[Dependencies] = None
    difficulty_evidence: Optional[DifficultyEvidence] = None

    @field_validator('task_id')
    @classmethod
    def validate_task_id(cls, v):
        """Validate task ID format and domain consistency"""
        parts = v.split('_')
        domain_prefix = {
            'ec': 'ecommerce',
            'dev': 'development',
            'cms': 'cms',
            'forum': 'forum',
            'kb': 'knowledge',
        }
        if parts[0] not in domain_prefix:
            raise ValueError(f"Invalid domain prefix: {parts[0]}")
        return v

    class Config:
        use_enum_values = False
