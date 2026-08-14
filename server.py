#!/usr/bin/env python3
"""
Hovedserver for Byggeval webapplikasjon.
Kjører FastAPI med Uvicorn.
"""

import sys
import os
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from byggeval.api import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"\n🚀 Starter Byggeval på http://localhost:{port}\n")
    uvicorn.run("byggeval.api:app", host=host, port=port, reload=True)
