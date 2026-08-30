"""Command-line entry point for the seeded local demo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pcp-demo",
        description="Run the seeded Personalization Control Plane demo.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("PCP_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        default=int(os.getenv("PCP_PORT", "8102")),
        type=int,
        help="Bind port (default: 8102).",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("PCP_DB_PATH", "data/personalization-control-plane.db"),
        help="SQLite database path.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("PCP_LOG_LEVEL", "info"),
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_path = Path(args.db).expanduser()
    os.environ["PCP_DB_PATH"] = str(database_path)
    from .app import app as application

    print(f"Personalization Control Plane: http://{args.host}:{args.port}")
    print(f"Operator dashboard:            http://{args.host}:{args.port}/dashboard")
    print(f"Interactive architecture:      http://{args.host}:{args.port}/architecture")
    print(f"OpenAPI:                       http://{args.host}:{args.port}/api/docs")
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()
