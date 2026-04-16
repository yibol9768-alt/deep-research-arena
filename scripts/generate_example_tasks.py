#!/usr/bin/env python3
"""
Generate example tasks for each domain.
These serve as templates and starting points for task creation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.models.task import (
    Task, Difficulty, Domain, Instruction, StructuredInstruction, Goal,
    OutputFormatSpec, SuccessCriteria, PrimaryCriteria, SecondaryCriteria,
    NoiseProfile, EstimatedComplexity, Annotations, TaskStatus,
    InitialState, SuccessCriteriaType, SecondaryType,
)
from src.tasks.repository import TaskRepository


def create_ecommerce_example():
    """E-commerce example: Product search and purchase"""
    return Task(
        task_id="ec_0001",
        version="1.0.0",
        domain=Domain.ECOMMERCE,
        difficulty=Difficulty.MEDIUM,
        instruction=Instruction(
            natural_language=(
                "Find a blue winter jacket priced between $50-$150 with at least "
                "4 stars rating. Add it to your shopping cart. Use the search "
                "functionality and filters to complete this task."
            ),
            structured=StructuredInstruction(
                goals=[
                    Goal(
                        id="goal_1",
                        description="Find a blue winter jacket",
                        constraints={
                            "color": "blue",
                            "product_type": "winter jacket",
                            "price_range": [50, 150],
                            "min_rating": 4.0
                        },
                        priority="must"
                    ),
                    Goal(
                        id="goal_2",
                        description="Add the product to cart",
                        priority="must"
                    )
                ],
                required_tools=["web_browser", "search"],
                preconditions=[
                    "Connected to e-commerce website",
                    "Shopping cart is accessible"
                ]
            )
        ),
        output_format_specification=OutputFormatSpec(
            type="object",
            properties={
                "status": {
                    "type": "string",
                    "enum": ["SUCCESS", "ELEMENT_NOT_FOUND", "FORMAT_MISMATCH", "TIMEOUT_ERROR"]
                },
                "product": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "name": {"type": "string"},
                        "price": {"type": "number"},
                        "color": {"type": "string"},
                        "rating": {"type": "number", "minimum": 0, "maximum": 5},
                        "in_stock": {"type": "boolean"}
                    }
                },
                "cart_action": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["added", "updated", "failed"]},
                        "cart_item_count": {"type": "integer"}
                    }
                }
            },
            required=["status", "product"],
            examples=[
                {
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
                }
            ]
        ),
        success_criteria=SuccessCriteria(
            primary=PrimaryCriteria(
                type=SuccessCriteriaType.DETERMINISTIC_MATCH,
                weight=0.70,
                verification_function="verify_product_and_cart",
                acceptance_criteria={
                    "correct_product": "Product must be blue, winter jacket, within price and rating range",
                    "added_to_cart": "Product must be in final cart",
                    "json_valid": "Output must be valid JSON matching schema"
                }
            ),
            secondary=[
                SecondaryCriteria(
                    type=SecondaryType.PROCESS_QUALITY,
                    weight=0.15,
                    metric="steps_taken",
                    target=6,
                    tolerance=4
                ),
                SecondaryCriteria(
                    type=SecondaryType.FORMAT_CHECK,
                    weight=0.10,
                    metric="json_schema_valid"
                ),
                SecondaryCriteria(
                    type=SecondaryType.EFFICIENCY,
                    weight=0.05,
                    metric="token_efficiency",
                    target=2000,
                    tolerance=1000
                )
            ]
        ),
        error_codes={
            "SUCCESS": "Task completed successfully",
            "PRODUCT_NOT_FOUND": "Product matching criteria not found",
            "FILTER_NOT_AVAILABLE": "Search filters unavailable",
            "ADD_TO_CART_FAILED": "Could not add product to cart",
            "TIMEOUT_ERROR": "Request timeout or page load failure"
        },
        initial_state=InitialState(
            start_url="http://www.shop.local",
            environment=Domain.ECOMMERCE,
            logged_in=False,
            cache_state="warm",
            environment_seed=42
        ),
        noise_profile=NoiseProfile(
            name="realistic",
            network_latency_ms=[100, 300],
            request_timeout_probability=0.02,
            image_load_failure_rate=0.05,
            visual_noise_level=0.1,
            ad_injection_rate=0.2,
            content_change_rate=0.05
        ),
        estimated_complexity=EstimatedComplexity(
            expected_steps=6,
            expected_tokens=3000,
            expected_duration_seconds=180,
            unique_tools_required=2,
            information_integration_level="few_sources"
        ),
        annotations=Annotations(
            created_by="system",
            created_date=datetime.now(),
            annotators=["annotator_1", "annotator_2", "annotator_3"],
            inter_annotator_agreement=0.85,
            revision=1,
            status=TaskStatus.PILOT
        )
    )


def create_development_example():
    """Development domain: Code review and bug fix"""
    return Task(
        task_id="dev_0001",
        version="1.0.0",
        domain=Domain.DEVELOPMENT,
        difficulty=Difficulty.HARD,
        instruction=Instruction(
            natural_language=(
                "Review the failing test in the repository. Identify the bug in the "
                "implementation that causes the test to fail. Create a fix and verify "
                "the test passes."
            ),
            structured=StructuredInstruction(
                goals=[
                    Goal(
                        id="goal_1",
                        description="Understand the failing test",
                        priority="must"
                    ),
                    Goal(
                        id="goal_2",
                        description="Identify root cause of failure",
                        priority="must"
                    ),
                    Goal(
                        id="goal_3",
                        description="Implement and verify fix",
                        priority="must"
                    )
                ],
                required_tools=["code_executor", "file_system", "search"],
            )
        ),
        output_format_specification=OutputFormatSpec(
            type="object",
            properties={
                "status": {"type": "string"},
                "bug_description": {"type": "string"},
                "root_cause": {"type": "string"},
                "fix_applied": {"type": "string"},
                "test_passed": {"type": "boolean"},
                "files_modified": {"type": "array", "items": {"type": "string"}}
            },
            required=["status", "bug_description", "test_passed"],
            examples=[
                {
                    "status": "SUCCESS",
                    "bug_description": "Off-by-one error in loop iteration",
                    "root_cause": "Loop condition used < instead of <=",
                    "fix_applied": "Changed line 42 from 'i < n' to 'i <= n'",
                    "test_passed": True,
                    "files_modified": ["src/algorithm.py"]
                }
            ]
        ),
        success_criteria=SuccessCriteria(
            primary=PrimaryCriteria(
                type=SuccessCriteriaType.DETERMINISTIC_MATCH,
                weight=0.75,
                verification_function="verify_test_passes",
            ),
            secondary=[
                SecondaryCriteria(
                    type=SecondaryType.PROCESS_QUALITY,
                    weight=0.15,
                    metric="bug_correctly_identified"
                ),
                SecondaryCriteria(
                    type=SecondaryType.EFFICIENCY,
                    weight=0.10,
                    metric="minimal_changes"
                )
            ]
        ),
        error_codes={
            "SUCCESS": "Test passing",
            "TEST_STILL_FAILING": "Test still fails after fix",
            "CANNOT_RUN_TEST": "Test execution failed",
            "WRONG_FIX": "Fix applied but incorrect",
            "TIMEOUT_ERROR": "Code execution timeout"
        },
        initial_state=InitialState(
            start_url="http://git.local/repo",
            environment=Domain.DEVELOPMENT,
            logged_in=True,
            environment_seed=123
        ),
        noise_profile=NoiseProfile(
            name="realistic",
            network_latency_ms=[50, 200],
            request_timeout_probability=0.01
        ),
        estimated_complexity=EstimatedComplexity(
            expected_steps=8,
            expected_tokens=4000,
            expected_duration_seconds=300,
            unique_tools_required=3,
            information_integration_level="few_sources"
        ),
        annotations=Annotations(
            created_by="system",
            created_date=datetime.now(),
            annotators=["dev1", "dev2"],
            inter_annotator_agreement=0.82,
            revision=1,
            status=TaskStatus.PILOT
        )
    )


def create_cms_example():
    """CMS domain: Content management"""
    return Task(
        task_id="cms_0001",
        version="1.0.0",
        domain=Domain.CMS,
        difficulty=Difficulty.EASY,
        instruction=Instruction(
            natural_language=(
                "Create a new blog post with the title 'Introduction to AI Safety', "
                "category 'Technology', and publish it."
            ),
            structured=StructuredInstruction(
                goals=[
                    Goal(
                        id="goal_1",
                        description="Navigate to create new post",
                        priority="must"
                    ),
                    Goal(
                        id="goal_2",
                        description="Fill in post details",
                        priority="must"
                    ),
                    Goal(
                        id="goal_3",
                        description="Publish the post",
                        priority="must"
                    )
                ],
                required_tools=["web_browser"],
            )
        ),
        output_format_specification=OutputFormatSpec(
            type="object",
            properties={
                "status": {"type": "string"},
                "post_id": {"type": "string"},
                "title": {"type": "string"},
                "category": {"type": "string"},
                "published": {"type": "boolean"},
                "publish_url": {"type": "string"}
            },
            required=["status", "post_id", "published"],
            examples=[
                {
                    "status": "SUCCESS",
                    "post_id": "post_12345",
                    "title": "Introduction to AI Safety",
                    "category": "Technology",
                    "published": True,
                    "publish_url": "http://blog.local/posts/intro-ai-safety"
                }
            ]
        ),
        success_criteria=SuccessCriteria(
            primary=PrimaryCriteria(
                type=SuccessCriteriaType.DETERMINISTIC_MATCH,
                weight=0.80,
            ),
        ),
        error_codes={
            "SUCCESS": "Post published successfully",
            "CREATION_FAILED": "Could not create post",
            "PUBLISH_FAILED": "Could not publish post",
            "VALIDATION_ERROR": "Post validation failed"
        },
        initial_state=InitialState(
            start_url="http://cms.local",
            environment=Domain.CMS,
            logged_in=True,
            user_account={"username": "admin", "roles": ["editor", "admin"]}
        ),
        noise_profile=NoiseProfile(
            name="clean",
            network_latency_ms=[50, 100],
            request_timeout_probability=0.0
        ),
        estimated_complexity=EstimatedComplexity(
            expected_steps=4,
            expected_tokens=1500,
            expected_duration_seconds=120,
            unique_tools_required=1,
            information_integration_level="single_source"
        ),
        annotations=Annotations(
            created_by="system",
            created_date=datetime.now(),
            annotators=["cms_annotator"],
            inter_annotator_agreement=0.95,
            revision=1,
            status=TaskStatus.PUBLISHED
        )
    )


def generate_all_examples():
    """Generate and save all example tasks"""
    repo = TaskRepository("data/tasks")

    tasks = [
        create_ecommerce_example(),
        create_development_example(),
        create_cms_example(),
    ]

    for task in tasks:
        file_path = repo.save_task(task)
        print(f"✅ Saved: {task.task_id} -> {file_path}")

    # Print statistics
    stats = repo.get_statistics()
    print(f"\n📊 Task Repository Statistics:")
    print(f"   Total tasks: {stats['total_tasks']}")
    for domain, count in stats['by_domain'].items():
        print(f"   {domain}: {count} tasks")


if __name__ == "__main__":
    generate_all_examples()
