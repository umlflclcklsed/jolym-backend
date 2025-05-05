from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging
from sqlalchemy.exc import IntegrityError
from auth_utils import verify_access_token
from fastapi.security import OAuth2PasswordBearer
from config import get_db
from schemas.models import *
from typing import List
from utils.ai_roadmap_generator import generate_roadmap
from pydantic import BaseModel

# Set up logging
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class RoadmapGenerateRequest(BaseModel):
    query: str

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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

@router.get("/roadmaps/", response_model=List[Roadmap])
def get_roadmaps(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """Get a list of all roadmaps"""
    try:
        roadmaps = db.query(RoadmapInDB).offset(skip).limit(limit).all()
        return roadmaps
    except Exception as e:
        logger.error(f"Error retrieving roadmaps: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roadmaps"
        )

@router.get("/roadmaps/{roadmap_id}", response_model=Roadmap)
def get_roadmap(roadmap_id: int, db: Session = Depends(get_db)):
    """Get a specific roadmap by ID"""
    try:
        roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
        if roadmap is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roadmap not found"
            )
        return roadmap
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roadmap"
        )

@router.post("/roadmaps/", response_model=Roadmap, status_code=status.HTTP_201_CREATED)
def create_roadmap(roadmap: RoadmapCreate, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Create a new roadmap"""
    try:
        db_roadmap = RoadmapInDB(
            name=roadmap.name,
            description=roadmap.description
        )
        db.add(db_roadmap)
        db.commit()
        db.refresh(db_roadmap)
        
        # Create all steps
        for step_data in roadmap.steps:
            db_step = RoadmapStepInDB(
                id=step_data.id,
                title=step_data.title,
                description=step_data.description,
                icon=step_data.icon,
                icon_color=step_data.icon_color,
                icon_bg=step_data.icon_bg,
                time_to_complete=step_data.time_to_complete,
                difficulty=step_data.difficulty,
                tips=step_data.tips,
                roadmap_id=db_roadmap.id
            )
            db.add(db_step)
            
            # Create resources for this step
            for resource_data in step_data.resources:
                db_resource = ResourceInDB(
                    title=resource_data.title,
                    url=resource_data.url,
                    source=resource_data.source,
                    description=resource_data.description,
                    step_id=db_step.id
                )
                db.add(db_resource)
        
        db.commit()
        return db_roadmap
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Roadmap creation failed due to data constraints"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create roadmap"
        )

@router.post("/roadmaps/{roadmap_id}/favorite", status_code=status.HTTP_200_OK)
def favorite_roadmap(roadmap_id: int, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Add a roadmap to user's favorites"""
    try:
        # Check if roadmap exists
        roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
        if roadmap is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roadmap not found"
            )
        
        # Check if already favorited
        existing = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == current_user.id,
            UserFavoriteRoadmap.roadmap_id == roadmap_id
        ).first()
        
        if existing:
            return {"message": "Roadmap is already in favorites"}
        
        # Add to favorites
        favorite = UserFavoriteRoadmap(user_id=current_user.id, roadmap_id=roadmap_id)
        db.add(favorite)
        db.commit()
        
        return {"message": "Roadmap added to favorites"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding roadmap to favorites: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add roadmap to favorites"
        )

@router.post("/roadmaps/steps/{step_id}/progress", status_code=status.HTTP_200_OK)
def update_step_progress(step_id: str, completed: bool = True, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Update user's progress on a roadmap step"""
    try:
        # Check if step exists
        step = db.query(RoadmapStepInDB).filter(RoadmapStepInDB.id == step_id).first()
        if step is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roadmap step not found"
            )
        
        # Get current progress or create new
        progress = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == current_user.id,
            UserRoadmapProgress.step_id == step_id
        ).first()
        
        if progress:
            progress.completed = completed
            if completed:
                progress.completed_at = datetime.now()
        else:
            completed_at = datetime.now() if completed else None
            progress = UserRoadmapProgress(
                user_id=current_user.id,
                step_id=step_id,
                completed=completed,
                completed_at=completed_at
            )
            db.add(progress)
            
        db.commit()
        
        return {"message": f"Progress updated. Step marked as {'completed' if completed else 'not completed'}"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating step progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update progress"
        )

