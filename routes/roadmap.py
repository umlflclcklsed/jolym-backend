from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import text
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from config import get_db
from schemas.models import (
    RoadmapInDB, RoadmapStepInDB, ResourceInDB, UserInDB,
    Roadmap, RoadmapCreate, RoadmapStep, UserFavoriteRoadmap,
    UserRoadmapProgress
)
from auth_utils import verify_access_token
from utils.embedding_utils import generate_embedding, find_similar_roadmap
from utils.redis_cache import cache_key, get_from_cache, save_to_cache
from utils.ai_roadmap_generator import generate_roadmap

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache prefix for roadmaps
CACHE_PREFIX_ROADMAP = "roadmap"
CACHE_PREFIX_ROADMAP_QUERY = "roadmap_query"

# Similarity threshold for finding similar roadmaps
SIMILARITY_THRESHOLD = 0.85

router = APIRouter(
    prefix="/roadmaps",
    tags=["roadmaps"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Get current user
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to an unexpected error"
        )

# Get current user if available, or None if not authenticated
async def get_optional_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        return None
    
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None

# Setup PostgreSQL vector extension
@router.on_event("startup")
async def startup():
    import sys
    
    # Get reference to the embedding_utils module
    from utils import embedding_utils
    
    db = next(get_db())
    try:
        # Check if pgvector extension exists
        result = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        if not result.fetchone():
            # Try to create pgvector extension
            try:
                db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                db.commit()
                logger.info("Created pgvector extension")
            except Exception as e:
                logger.warning(f"Could not create pgvector extension: {str(e)}")
                # Disable embeddings if pgvector is not available
                embedding_utils.EMBEDDINGS_SUPPORTED = False
                logger.warning("Embeddings disabled due to missing pgvector extension")
    except Exception as e:
        logger.error(f"Error setting up pgvector extension: {str(e)}", exc_info=True)
        # Disable embeddings if there's any error
        embedding_utils.EMBEDDINGS_SUPPORTED = False
        logger.warning("Embeddings disabled due to error")
    finally:
        db.close()

# Generate roadmap from query
@router.post("/generate", response_model=Roadmap)
async def create_roadmap_from_query(
    query: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    user: Optional[UserInDB] = Depends(get_optional_user)
):
    """Generate a roadmap from a natural language query"""
    try:
        logger.info(f"Processing roadmap generation request for query: {query}")
        
        # Check if embeddings are supported
        from utils.embedding_utils import EMBEDDINGS_SUPPORTED
        
        # Check cache first
        cache_query_key = cache_key(CACHE_PREFIX_ROADMAP_QUERY, query)
        cached_roadmap_id = get_from_cache(cache_query_key)
        
        if cached_roadmap_id:
            # Get roadmap from cache
            roadmap_id = cached_roadmap_id.get("id")
            roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
            if roadmap:
                logger.info(f"Retrieved roadmap from cache: {roadmap.name}")
                return roadmap
        
        # Find similar roadmap in database if embeddings are supported
        similar_roadmap_id = None
        if EMBEDDINGS_SUPPORTED:
            similar_roadmap_id = find_similar_roadmap(
                query_text=query,
                db_session=db,
                roadmap_model=RoadmapInDB,
                similarity_threshold=SIMILARITY_THRESHOLD
            )
        
        if similar_roadmap_id:
            # Found similar roadmap
            roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == similar_roadmap_id).first()
            logger.info(f"Found similar roadmap: {roadmap.name}")
            
            # Cache the roadmap ID for this query
            save_to_cache(cache_query_key, {"id": roadmap.id})
            
            return roadmap
        
        # Generate new roadmap
        roadmap_data = generate_roadmap(query)
        if not roadmap_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate roadmap"
            )
        
        # Create embedding for the query if supported
        embedding = None
        if EMBEDDINGS_SUPPORTED:
            embedding = generate_embedding(query)
        
        # Create roadmap in database
        db_roadmap = RoadmapInDB(
            name=roadmap_data.get("name", "Untitled Roadmap"),
            description=roadmap_data.get("description", ""),
            embedding=embedding,
            query_text=query
        )
        db.add(db_roadmap)
        db.commit()
        db.refresh(db_roadmap)
        
        # Add steps and resources
        for step_data in roadmap_data.get("steps", []):
            db_step = RoadmapStepInDB(
                id=step_data.get("id", "0-0"),
                title=step_data.get("title", "Untitled Step"),
                description=step_data.get("description", ""),
                icon=step_data.get("icon", "Code"),
                icon_color=step_data.get("iconColor", "text-blue-600"),
                icon_bg=step_data.get("iconBg", "bg-blue-100"),
                time_to_complete=step_data.get("timeToComplete", ""),
                difficulty=step_data.get("difficulty", 1),
                tips=step_data.get("tips", ""),
                roadmap_id=db_roadmap.id
            )
            db.add(db_step)
            db.commit()
            
            for resource_data in step_data.get("resources", []):
                db_resource = ResourceInDB(
                    title=resource_data.get("title", "Untitled Resource"),
                    url=resource_data.get("url", "#"),
                    source=resource_data.get("source", ""),
                    description=resource_data.get("description", ""),
                    step_id=db_step.id
                )
                db.add(db_resource)
        
        db.commit()
        
        # Cache the roadmap ID for this query
        save_to_cache(cache_query_key, {"id": db_roadmap.id})
        
        logger.info(f"Created new roadmap: {db_roadmap.name}")
        return db_roadmap
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating the roadmap"
        )

