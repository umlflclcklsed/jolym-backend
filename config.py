from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from schemas.models import Base
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# PostgreSQL connection string
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_POSTGRES_URL")

# Remove SQLite-specific connect_args
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("Initializing the database...")
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()