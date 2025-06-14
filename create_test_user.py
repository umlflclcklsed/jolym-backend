from sqlalchemy.orm import Session
from schemas.models import UserInDB
from auth_utils import hash_password
from config import SessionLocal
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_user():
    db = SessionLocal()
    try:
        # Check if test user already exists
        test_user = db.query(UserInDB).filter(UserInDB.email == "test@example.com").first()
        
        if test_user:
            logger.info("Test user already exists")
            return
        
        # Create test user
        hashed_password = hash_password("password123")
        new_user = UserInDB(
            email="test@example.com",
            hashed_password=hashed_password,
            name="Test User"
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"Test user created with ID: {new_user.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating test user: {str(e)}", exc_info=True)
    finally:
        db.close()

if __name__ == "__main__":
    create_test_user()