@router.post("/", response_model=Roadmap, status_code=status.HTTP_201_CREATED)
def create_roadmap(roadmap: RoadmapCreate, db: Session = Depends(get_db), user = Depends(get_current_user)):
    """Create a new roadmap with steps and resources"""
    try:
        logger.info(f"Creating new roadmap: {roadmap.name}")
        
        # Validate roadmap data
        if not roadmap.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Roadmap name is required"
            )
        
        # Create roadmap
        db_roadmap = RoadmapInDB(
            name=roadmap.name,
            description=roadmap.description,
            embedding=None,  # No embedding for manually created roadmaps
            query_text=None
        )
        db.add(db_roadmap)
        try:
            db.commit()
            db.refresh(db_roadmap)
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error creating roadmap: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A roadmap with this name may already exist"
            )
        
        # Create steps and resources
        try:
            for step in roadmap.steps:
                db_step = RoadmapStepInDB(
                    id=step.id,
                    title=step.title,
                    description=step.description,
                    icon=step.icon,
                    icon_color=step.icon_color,
                    icon_bg=step.icon_bg,
                    time_to_complete=step.time_to_complete,
                    difficulty=step.difficulty,
                    tips=step.tips,
                    roadmap_id=db_roadmap.id
                )
                db.add(db_step)
                db.commit()
                
                for resource in step.resources:
                    db_resource = ResourceInDB(
                        title=resource.title,
                        url=resource.url,
                        source=resource.source,
                        description=resource.description,
                        step_id=db_step.id
                    )
                    db.add(db_resource)
            
            db.commit()
            logger.info(f"Roadmap created successfully: {roadmap.name}")
            return db_roadmap
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error adding steps/resources: {str(e)}")
            # Delete the roadmap if step creation fails
            db.query(RoadmapInDB).filter(RoadmapInDB.id == db_roadmap.id).delete()
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Error creating roadmap steps or resources"
            )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the roadmap"
        )

@router.get("/", response_model=List[Roadmap])
def get_roadmaps(db: Session = Depends(get_db)):
    """Get all roadmaps"""
    try:
        roadmaps = db.query(RoadmapInDB).all()
        return roadmaps
    except Exception as e:
        logger.error(f"Error retrieving roadmaps: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roadmaps"
        )

@router.get("/{roadmap_id}", response_model=Roadmap)
def get_roadmap(roadmap_id: int, db: Session = Depends(get_db)):
    """Get a specific roadmap by ID"""
    try:
        # Try to get from cache first
        cache_id_key = cache_key(CACHE_PREFIX_ROADMAP, roadmap_id)
        cached_roadmap = get_from_cache(cache_id_key)
        
        if cached_roadmap:
            logger.info(f"Retrieved roadmap from cache: ID {roadmap_id}")
            return cached_roadmap
        
        # Get from database
        roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
        if roadmap is None:
            logger.warning(f"Roadmap not found: ID {roadmap_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Roadmap not found"
            )
        
        # Save to cache
        save_to_cache(cache_id_key, roadmap.__dict__)
        
        return roadmap
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving roadmap: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve the roadmap"
        )

