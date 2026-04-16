"""
Configuration settings for the benchmark system
"""

from pathlib import Path

# Project structure
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TASKS_DIR = DATA_DIR / "tasks"
RESULTS_DIR = DATA_DIR / "results"
LOGS_DIR = PROJECT_ROOT / "logs"

# Create directories if they don't exist
for directory in [DATA_DIR, TASKS_DIR, RESULTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Database configuration
DATABASE_URL = "sqlite:///./benchmark.db"  # Default to SQLite
# For PostgreSQL: DATABASE_URL = "postgresql://user:password@localhost/benchmark"

# Task domains
DOMAINS = ["ecommerce", "development", "cms", "forum", "knowledge"]

# Difficulty levels
DIFFICULTIES = {
    1: "easy",
    2: "medium",
    3: "hard",
}

# Task status
TASK_STATUS = ["draft", "pilot", "published", "archived"]

# Evaluation settings
EVALUATION_DIMENSIONS = {
    "outcome": 0.40,
    "efficiency": 0.20,
    "robustness": 0.25,
    "complexity": 0.15,
}

# Noise profiles
NOISE_PROFILES = ["clean", "realistic", "adversarial", "degraded"]

# IAA (Inter-Annotator Agreement) threshold
IAA_THRESHOLD = 0.75  # Cohen's Kappa

# Benchmark parameters
HUMAN_BASELINE_TARGET = (0.70, 0.85)  # (min, max) success rate
SOTA_BASELINE_TARGET = (0.30, 0.50)   # (min, max) success rate

# Context window sizes (tokens)
CONTEXT_WINDOW_SIZES = {
    "small": 8000,
    "medium": 32000,
    "large": 128000,
}

# API settings
API_HOST = "0.0.0.0"
API_PORT = 8000
API_DEBUG = True
