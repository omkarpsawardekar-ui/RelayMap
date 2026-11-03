import os

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection
from app.core.dependencies import get_current_user

from app.api import (
    users,
    projects,
    documents,
    knowledge,
    continuity,
    relationships,
    handovers,
    github,
    auth,
    workspaces,
)


# --------------------------------------------------
# APPLICATION INITIALIZATION
# --------------------------------------------------

app = FastAPI(
    title="RelayMap API",
    description="Evidence-First Project Continuity and Knowledge Handover Platform",
    version="0.1.0",
)


# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

# Local development origins.
local_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Production frontend origins.
# Supports one or multiple comma-separated URLs.
configured_origins = (
    os.getenv("FRONTEND_URLS")
    or os.getenv("FRONTEND_URL")
    or ""
)

production_origins = [
    origin.strip().rstrip("/")
    for origin in configured_origins.split(",")
    if origin.strip()
]

# Combine and remove duplicates.
allowed_origins = list(
    dict.fromkeys(local_origins + production_origins)
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# AUTHENTICATION AND ROUTER REGISTRATION
# --------------------------------------------------

# Require authentication for business API routers.
# Authentication endpoints are registered separately
# because login and initial password setup do not
# require an existing JWT.

auth_required = [Depends(get_current_user)]

app.include_router(users.router, dependencies=auth_required)
app.include_router(projects.router, dependencies=auth_required)
app.include_router(documents.router, dependencies=auth_required)
app.include_router(knowledge.router, dependencies=auth_required)
app.include_router(continuity.router, dependencies=auth_required)
app.include_router(relationships.router, dependencies=auth_required)
app.include_router(handovers.router, dependencies=auth_required)
app.include_router(github.router, dependencies=auth_required)

# Authentication endpoints manage their own access requirements.
app.include_router(auth.router)

app.include_router(
    workspaces.router,
    dependencies=auth_required,
)


# --------------------------------------------------
# ROOT ENDPOINT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Welcome to RelayMap API",
        "status": "running",
    }


# --------------------------------------------------
# BACKEND HEALTH CHECK
# --------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "RelayMap Backend",
    }


# --------------------------------------------------
# DATABASE HEALTH CHECK
# --------------------------------------------------

@app.get("/api/health/db")
def database_health():
    try:
        check_database_connection()

        return {
            "status": "connected",
            "database": "PostgreSQL",
        }

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc