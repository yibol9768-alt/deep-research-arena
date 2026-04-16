#!/usr/bin/env python3
"""
Demo: Complete evaluation pipeline
Shows how tasks are executed and evaluated using CompositeScorer
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.models.task import Task
from src.models.execution import ExecutionTrace, ExecutionStep, EvaluationResult
from src.evaluators.scorer import CompositeScorer
from src.tasks.repository import TaskRepository
import json


def create_demo_execution(task: Task, success: bool = True) -> ExecutionTrace:
    """Create a mock execution trace for demonstration"""
    return ExecutionTrace(
        execution_id=f"exec_{task.task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        task_id=task.task_id,
        execution_timestamp=datetime.now(),
        noise_profile_applied="clean",
        step_count=6,
        total_tokens=2500,
        total_cost=0.0025,
        total_duration_seconds=145.2,
        tools_used=["web_browser", "search"],
        unique_tools_count=2,
        total_errors=0,
        recovered_errors=0,
        error_codes={},
        final_output={
            "status": "SUCCESS",
            "product": {
                "product_id": "JACKET-BLUE-001",
                "name": "Premium Blue Winter Jacket",
                "price": 95.99,
                "color": "blue",
                "rating": 4.5,
                "in_stock": True
            },
            "cart_action": {
                "action": "added",
                "cart_item_count": 1
            }
        } if success else None,
        success=success,
        steps=[
            ExecutionStep(
                step_id=1,
                tool_used="web_browser",
                action="navigate",
                input_data={"url": "http://www.shop.local"},
                output={"status": "success"},
                timestamp=datetime.now(),
                duration_ms=250.5,
                tokens_used=100
            ),
        ]
    )


def run_evaluation_demo():
    """Run complete evaluation demo"""
    print("=" * 80)
    print("🎯 AI Agent Benchmark - Evaluation Pipeline Demo")
    print("=" * 80)

    # Load example tasks
    repo = TaskRepository("data/tasks")
    tasks = repo.list_tasks(domain="ecommerce", status="pilot")

    if not tasks:
        print("❌ No example tasks found. Run: python scripts/generate_example_tasks.py")
        return

    # Initialize scorer
    scorer = CompositeScorer()

    print(f"\n📋 Found {len(tasks)} tasks\n")

    # Evaluate each task
    results = []
    for task in tasks[:1]:  # Demo with first task
        print(f"📝 Evaluating Task: {task.task_id}")
        print(f"   Domain: {task.domain.value}")
        print(f"   Difficulty: {task.difficulty.value}")
        print(f"   Instructions: {task.instruction.natural_language[:60]}...")

        # Create mock executions
        exec_clean = create_demo_execution(task, success=True)
        exec_noisy = create_demo_execution(task, success=True)
        exec_noisy.noise_profile_applied = "realistic"

        # Run evaluation
        evaluation = scorer.compute_overall_score(exec_clean, exec_noisy, task)

        # Store result
        results.append(evaluation)

        # Print results
        print(f"\n   📊 Evaluation Results:")
        print(f"   ├─ Outcome Score:     {evaluation.outcome_score:.4f}")
        print(f"   ├─ Efficiency Score:  {evaluation.efficiency_score:.4f}")
        print(f"   ├─ Robustness Score:  {evaluation.robustness_score:.4f}")
        print(f"   ├─ Complexity Score:  {evaluation.complexity_score:.4f}")
        print(f"   ├─ Composite Score:   {evaluation.composite_score:.4f}")
        print(f"   ├─ Grade:             {evaluation.grade}")
        print(f"   ├─ Pass@1:            {evaluation.pass_1}")
        print(f"   └─ Pass@2:            {evaluation.pass_2}")

        print(f"\n   💰 Score Breakdown:")
        for dim, score in evaluation.breakdown.items():
            print(f"      {dim}: {score:.4f}")

    # Summary statistics
    if results:
        print("\n" + "=" * 80)
        print("📈 Summary Statistics")
        print("=" * 80)

        avg_composite = sum(r.composite_score for r in results) / len(results)
        avg_outcome = sum(r.outcome_score for r in results) / len(results)
        avg_efficiency = sum(r.efficiency_score for r in results) / len(results)
        avg_robustness = sum(r.robustness_score for r in results) / len(results)
        avg_complexity = sum(r.complexity_score for r in results) / len(results)

        pass_1_rate = sum(1 for r in results if r.pass_1) / len(results)
        pass_2_rate = sum(1 for r in results if r.pass_2) / len(results)

        print(f"Average Composite Score:    {avg_composite:.4f}")
        print(f"Average Outcome Score:      {avg_outcome:.4f}")
        print(f"Average Efficiency Score:   {avg_efficiency:.4f}")
        print(f"Average Robustness Score:   {avg_robustness:.4f}")
        print(f"Average Complexity Score:   {avg_complexity:.4f}")
        print(f"Pass@1 Rate:                {pass_1_rate:.1%}")
        print(f"Pass@2 Rate:                {pass_2_rate:.1%}")

    print("\n✅ Demo complete!")


if __name__ == "__main__":
    run_evaluation_demo()
