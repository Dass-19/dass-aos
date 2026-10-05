"""Allow `python -m dass_aos <command>`."""
import sys

from .cli import main

sys.exit(main())
