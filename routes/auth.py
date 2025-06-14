from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import logging
import os
from sqlalchemy.exc import IntegrityError
from auth_utils import (
    hash_password, verify_password, create_access_token, verify_access_token,
    generate_password_reset_token, create_password_reset_token, verify_password_reset_token,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
)
from config import get_db
from schemas.models import *
from datetime import timedelta, datetime
from utils.email_utils import send_password_reset_email

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
            logger.warning(f"Login attempt with incorrect passwordd for user: {user.email}")
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

@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Request a password reset link to be sent to the user's email.
    """
    try:
        # Find the user by email
        user = db.query(UserInDB).filter(UserInDB.email == request.email).first()
        
        # For security reasons, don't reveal if the email exists or not
        if not user:
            logger.info(f"Password reset requested for non-existent email: {request.email}")
            return {"message": "If your email is registered, you will receive a password reset link.", "success": True}
        
        # Generate a reset token
        reset_token = create_password_reset_token(user.id)
        
        # For development, log the token
        logger.info(f"DEVELOPMENT: Reset token for {user.email}: {reset_token}")
        logger.info(f"DEVELOPMENT: Reset URL: {os.getenv('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={reset_token}")
        
        # Store the token in the database
        token_expires = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        
        # Check if there's an existing token and update it, or create a new one
        db_token = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False
        ).first()
        
        if db_token:
            db_token.token = reset_token
            db_token.expires_at = token_expires
            db_token.used = False
            db_token.created_at = datetime.utcnow()
        else:
            db_token = PasswordResetToken(
                user_id=user.id,
                token=reset_token,
                expires_at=token_expires
            )
            db.add(db_token)
        
        db.commit()
        
        # Send the reset email
        email_sent = send_password_reset_email(user.email, reset_token)
        
        if not email_sent:
            logger.error(f"Failed to send password reset email to {user.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password reset email. Please try again later."
            )
        
        logger.info(f"Password reset email sent to {user.email}")
        return {"message": "If your email is registered, you will receive a password reset link.", "success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in forgot_password: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later."
        )

@router.post("/reset-password", response_model=PasswordResetResponse)
def reset_password(request: PasswordResetConfirm, db: Session = Depends(get_db)):
    """
    Reset a user's password using a valid reset token.
    """
    try:
        # Verify the token
        payload = verify_password_reset_token(request.token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token"
            )
        
        user_id = int(payload.get("sub"))
        
        # Find the token in the database
        db_token = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == request.token,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.utcnow()
        ).first()
        
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token"
            )
        
        # Find the user
        user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate the new password
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        
        # Update the user's password
        user.hashed_password = hash_password(request.new_password)
        
        # Mark the token as used
        db_token.used = True
        
        db.commit()
        
        logger.info(f"Password reset successful for user ID: {user_id}")
        return {"message": "Password has been reset successfully", "success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in reset_password: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later."
        )
