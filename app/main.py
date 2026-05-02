"""FastAPI entrypoint for the local MARS MVP.

Phase 0/1 keeps the API surface intentionally small: the app only exposes a
health endpoint so we can verify the service boots before adding memory APIs in
later phases.
"""

from fastapi import FastAPI


app = FastAPI(title="MARS", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple liveness signal for local development."""
    return {"status": "ok"}
