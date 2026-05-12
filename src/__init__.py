"""
AI Agent Benchmark System
A comprehensive evaluation framework for testing intelligent agents
"""

__version__ = "1.0.0"
__author__ = "Benchmark Team"

try:
    from .models import Task, ExecutionTrace, EvaluationResult
    from .evaluators import CompositeScorer
    from .tasks import TaskRepository
    __all__ = [
        'Task',
        'ExecutionTrace',
        'EvaluationResult',
        'CompositeScorer',
        'TaskRepository',
    ]
except ImportError:
    __all__ = []
