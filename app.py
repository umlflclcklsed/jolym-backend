from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from config import init_db
from routes.auth import router as auth_router
from routes.roadmap import router as roadmap_router

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create utils directory if it doesn't exist
os.makedirs(os.path.join(os.path.dirname(__file__), 'utils'), exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(roadmap_router, prefix="/roadmap", tags=["Roadmap"])

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "Hello World"}