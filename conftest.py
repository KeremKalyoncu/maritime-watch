import sys
from pathlib import Path

# make `import src.*` work from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent))
