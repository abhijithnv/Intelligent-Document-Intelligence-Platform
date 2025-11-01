from fastapi import FastAPI
from .database import engine, Base, enable_pgvector_extension
from app.auth import routes as auth_routes
from app.api.documents import router as document_routes
from app.admin.admin_access import router as admin_routes
from app.cache import get_redis_client, is_redis_available

# Enable pgvector extension before creating tables
enable_pgvector_extension()

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize Redis connection
get_redis_client()
if is_redis_available():
    print(" Redis caching is available and enabled")
else:
    print(" Redis caching is not available - running without cache")

app = FastAPI(
    title="Intelligent Document Intelligence Platform",
    version="1.0.0",
    description="FastAPI microservice for document summarization and semantic search"
)

@app.get("/")
def root():
    return {
        "message": "Welcome to Intelligent Document Intelligence Platform!",
        "redis_cache": "enabled" if is_redis_available() else "disabled"
    }


app.include_router(auth_routes.router)

app.include_router(document_routes)

app.include_router(admin_routes)