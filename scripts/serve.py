"""Start the production API and built frontend on a platform-provided port."""

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
uvicorn.run("server.studio:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
