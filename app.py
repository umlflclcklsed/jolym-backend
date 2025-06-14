from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from config import init_db
from routes.auth import router as auth_router
from routes.roadmap import router as roadmap_router
from routes.dashboard import router as dashboard_router

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create utils directory if it doesn't exist
os.makedirs(os.path.join(os.path.dirname(__file__), 'utils'), exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Initialize database
init_db()

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(roadmap_router, prefix="/roadmap", tags=["Roadmap"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "Hello World"}