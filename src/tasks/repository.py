"""
Task Repository: Load, save, and manage task specifications
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from src.models.task import Task


class TaskRepository:
    """
    Manages task storage and retrieval.
    Tasks are stored as JSON files with version control.
    """

    def __init__(self, base_path: str = "data/tasks"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Create domain subdirectories
        for domain in ['ecommerce', 'development', 'cms', 'forum', 'knowledge']:
            (self.base_path / domain).mkdir(exist_ok=True)

    def save_task(self, task: Task) -> str:
        """
        Save a task to JSON file.
        Returns the file path.
        """
        domain = task.domain.value
        task_file = self.base_path / domain / f"{task.task_id}.json"

        # Save task as JSON
        task_data = task.model_dump(mode='json', by_alias=False, exclude_none=False)
        with open(task_file, 'w') as f:
            json.dump(task_data, f, indent=2, default=str)

        return str(task_file)

    def load_task(self, task_id: str) -> Task:
        """Load a task by its ID"""
        # Extract domain prefix from task_id
        domain_prefix = task_id.split('_')[0]
        domain_map = {
            'ec': 'ecommerce',
            'dev': 'development',
            'cms': 'cms',
            'forum': 'forum',
            'kb': 'knowledge',
        }

        domain = domain_map.get(domain_prefix)
        if not domain:
            raise ValueError(f"Unknown domain prefix in task_id: {task_id}")

        task_file = self.base_path / domain / f"{task_id}.json"
        if not task_file.exists():
            raise FileNotFoundError(f"Task not found: {task_id}")

        with open(task_file, 'r') as f:
            task_data = json.load(f)

        return Task(**task_data)

    def list_tasks(
        self,
        domain: Optional[str] = None,
        difficulty: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Task]:
        """List all tasks matching filters"""
        tasks = []

        # Determine which domains to search
        if domain:
            domains = [domain]
        else:
            domains = ['ecommerce', 'development', 'cms', 'forum', 'knowledge']

        for dom in domains:
            domain_path = self.base_path / dom
            if not domain_path.exists():
                continue

            for task_file in domain_path.glob("*.json"):
                try:
                    task = self.load_task(task_file.stem)

                    # Apply filters
                    if difficulty and task.difficulty != difficulty:
                        continue
                    if status and task.annotations.status != status:
                        continue

                    tasks.append(task)
                except Exception as e:
                    print(f"Error loading task {task_file.stem}: {e}")

        return tasks

    def delete_task(self, task_id: str) -> bool:
        """Delete a task file"""
        domain_prefix = task_id.split('_')[0]
        domain_map = {
            'ec': 'ecommerce',
            'dev': 'development',
            'cms': 'cms',
            'forum': 'forum',
            'kb': 'knowledge',
        }

        domain = domain_map.get(domain_prefix)
        if not domain:
            raise ValueError(f"Unknown domain prefix in task_id: {task_id}")

        task_file = self.base_path / domain / f"{task_id}.json"
        if task_file.exists():
            task_file.unlink()
            return True
        return False

    def get_task_count_by_domain(self) -> Dict[str, int]:
        """Get count of tasks per domain"""
        counts = {}
        for domain in ['ecommerce', 'development', 'cms', 'forum', 'knowledge']:
            domain_path = self.base_path / domain
            if domain_path.exists():
                counts[domain] = len(list(domain_path.glob("*.json")))
            else:
                counts[domain] = 0
        return counts

    def get_statistics(self) -> Dict:
        """Get overall task statistics"""
        tasks = self.list_tasks()

        if not tasks:
            return {
                'total_tasks': 0,
                'by_domain': {},
                'by_difficulty': {},
                'by_status': {},
            }

        # Count by various dimensions
        by_domain = {}
        by_difficulty = {1: 0, 2: 0, 3: 0}
        by_status = {}

        for task in tasks:
            # By domain
            domain = task.domain.value
            by_domain[domain] = by_domain.get(domain, 0) + 1

            # By difficulty
            by_difficulty[int(task.difficulty)] += 1

            # By status
            if task.annotations:
                status = task.annotations.status
                by_status[status] = by_status.get(status, 0) + 1

        return {
            'total_tasks': len(tasks),
            'by_domain': by_domain,
            'by_difficulty': by_difficulty,
            'by_status': by_status,
            'avg_inter_annotator_agreement': self._calc_avg_iaa(tasks),
        }

    @staticmethod
    def _calc_avg_iaa(tasks: List[Task]) -> float:
        """Calculate average inter-annotator agreement"""
        iaas = [
            t.annotations.inter_annotator_agreement
            for t in tasks
            if t.annotations and t.annotations.inter_annotator_agreement
        ]
        return sum(iaas) / len(iaas) if iaas else 0.0
