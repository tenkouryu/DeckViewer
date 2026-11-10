"""Entry point for the embedded HTML viewer."""

import sys
from pathlib import Path

# Add Src directory to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from mtg.mtg_web_window import main


if __name__ == "__main__":
    main()
