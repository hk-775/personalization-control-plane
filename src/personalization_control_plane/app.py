"""FastAPI application for the Personalization Control Plane."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .models import (
    ApprovalDecision,
    DemoScenarioRequest,
    ExperimentCreate,
    ExperimentTransition,
    ExposureEvent,
    FairnessEvaluationRequest,
    GuardrailEvaluationRequest,
    KillSwitchRequest,
    OperatorAction,
    OutcomeEvent,
    PolicyCreate,
    PolicyUpdate,
    RankRequest,
)
from .seed import DEMO_CANDIDATES
from .service import ControlPlane, ControlPlaneError
from .storage import Database

PACKAGE_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PACKAGE_ROOT / "web"


def _default_database_path() -> Path:
    configured = os.getenv("PCP_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "data" / "personalization-control-plane.db"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create an isolated application instance, optionally with a custom database."""

    database = Database(db_path or _default_database_path())
    control_plane = ControlPlane(database)
    app = FastAPI(
        title="Personalization Control Plane",
        summary="Governed experimentation and recommendation optimization",
        description=(
            "A local-first reference control plane with deterministic ranking, "
            "experiment lifecycle, privacy floors, fairness guardrails, approvals, "
            "rollback, and a hash-chained audit log."
        ),
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.state.control_plane = control_plane
    app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")

    @app.middleware("http")
    async def security_and_request_headers(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-Id") or f"req-http-{uuid4().hex[:16]}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ControlPlaneError)
    async def control_plane_error_handler(
        request: Request,
        exc: ControlPlaneError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_failed",
                    "message": "Request body or query parameters are invalid.",
                    "details": {"violations": jsonable_encoder(exc.errors())},
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def landing_page() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    @app.get("/dashboard", include_in_schema=False)
    @app.get("/dashboard.html", include_in_schema=False)
    def dashboard_page() -> FileResponse:
        return FileResponse(WEB_ROOT / "dashboard.html")

    @app.get("/architecture", include_in_schema=False)
    @app.get("/architecture.html", include_in_schema=False)
    def architecture_page() -> FileResponse:
        return FileResponse(WEB_ROOT / "architecture.html")

    @app.get("/health", tags=["system"])
    @app.get("/api/v1/health", tags=["system"])
    def health() -> dict[str, Any]:
        return control_plane.health()

    @app.get("/api/v1/portfolio", tags=["portfolio"])
    def portfolio() -> dict[str, Any]:
        return control_plane.portfolio()

    @app.get("/api/v1/policies", tags=["policies"])
    def list_policies() -> dict[str, Any]:
        return {"policies": control_plane.list_policies()}

    @app.post("/api/v1/policies", status_code=201, tags=["policies"])
    def create_policy(request: PolicyCreate) -> dict[str, Any]:
        return control_plane.create_policy(request)

    @app.get("/api/v1/policies/{policy_id}", tags=["policies"])
    def get_policy(policy_id: str) -> dict[str, Any]:
        return control_plane.get_policy(policy_id)

    @app.put("/api/v1/policies/{policy_id}", tags=["policies"])
    def update_policy(policy_id: str, request: PolicyUpdate) -> dict[str, Any]:
        return control_plane.update_policy(policy_id, request)

    @app.post("/api/v1/policies/{policy_id}/activate", tags=["policies"])
    def activate_policy(policy_id: str, request: OperatorAction) -> dict[str, Any]:
        return control_plane.activate_policy(
            policy_id,
            actor=request.actor,
            reason=request.reason,
        )

    @app.get("/api/v1/cohorts", tags=["cohorts"])
    def list_cohorts() -> dict[str, Any]:
        return {"cohorts": control_plane.list_cohorts()}

    @app.get("/api/v1/experiments", tags=["experiments"])
    def list_experiments() -> dict[str, Any]:
        return {"experiments": control_plane.list_experiments()}

    @app.post("/api/v1/experiments", status_code=201, tags=["experiments"])
    def create_experiment(request: ExperimentCreate) -> dict[str, Any]:
        return control_plane.create_experiment(request)

    @app.get("/api/v1/experiments/{experiment_id}", tags=["experiments"])
    def get_experiment(experiment_id: str) -> dict[str, Any]:
        return control_plane.get_experiment(experiment_id)

    @app.post(
        "/api/v1/experiments/{experiment_id}/transition",
        tags=["experiments"],
    )
    def transition_experiment(
        experiment_id: str,
        request: ExperimentTransition,
    ) -> dict[str, Any]:
        return control_plane.transition_experiment(experiment_id, request)

    @app.get("/api/v1/approvals", tags=["approvals"])
    def list_approvals(
        status: str | None = Query(default=None, pattern="^(pending|approved|denied)$"),
    ) -> dict[str, Any]:
        return {"approvals": control_plane.list_approvals(status)}

    @app.post("/api/v1/approvals/{approval_id}/decision", tags=["approvals"])
    def decide_approval(
        approval_id: str,
        request: ApprovalDecision,
    ) -> dict[str, Any]:
        return control_plane.decide_approval(approval_id, request)

    @app.post("/api/v1/recommendations/rank", tags=["recommendations"])
    def rank(request: RankRequest) -> dict[str, Any]:
        return control_plane.rank(request)

    @app.get("/api/v1/decisions/{decision_id}", tags=["recommendations"])
    def get_decision(decision_id: str) -> dict[str, Any]:
        return control_plane.get_decision(decision_id)

    @app.post("/api/v1/events/exposures", status_code=201, tags=["events"])
    def ingest_exposure(request: ExposureEvent) -> dict[str, Any]:
        return control_plane.ingest_exposure(request)

    @app.post("/api/v1/events/outcomes", status_code=201, tags=["events"])
    def ingest_outcome(request: OutcomeEvent) -> dict[str, Any]:
        return control_plane.ingest_outcome(request)

    @app.get("/api/v1/metrics", tags=["metrics"])
    def list_metrics(experiment_id: str | None = None) -> dict[str, Any]:
        return {"metrics": control_plane.list_metrics(experiment_id)}

    @app.post("/api/v1/guardrails/evaluate", tags=["guardrails"])
    def evaluate_guardrails_endpoint(
        request: GuardrailEvaluationRequest,
    ) -> dict[str, Any]:
        return control_plane.evaluate_experiment_guardrails(request)

    @app.post("/api/v1/guardrails/fairness", tags=["guardrails"])
    def evaluate_fairness_endpoint(
        request: FairnessEvaluationRequest,
    ) -> dict[str, Any]:
        return control_plane.evaluate_experiment_fairness(request)

    @app.get("/api/v1/control/kill-switch", tags=["control"])
    def get_kill_switch() -> dict[str, Any]:
        return control_plane.db.get_setting("kill_switch", {"enabled": False})

    @app.post("/api/v1/control/kill-switch", tags=["control"])
    def set_kill_switch(request: KillSwitchRequest) -> dict[str, Any]:
        return control_plane.set_kill_switch(request)

    @app.get("/api/v1/audit", tags=["audit"])
    def list_audit(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        return control_plane.list_audit(limit)

    @app.get("/api/v1/demo", tags=["demo"])
    def demo_manifest() -> dict[str, Any]:
        return {
            "fictional_data": True,
            "scenarios": [
                {
                    "id": "transparent-ranking",
                    "title": "Transparent deterministic ranking",
                    "duration_seconds": 12,
                },
                {
                    "id": "privacy-floor",
                    "title": "Minimum cohort privacy floor",
                    "duration_seconds": 8,
                },
                {
                    "id": "approval-gate",
                    "title": "Human approval for risky launches",
                    "duration_seconds": 10,
                },
                {
                    "id": "guardrail-rollback",
                    "title": "Automatic guardrail rollback",
                    "duration_seconds": 12,
                },
                {
                    "id": "kill-switch",
                    "title": "Global safe fallback",
                    "duration_seconds": 10,
                },
            ],
            "sample_candidates": DEMO_CANDIDATES,
        }

    @app.post("/api/v1/demo/scenarios/{scenario_id}", tags=["demo"])
    def run_demo_scenario(
        scenario_id: str,
        request: DemoScenarioRequest,
    ) -> dict[str, Any]:
        return control_plane.run_demo_scenario(scenario_id, request)

    @app.post("/api/v1/demo/reset", tags=["demo"])
    def reset_demo(request: OperatorAction) -> dict[str, Any]:
        return control_plane.reset_demo(actor=request.actor, reason=request.reason)

    return app


app = create_app()
