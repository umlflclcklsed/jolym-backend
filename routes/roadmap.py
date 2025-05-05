from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging
from sqlalchemy.exc import IntegrityError
from auth_utils import verify_access_token
from fastapi.security import OAuth2PasswordBearer
from config import get_db
from schemas.models import *
from typing import List, Optional
from utils.ai_roadmap_generator import generate_roadmap
from utils.embedding_utils import generate_embedding
# Import Pinecone utilities with better error handling
import importlib.util
import sys
from pydantic import BaseModel
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

# Try to import Pinecone utilities
try:
    if importlib.util.find_spec("pinecone") is not None:
        from utils.pinecone_utils import store_roadmap_embedding, find_similar_roadmap, PINECONE_SUPPORTED, list_available_indexes
        logger.info("Successfully imported Pinecone utilities")
    else:
        logger.warning("Pinecone package not found, similarity search will be disabled")
        store_roadmap_embedding = lambda *args, **kwargs: False
        find_similar_roadmap = lambda *args, **kwargs: None
        list_available_indexes = lambda: []
        PINECONE_SUPPORTED = False
except ImportError as e:
    logger.warning(f"Failed to import Pinecone utilities: {str(e)}")
    store_roadmap_embedding = lambda *args, **kwargs: False
    find_similar_roadmap = lambda *args, **kwargs: None
    list_available_indexes = lambda: []
    PINECONE_SUPPORTED = False

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Получает текущего пользователя по токену"""
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
    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

class PromptRequest(BaseModel):
    text: str

class PromptResponse(BaseModel):
    id: int
    text: str
    created_at: datetime
    roadmap_id: Optional[int] = None

    class Config:
        from_attributes = True

@router.post("/prompt", response_model=PromptResponse)
async def create_prompt(
    prompt: PromptRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Создает новый промпт и генерирует roadmap, если похожего еще нет в базе"""
    try:
        # Генерируем embedding для промпта
        embedding = generate_embedding(prompt.text)
        
        # Создаем запись промпта
        db_prompt = PromptInDB(
            text=prompt.text,
            embedding=embedding
        )
        db.add(db_prompt)
        db.commit()
        db.refresh(db_prompt)
        
        # Проверяем наличие похожих roadmap в Pinecone
        similar_roadmap = None
        if PINECONE_SUPPORTED:
            similar_result = find_similar_roadmap(
                query_embedding=embedding,
                threshold=0.85
            )
            
            if similar_result and 'roadmap_id' in similar_result.get('metadata', {}):
                roadmap_id = int(similar_result['metadata']['roadmap_id'])
                similar_roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
                
                if similar_roadmap:
                    # Связываем промпт с существующим roadmap
                    db_prompt.roadmap_id = similar_roadmap.id
                    db.commit()
                    logger.info(f"Found similar roadmap and reused it: {similar_roadmap.id}")
                    return db_prompt
        
        # Если похожий roadmap не найден, генерируем новый
        try:
            roadmap_data = generate_roadmap(prompt.text)
            if roadmap_data:
                # Создаем roadmap
                db_roadmap = RoadmapInDB(
                    name=roadmap_data.get("name", "Generated Roadmap"),
                    description=roadmap_data.get("description", ""),
                    query_text=prompt.text
                )
                db.add(db_roadmap)
                db.commit()
                db.refresh(db_roadmap)
                
                # Сохраняем embedding в Pinecone
                if PINECONE_SUPPORTED:
                    # Add roadmap metadata for easier retrieval
                    roadmap_metadata = {
                        "roadmap_id": db_roadmap.id,
                        "name": db_roadmap.name,
                        "description": db_roadmap.description,
                        "query": prompt.text
                    }
                    
                    try:
                        store_roadmap_embedding(
                            roadmap_id=db_roadmap.id,
                            embedding=embedding,
                            metadata=roadmap_metadata
                        )
                        logger.info(f"Successfully stored roadmap embedding in Pinecone for roadmap ID: {db_roadmap.id}")
                    except Exception as e:
                        logger.error(f"Failed to store embedding in Pinecone: {str(e)}")
                        # Continue even if Pinecone storage fails
                
                # Связываем промпт с roadmap
                db_prompt.roadmap_id = db_roadmap.id
                db.commit()
                
                # Создаем шаги для roadmap
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
                    
                    # Создаем ресурсы для этого шага
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
                logger.info(f"Successfully created new roadmap from prompt: {prompt.text}")
            
        except Exception as e:
            logger.error(f"Error generating roadmap: {str(e)}")
            # Продолжаем выполнение даже если не удалось создать roadmap
        
        return db_prompt
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing prompt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process prompt"
        )

@router.get("/prompts/similar", response_model=List[PromptResponse])
async def find_similar_prompts(
    text: str,
    limit: int = 5,
    threshold: float = 0.7,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Находит похожие промпты, используя Pinecone для поиска"""
    try:
        query_embedding = generate_embedding(text)
        
        if PINECONE_SUPPORTED:
            # Ищем похожие roadmap в Pinecone
            similar_result = find_similar_roadmap(
                query_embedding=query_embedding,
                threshold=threshold
            )
            
            if similar_result and 'roadmap_id' in similar_result.get('metadata', {}):
                roadmap_id = int(similar_result['metadata']['roadmap_id'])
                # Получаем промпты, связанные с найденным roadmap
                prompts = db.query(PromptInDB).filter(PromptInDB.roadmap_id == roadmap_id).all()
                return prompts
        
        # Если Pinecone недоступен или нет результатов, возвращаем пустой список
        return []
        
    except Exception as e:
        logger.error(f"Error finding similar prompts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find similar prompts"
        )

@router.get("/health")
async def health_check():
    return {"status": "ok"}

# Add a new endpoint for Pinecone info and indexes
@router.get("/pinecone/indexes")
async def get_pinecone_indexes(
    current_user: UserInDB = Depends(get_current_user)
):
    """Возвращает список доступных индексов Pinecone"""
    try:
        indexes = list_available_indexes()
        return {
            "pinecone_supported": PINECONE_SUPPORTED,
            "indexes": indexes
        }
    except Exception as e:
        logger.error(f"Error getting Pinecone indexes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Pinecone indexes"
        )