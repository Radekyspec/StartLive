import os
from pathlib import Path

version = os.environ.get("VERSION", "0.0.0-dev")
version_file = Path(__file__).resolve().parents[1] / "constant" / "_version.py"
version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
