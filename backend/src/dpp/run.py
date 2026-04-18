# backend/src/dpp/run.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.getenv("DOCKER") == "1"


def build_mongo_uri(
    mode: str,
    mongo_uri: str | None,
    db_user: str | None,
    db_pass: str | None,
    db_host: str | None,
    db_port: int,
    db_name: str,
    db_auth_source: str,
) -> str:
    if mongo_uri:
        return mongo_uri

    if not db_host:
        db_host = "mongo" if mode == "docker" else "127.0.0.1"

    if db_user and db_pass:
        auth = f"{db_user}:{db_pass}@"
        suffix = f"?authSource={db_auth_source}"
    else:
        auth = ""
        suffix = ""

    return f"mongodb://{auth}{db_host}:{db_port}/{db_name}{suffix}"


def main():
    parser = argparse.ArgumentParser(description="Run DPP API with CLI-configured settings.")
    parser.add_argument(
        "--mode",
        choices=["auto", "local", "docker"],
        default="auto",
        help="Where the API runs. Affects default DB host & bind address.",
    )
    parser.add_argument("--host", default=None, help="Uvicorn bind host (default depends on mode).")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn port (default 8000).")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload.")
    parser.add_argument("--mongo-uri", default=None, help="Full MongoDB URI (overrides parts below).")
    parser.add_argument("--db-user", default="root", help="DB username (default root).")
    parser.add_argument("--db-pass", default="example", help="DB password (default example).")
    parser.add_argument("--db-host", default=None, help="DB host (default mongo in docker, 127.0.0.1 locally).")
    parser.add_argument("--db-port", type=int, default=27017, help="DB port (default 27017).")
    parser.add_argument("--db-name", default="dpp_prototype", help="DB name (default dpp_prototype).")
    parser.add_argument("--db-auth-source", default="admin", help="DB authSource (default admin).")

    # CORS / ngrok
    parser.add_argument(
        "--ngrok-host",
        action="append",
        default=[],
        help="Add an ngrok host. Can be repeated.",
    )
    parser.add_argument("--cors", default="", help="Comma-separated extra allowed origins (in addition to localhost).")
    parser.add_argument("--log-level", default="info", help="Uvicorn log level.")

    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        mode = "docker" if in_docker() else "local"

    # Build & export DB URI
    mongo_uri = build_mongo_uri(
        mode=mode,
        mongo_uri=args.mongo_uri,
        db_user=args.db_user,
        db_pass=args.db_pass,
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
        db_auth_source=args.db_auth_source,
    )
    os.environ["MONGODB_URI"] = mongo_uri

    # Build & export CORS allow list
    base_origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    }
    base_origins.update({f"https://{h}" if not h.startswith("http") else h for h in (args.ngrok_host or [])})
    if args.cors:
        base_origins.update({o.strip() for o in args.cors.split(",") if o.strip()})

    os.environ["CORS_ALLOW_ORIGINS"] = ",".join(sorted(base_origins))
    os.environ.setdefault("CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.ngrok-free\.app")

    # Default bind address
    host = args.host or ("0.0.0.0" if mode == "docker" else "127.0.0.1")

    print(f">> MODE: {mode}")
    print(f">> USING MONGODB_URI: {mongo_uri}")
    print(f">> ALLOW_ORIGINS: {os.environ['CORS_ALLOW_ORIGINS']}")
    print(f">> ALLOW_ORIGIN_REGEX: {os.environ['CORS_ALLOW_ORIGIN_REGEX']}")
    uvicorn.run(
        "dpp.server:app",
        host=host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
