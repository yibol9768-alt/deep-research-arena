"""
CompositeScorer: Complete evaluation scoring system
Implements 4-dimensional evaluation framework from the specification
"""

from typing import Dict, Tuple, Optional
from src.models.execution import ExecutionTrace, ExecutionComparison, EvaluationResult
from src.models.task import Task


class CompositeScorer:
    """
    Complete scoring pipeline implementing the 4-dimensional evaluation framework:
    - Outcome (40%): Did the agent accomplish the task goals?
    - Efficiency (20%): Did it use resources well (time, tokens, cost)?
    - Robustness (25%): How gracefully does it handle noise?
    - Complexity (15%): Can it handle complex multi-tool workflows?
    """

    # Score-to-grade mapping
    GRADE_THRESHOLDS = {
        0.95: 'A+',
        0.90: 'A',
        0.85: 'A-',
        0.80: 'B+',
        0.75: 'B',
        0.70: 'B-',
        0.60: 'C',
        0.50: 'D',
        0.0: 'F',
    }

    # Dimension weights
    WEIGHTS = {
        'outcome': 0.40,
        'efficiency': 0.20,
        'robustness': 0.25,
        'complexity': 0.15,
    }

    def compute_overall_score(
        self,
        execution_clean: ExecutionTrace,
        execution_noisy: Optional[ExecutionTrace],
        task: Task,
    ) -> EvaluationResult:
        """
        Compute overall A-F grade and all dimension scores.

        Args:
            execution_clean: Clean environment execution
            execution_noisy: Noisy environment execution (if applicable)
            task: Task specification

        Returns:
            EvaluationResult with all scores and breakdown
        """
        # Compute 4 dimension scores (0-1 scale)
        outcome_score = self.score_outcome(execution_clean, task)
        efficiency_score = self.score_efficiency(execution_clean, task)

        if execution_noisy:
            robustness_score = self.score_robustness(execution_clean, execution_noisy, task)
        else:
            robustness_score = 1.0 if execution_clean.success else 0.5

        complexity_score = self.score_complexity(execution_clean, task)

        # Weighted composite score
        composite = (
            self.WEIGHTS['outcome'] * outcome_score +
            self.WEIGHTS['efficiency'] * efficiency_score +
            self.WEIGHTS['robustness'] * robustness_score +
            self.WEIGHTS['complexity'] * complexity_score
        )

        # Convert to grade
        grade = self._score_to_grade(composite)

        # Determine Pass@1 and Pass@2
        pass_1 = execution_clean.success
        pass_2 = pass_1 or (execution_clean.recovered_errors > 0)

        return EvaluationResult(
            execution_id=execution_clean.execution_id,
            task_id=task.task_id,
            evaluation_timestamp=execution_clean.execution_timestamp,
            outcome_score=round(outcome_score, 4),
            efficiency_score=round(efficiency_score, 4),
            robustness_score=round(robustness_score, 4),
            complexity_score=round(complexity_score, 4),
            composite_score=round(composite, 4),
            grade=grade,
            breakdown={
                'outcome': round(outcome_score * self.WEIGHTS['outcome'], 4),
                'efficiency': round(efficiency_score * self.WEIGHTS['efficiency'], 4),
                'robustness': round(robustness_score * self.WEIGHTS['robustness'], 4),
                'complexity': round(complexity_score * self.WEIGHTS['complexity'], 4),
            },
            primary_criteria_met=outcome_score >= 0.70,
            pass_1=pass_1,
            pass_2=pass_2,
            output_schema_valid=self._validate_output_schema(execution_clean, task),
        )

    def score_outcome(self, execution: ExecutionTrace, task: Task) -> float:
        """
        Score primary task completion and result quality.
        Weight in composite: 40%

        Primary criteria: Did the agent accomplish the goal? (70% of outcome)
        Secondary criteria: Process quality, format, efficiency (30% of outcome)
        """
        primary = task.success_criteria.primary
        secondary = task.success_criteria.secondary or []

        # Primary criteria (70% of outcome score)
        if execution.success and execution.final_output:
            # Check if output matches expected schema
            is_valid_schema = self._validate_output_schema(execution, task)
            primary_score = 0.70 if is_valid_schema else 0.35
        else:
            primary_score = 0.0

        # Secondary criteria (30% of outcome score)
        secondary_scores = []
        for criterion in secondary:
            score = self._score_secondary_criterion(criterion, execution, task)
            weighted = score * criterion.weight
            secondary_scores.append(weighted)

        secondary_score = (sum(secondary_scores) / len(secondary_scores) * 0.30
                          if secondary_scores else 0.0)

        return min(primary_score + secondary_score, 1.0)

    def score_efficiency(self, execution: ExecutionTrace, task: Task) -> float:
        """
        Score resource consumption vs quality balance.
        Weight in composite: 20%

        Components:
        - Time efficiency (steps) - 40%
        - Token efficiency - 35%
        - Cost efficiency - 25%
        """
        expected_steps = task.estimated_complexity.expected_steps
        expected_tokens = task.estimated_complexity.expected_tokens

        # Time efficiency (40%)
        actual_steps = execution.step_count
        step_ratio = actual_steps / max(expected_steps, 1)

        if step_ratio <= 1.0:
            time_score = 1.0
        elif step_ratio <= 1.5:
            time_score = 1.0 - (step_ratio - 1.0) * 0.4
        elif step_ratio <= 2.0:
            time_score = 0.8 - (step_ratio - 1.5) * 0.4
        else:
            time_score = max(0.6 - (step_ratio - 2.0) * 0.2, 0.3)

        # Token efficiency (35%)
        actual_tokens = execution.total_tokens
        token_ratio = actual_tokens / max(expected_tokens, 1)

        if token_ratio <= 1.0:
            token_score = 1.0
        elif token_ratio <= 1.5:
            token_score = 1.0 - (token_ratio - 1.0) * 0.3
        else:
            token_score = max(0.85 - (token_ratio - 1.5) * 0.2, 0.5)

        # Cost efficiency (25%)
        # Simple model: cost ~ tokens
        cost_per_step = execution.total_cost / max(execution.step_count, 1)
        expected_cost_per_step = (expected_tokens / max(expected_steps, 1)) * 0.0001

        if cost_per_step <= expected_cost_per_step:
            cost_score = 1.0
        elif cost_per_step <= expected_cost_per_step * 2:
            cost_score = 1.0 - (cost_per_step / expected_cost_per_step - 1.0) * 0.3
        else:
            cost_score = max(0.7, 1.0 - cost_per_step / expected_cost_per_step * 0.4)

        efficiency = (
            0.40 * time_score +
            0.35 * token_score +
            0.25 * cost_score
        )

        return min(efficiency, 1.0)

    def score_robustness(
        self,
        execution_clean: ExecutionTrace,
        execution_noisy: ExecutionTrace,
        task: Task,
    ) -> float:
        """
        Score graceful degradation under noise.
        Weight in composite: 25%

        Components:
        - Success rate degradation - 70%
        - Graceful degradation indicator - 30%
        """
        # Success degradation (70%)
        success_clean = 1.0 if execution_clean.success else 0.0
        success_noisy = 1.0 if execution_noisy.success else 0.0
        degradation = success_clean - success_noisy

        if degradation < 0.1:
            robustness_score = 1.0
        elif degradation < 0.3:
            robustness_score = 0.95 - (degradation - 0.1) * 1.5
        else:
            robustness_score = max(0.55, 1.0 - degradation)

        # Graceful degradation (30%)
        is_graceful = self._check_graceful_degradation(execution_clean, execution_noisy)
        grace_score = 0.8 if is_graceful else 0.3

        robustness = 0.70 * robustness_score + 0.30 * grace_score
        return min(robustness, 1.0)

    def score_complexity(self, execution: ExecutionTrace, task: Task) -> float:
        """
        Score handling of complex multi-step, multi-tool workflows.
        Weight in composite: 15%

        Components:
        - Tool diversity - 35%
        - Context management - 35%
        - Error recovery - 30%
        """
        required_tools = task.instruction.structured.required_tools or []

        # Tool diversity (35%)
        if required_tools:
            unique_tools = len(set(execution.tools_used))
            required_count = len(set(required_tools))
            tool_diversity = min(unique_tools / required_count, 1.0)
        else:
            tool_diversity = 1.0 if execution.unique_tools_count > 0 else 0.5

        # Context management (35%)
        # For long executions, measure how well agent manages context
        if execution.step_count > 10:
            context_efficiency = self._measure_context_efficiency(execution)
        else:
            context_efficiency = 1.0  # Not applicable for short executions

        # Error recovery (30%)
        total_errors = max(execution.total_errors, 1)
        recovery_rate = execution.recovered_errors / total_errors

        complexity = (
            0.35 * tool_diversity +
            0.35 * context_efficiency +
            0.30 * recovery_rate
        )

        return min(complexity, 1.0)

    def _score_secondary_criterion(
        self,
        criterion,
        execution: ExecutionTrace,
        task: Task,
    ) -> float:
        """Score a single secondary criterion"""
        criterion_type = criterion.type.value

        if criterion_type == 'format_check':
            return 1.0 if self._validate_output_schema(execution, task) else 0.0
        elif criterion_type == 'process_quality':
            target = criterion.target or task.estimated_complexity.expected_steps
            tolerance = criterion.tolerance or 4
            diff = abs(execution.step_count - target)
            return max(0.0, 1.0 - (diff / tolerance))
        elif criterion_type == 'efficiency':
            expected = criterion.target or task.estimated_complexity.expected_tokens
            tolerance = criterion.tolerance or 1000
            diff = abs(execution.total_tokens - expected)
            return max(0.0, 1.0 - (diff / tolerance))
        elif criterion_type == 'visual_similarity':
            # Placeholder for visual matching
            return 0.8 if execution.success else 0.3

        return 0.5  # Default if unknown

    def _validate_output_schema(self, execution: ExecutionTrace, task: Task) -> bool:
        """Check if execution output matches expected JSON schema"""
        if not execution.final_output or not execution.success:
            return False

        # Basic schema validation: check required fields exist
        required = task.output_format_specification.required
        output_keys = set(execution.final_output.keys())

        return all(field in output_keys for field in required)

    def _check_graceful_degradation(
        self,
        execution_clean: ExecutionTrace,
        execution_noisy: ExecutionTrace,
    ) -> bool:
        """
        Check if agent gracefully degrades under noise rather than crashing.
        True if: agent detects errors and recovers, or provides partial output
        """
        # If noisy execution recovered errors, that's graceful
        if execution_noisy.recovered_errors > 0:
            return True

        # If both succeeded, that's very graceful
        if execution_clean.success and execution_noisy.success:
            return True

        # If noisy provided any output despite failure, that's graceful
        if execution_noisy.final_output is not None and not execution_noisy.success:
            return True

        return False

    def _measure_context_efficiency(self, execution: ExecutionTrace) -> float:
        """
        For executions with >10 steps, measure context window efficiency.
        Returns 0-1 score based on how efficiently agent manages long contexts.
        """
        if execution.context_tokens_used == 0:
            return 1.0

        # Ratio of context actually used vs max available
        context_ratio = execution.context_tokens_used / execution.context_tokens_max

        # Penalize if using >80% of context
        if context_ratio < 0.8:
            return 1.0
        elif context_ratio < 0.95:
            return 0.9
        else:
            return 0.7

    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score (0-1) to letter grade"""
        for threshold in sorted(self.GRADE_THRESHOLDS.keys(), reverse=True):
            if score >= threshold:
                return self.GRADE_THRESHOLDS[threshold]
        return 'F'
