from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import logging
from sqlalchemy.exc import IntegrityError
from auth_utils import hash_password, verify_password, create_access_token, verify_access_token
from config import get_db
from schemas.models import *
from datetime import timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user = db.query(UserInDB).filter(UserInDB.email == user.email).first()
        if not db_user:
            logger.warning(f"Login attempt with non-existent email: {user.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not verify_password(user.password, db_user.hashed_password):
            logger.warning(f"Login attempt with incorrect password for user: {user.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=30)
        )
        logger.info(f"User logged in successfully: {user.email}")
        return {"access_token": access_token, "type": "user"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later."
        )

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user: CreateUser, db: Session = Depends(get_db)):
    try:
        logger.info(f"Attempting to register user: {user.email}")
        
        # Check if email already exists
        if db.query(UserInDB).filter(UserInDB.email == user.email).first():
            logger.warning(f"Registration failed - Email already registered: {user.email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered. Please use a different email or recover your account."
            )
        
        # Validate input data
        if not user.email or not user.password or not user.name:
            logger.warning(f"Registration failed - Missing required fields")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All fields (name, email, password) are required"
            )
        
        # Email format validation
        if "@" not in user.email or "." not in user.email:
            logger.warning(f"Registration failed - Invalid email format: {user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Create user
        try:
            hashed_password = hash_password(user.password)
            new_user = UserInDB(
                email=user.email, 
                hashed_password=hashed_password, 
                name=user.name
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already registered. Please use a different email."
            )
        
        # Generate token
        access_token = create_access_token(
            data={"sub": new_user.email},
            expires_delta=timedelta(minutes=30)
        )
        logger.info(f"User registered successfully: {user.email}")
        return {"access_token": access_token, "type": "user"}
    
    except HTTPException:
        # Re-raise HTTP exceptions as they already have the appropriate status code
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error registering user: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An unexpected error occurred during registration. Please try again later."
        )

@router.delete("/users/", response_model=dict, status_code=status.HTTP_200_OK)
def delete_all_users(db: Session = Depends(get_db)):
    try:
        count = db.query(UserInDB).count()
        db.query(UserInDB).delete()
        db.commit()
        return {"message": f"All users deleted successfully. {count} users removed."}
    except Exception as e:
        db.rollback() 
        logger.error(f"Error deleting users: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to delete users: {str(e)}"
        )
    
@router.get("/users/me", status_code=status.HTTP_200_OK)
def get_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = verify_access_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token content",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving your profile"
        )
