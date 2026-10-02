"""Make the engine scripts importable from the tests."""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENGINE / ".scripts"))