@router.post("/{roadmap_id}/favorite", status_code=status.HTTP_200_OK)
async def favorite_roadmap(
    roadmap_id: int,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Add a roadmap to user's favorites"""
    try:
        # Check if roadmap exists
        roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
        if not roadmap:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roadmap not found"
            )
        
        # Check if already favorited
        existing = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == user.id,
            UserFavoriteRoadmap.roadmap_id == roadmap_id
        ).first()
        
        if existing:
            return {"message": "Roadmap is already in favorites"}
        
        # Add to favorites
        favorite = UserFavoriteRoadmap(
            user_id=user.id,
            roadmap_id=roadmap_id
        )
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

@router.delete("/{roadmap_id}/favorite", status_code=status.HTTP_200_OK)
async def unfavorite_roadmap(
    roadmap_id: int,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Remove a roadmap from user's favorites"""
    try:
        # Find the favorite entry
        favorite = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == user.id,
            UserFavoriteRoadmap.roadmap_id == roadmap_id
        ).first()
        
        if not favorite:
            return {"message": "Roadmap is not in favorites"}
        
        # Remove from favorites
        db.delete(favorite)
        db.commit()
        
        return {"message": "Roadmap removed from favorites"}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing roadmap from favorites: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove roadmap from favorites"
        )

@router.get("/favorites", response_model=List[Roadmap])
async def get_favorite_roadmaps(
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Get user's favorite roadmaps"""
    try:
        favorites = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == user.id
        ).all()
        
        roadmap_ids = [fav.roadmap_id for fav in favorites]
        roadmaps = db.query(RoadmapInDB).filter(
            RoadmapInDB.id.in_(roadmap_ids)
        ).all()
        
        return roadmaps
    
    except Exception as e:
        logger.error(f"Error retrieving favorite roadmaps: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve favorite roadmaps"
        )

@router.post("/{roadmap_id}/steps/{step_id}/complete", status_code=status.HTTP_200_OK)
async def mark_step_complete(
    roadmap_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Mark a roadmap step as completed"""
    try:
        # Check if step exists
        step = db.query(RoadmapStepInDB).filter(
            RoadmapStepInDB.id == step_id,
            RoadmapStepInDB.roadmap_id == roadmap_id
        ).first()
        
        if not step:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Step not found"
            )
        
        # Check if already marked complete
        progress = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == user.id,
            UserRoadmapProgress.step_id == step_id
        ).first()
        
        if progress:
            # Update existing progress
            progress.completed = True
            progress.completed_at = datetime.utcnow()
        else:
            # Create new progress entry
            progress = UserRoadmapProgress(
                user_id=user.id,
                step_id=step_id,
                completed=True,
                completed_at=datetime.utcnow()
            )
            db.add(progress)
        
        db.commit()
        
        return {"message": "Step marked as complete"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking step as complete: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark step as complete"
        )

@router.delete("/{roadmap_id}/steps/{step_id}/complete", status_code=status.HTTP_200_OK)
async def mark_step_incomplete(
    roadmap_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Mark a roadmap step as incomplete"""
    try:
        # Find progress entry
        progress = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == user.id,
            UserRoadmapProgress.step_id == step_id
        ).first()
        
        if not progress:
            return {"message": "Step is not marked as complete"}
        
        # Delete progress entry
        db.delete(progress)
        db.commit()
        
        return {"message": "Step marked as incomplete"}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking step as incomplete: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark step as incomplete"
        )

@router.get("/{roadmap_id}/progress", status_code=status.HTTP_200_OK)
async def get_roadmap_progress(
    roadmap_id: int,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user)
):
    """Get user's progress for a specific roadmap"""
    try:
        # Get all steps for the roadmap
        steps = db.query(RoadmapStepInDB).filter(
            RoadmapStepInDB.roadmap_id == roadmap_id
        ).all()
        
        if not steps:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roadmap not found or has no steps"
            )
        
        # Get completed steps
        completed = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == user.id,
            UserRoadmapProgress.step_id.in_([step.id for step in steps]),
            UserRoadmapProgress.completed == True
        ).all()
        
        completed_step_ids = [progress.step_id for progress in completed]
        
        # Calculate progress percentage
        progress_percent = int(len(completed) / len(steps) * 100) if steps else 0
        
        return {
            "total_steps": len(steps),
            "completed_steps": len(completed),
            "progress_percent": progress_percent,
            "completed_step_ids": completed_step_ids
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving roadmap progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roadmap progress"
        ) 