@router.get("/user/roadmaps/progress", status_code=status.HTTP_200_OK)
def get_user_progress(db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Get the user's progress across all roadmaps"""
    try:
        progress = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == current_user.id,
        ).all()
        
        result = {}
        for p in progress:
            step = db.query(RoadmapStepInDB).filter(RoadmapStepInDB.id == p.step_id).first()
            if step:
                roadmap_id = step.roadmap_id
                if roadmap_id not in result:
                    result[roadmap_id] = {
                        "roadmap_id": roadmap_id,
                        "steps_completed": 0,
                        "total_steps": 0,
                        "steps": []
                    }
                
                result[roadmap_id]["steps"].append({
                    "step_id": p.step_id,
                    "completed": p.completed,
                    "completed_at": p.completed_at
                })
                
                if p.completed:
                    result[roadmap_id]["steps_completed"] += 1
        
        # Get total steps for each roadmap
        for roadmap_id in result:
            total = db.query(RoadmapStepInDB).filter(
                RoadmapStepInDB.roadmap_id == roadmap_id
            ).count()
            result[roadmap_id]["total_steps"] = total
        
        return list(result.values())
    except Exception as e:
        logger.error(f"Error retrieving user progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve progress"
        )

@router.get("/user/roadmaps/favorites", response_model=List[Roadmap])
def get_user_favorites(db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Get the user's favorite roadmaps"""
    try:
        favorites = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == current_user.id
        ).all()
        
        roadmap_ids = [fav.roadmap_id for fav in favorites]
        roadmaps = db.query(RoadmapInDB).filter(RoadmapInDB.id.in_(roadmap_ids)).all()
        
        return roadmaps
    except Exception as e:
        logger.error(f"Error retrieving user favorites: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve favorites"
        )

@router.post("/roadmaps/generate", response_model=Roadmap, status_code=status.HTTP_201_CREATED)
def generate_ai_roadmap(request: RoadmapGenerateRequest, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    """Generate a roadmap using AI based on the user's query"""
    try:
        logger.info(f"Generating roadmap for query: {request.query}")
        
        # Generate roadmap using AI
        roadmap_data = generate_roadmap(request.query)
        if not roadmap_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate roadmap. AI service might be unavailable."
            )
        
        # Create the roadmap in the database
        db_roadmap = RoadmapInDB(
            name=roadmap_data.get("name", "Generated Roadmap"),
            description=roadmap_data.get("description", ""),
            query_text=request.query
        )
        db.add(db_roadmap)
        db.commit()
        db.refresh(db_roadmap)
        
        # Create steps for the roadmap
        for step_data in roadmap_data.get("steps", []):
            db_step = RoadmapStepInDB(
                id=step_data.get("id", ""),
                title=step_data.get("title", ""),
                description=step_data.get("description", ""),
                icon=step_data.get("icon", ""),
                icon_color=step_data.get("iconColor", ""),
                icon_bg=step_data.get("iconBg", ""),
                time_to_complete=step_data.get("timeToComplete", ""),
                difficulty=step_data.get("difficulty", 1),
                tips=step_data.get("tips", ""),
                roadmap_id=db_roadmap.id
            )
            db.add(db_step)
            
            # Create resources for this step
            for resource_data in step_data.get("resources", []):
                db_resource = ResourceInDB(
                    title=resource_data.get("title", ""),
                    url=resource_data.get("url", ""),
                    source=resource_data.get("source", ""),
                    description=resource_data.get("description", ""),
                    step_id=db_step.id
                )
                db.add(db_resource)
        
        db.commit()
        logger.info(f"Successfully created AI-generated roadmap with ID: {db_roadmap.id}")
        return db_roadmap
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating AI-generated roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create roadmap"
        )
