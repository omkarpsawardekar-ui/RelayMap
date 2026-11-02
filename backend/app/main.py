from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection

from app.api import users, projects, documents, knowledge, continuity, relationships, handovers, github 

# Initialize RelayMap application
app = FastAPI(
    title="RelayMap API",
    description="Evidence-First Project Continuity and Knowledge Handover Platform",
    version="0.1.0"
)


# Allow React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(users.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(knowledge.router)
app.include_router(continuity.router)
app.include_router(relationships.router)
app.include_router(handovers.router)
app.include_router(github.router)

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to RelayMap API",
        "status": "running"
    }


# Backend health check
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "RelayMap Backend"
    }


# PostgreSQL connection health check
@app.get("/api/health/db")
def database_health():
    try:
        check_database_connection()

        return {
            "status": "connected",
            "database": "PostgreSQL"
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )