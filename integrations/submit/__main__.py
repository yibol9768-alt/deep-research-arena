"""Entry point so `python -m integrations.submit ...` works."""
from .cli import main
import sys

sys.exit(main())
