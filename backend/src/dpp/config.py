# backend/src/dpp/config.py
import os

# Only used as a default; Makefile/compose override when needed.
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
