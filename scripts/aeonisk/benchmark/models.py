"""
Pydantic models for the Aeonisk YAGS benchmarking system.

This module defines the core data models used throughout the benchmarking framework.
"""

from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class TaskDomain(BaseModel):
    """Model representing a task domain."""
    core: str
    subdomain: str


class BenchmarkTask(BaseModel):
    """Model representing a benchmark task from the dataset."""
    task_id: str
    domain: TaskDomain
    scenario: str
    environment: str
    stakes: str
    characters: List[Dict[str, Any]]
    goal: str
    expected_fields: List[str]
    gold_answer: Dict[str, Any]
    aeonisk_extra_data: Optional[Dict[str, Any]] = None
    
    # Metadata for benchmarking
    difficulty_level: Optional[str] = None
    task_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ModelResponse(BaseModel):
    """Model representing a model's response to a benchmark task."""
    task_id: str
    model_name: str
    provider: str
    response_time: float
    token_count: Optional[int] = None
    raw_response: str
    parsed_response: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Response fields extracted from model output
    attribute_used: Optional[str] = None
    skill_used: Optional[str] = None
    roll_formula: Optional[str] = None
    difficulty_guess: Optional[int] = None
    outcome_explanation: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    
    # Error handling
    error: Optional[str] = None
    successful_parse: bool = True


class EvaluationDimension(str, Enum):
    """Enumeration of evaluation dimensions."""
    MECHANICAL_ACCURACY = "mechanical_accuracy"
    NARRATIVE_QUALITY = "narrative_quality"
    RULES_ADHERENCE = "rules_adherence"
    CONSISTENCY = "consistency"
    CREATIVITY = "creativity"
    DIFFICULTY_APPROPRIATE = "difficulty_appropriate"
    OVERALL_QUALITY = "overall_quality"


class EvaluationResult(BaseModel):
    """Model representing evaluation results for a single task."""
    task_id: str
    model_name: str
    scores: Dict[EvaluationDimension, float] = Field(default_factory=dict)
    comments: Dict[EvaluationDimension, str] = Field(default_factory=dict)
    overall_score: float
    gold_standard_similarity: float
    judge_rationale: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Specific evaluation metrics
    attribute_correct: bool = False
    skill_correct: bool = False
    difficulty_within_range: bool = False
    formula_correct: bool = False
    outcomes_plausible: bool = False


class BenchmarkResult(BaseModel):
    """Model representing complete benchmark results for a model."""
    model_name: str
    provider: str
    benchmark_config: Dict[str, Any]
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    average_response_time: float
    total_tokens: Optional[int] = None
    
    # Aggregate scores
    overall_score: float
    dimension_scores: Dict[EvaluationDimension, float] = Field(default_factory=dict)
    
    # Task-level results
    task_results: List[EvaluationResult] = Field(default_factory=list)
    
    # Performance by domain
    domain_performance: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    
    # Metadata
    start_time: datetime
    end_time: datetime
    duration: float
    
    @property
    def success_rate(self) -> float:
        """Calculate the success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks


class ComparisonReport(BaseModel):
    """Model representing comparison results between multiple models."""
    benchmark_name: str
    models: List[str]
    dataset_version: str
    total_tasks: int
    
    # Aggregate comparisons
    model_rankings: Dict[str, int] = Field(default_factory=dict)
    dimension_rankings: Dict[EvaluationDimension, Dict[str, int]] = Field(default_factory=dict)
    
    # Statistical analyses
    statistical_significance: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    effect_sizes: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    
    # Domain-specific comparisons
    domain_comparisons: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    
    # Individual model results
    results: List[BenchmarkResult] = Field(default_factory=list)
    
    # Report metadata
    generated_at: datetime = Field(default_factory=datetime.now)
    analysis_notes: Optional[str] = None


class BenchmarkConfig(BaseModel):
    """Model representing benchmark configuration."""
    name: str
    description: str
    dataset_path: str
    models: List[Dict[str, Any]]
    
    # Evaluation settings
    use_ai_judge: bool = True
    judge_model: str = "gpt-4"
    evaluation_dimensions: List[EvaluationDimension] = Field(
        default_factory=lambda: list(EvaluationDimension)
    )
    
    # Sampling settings
    sample_size: Optional[int] = None
    random_seed: Optional[int] = None
    filter_domains: Optional[List[str]] = None
    filter_difficulty: Optional[List[str]] = None
    
    # Performance settings
    max_concurrent_requests: int = 5
    timeout_seconds: int = 30
    retry_attempts: int = 3
    
    # Output settings
    output_dir: str = "benchmark_results"
    save_raw_responses: bool = True
    generate_whitepaper: bool = True
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0.0"


class TaskStatistics(BaseModel):
    """Model representing statistics for a specific task."""
    task_id: str
    domain: str
    subdomain: str
    
    # Response statistics
    model_responses: int
    successful_responses: int
    failed_responses: int
    
    # Score statistics
    mean_score: float
    median_score: float
    std_score: float
    min_score: float
    max_score: float
    
    # Specific metrics
    attribute_accuracy: float
    skill_accuracy: float
    difficulty_accuracy: float
    formula_accuracy: float
    
    # Model performance variance
    score_variance: float
    inter_model_agreement: float
    
    # Difficulty indicators
    estimated_difficulty: float
    human_difficulty_rating: Optional[float] = None
    
    # Qualitative analysis
    common_errors: List[str] = Field(default_factory=list)
    best_responses: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class DomainAnalysis(BaseModel):
    """Model representing analysis of a specific domain."""
    domain: str
    subdomain: str
    
    # Task distribution
    total_tasks: int
    difficulty_distribution: Dict[str, int] = Field(default_factory=dict)
    
    # Performance metrics
    average_scores: Dict[str, float] = Field(default_factory=dict)
    model_rankings: Dict[str, int] = Field(default_factory=dict)
    
    # Specific analysis
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    
    # Statistical tests
    anova_results: Optional[Dict[str, float]] = None
    post_hoc_tests: Optional[Dict[str, Dict[str, float]]] = None
    
    # Metadata
    analysis_date: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None