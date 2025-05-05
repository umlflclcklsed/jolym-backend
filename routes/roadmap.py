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
from utils.embedding_utils import generate_embedding, cosine_similarity
from pydantic import BaseModel
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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
    """Создает новый промпт, генерирует его embedding и пытается создать roadmap"""
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
        
        # Пытаемся сгенерировать roadmap
        try:
            roadmap_data = generate_roadmap(prompt.text)
            if roadmap_data:
                # Создаем roadmap
                db_roadmap = RoadmapInDB(
                    name=roadmap_data.get("name", "Generated Roadmap"),
                    description=roadmap_data.get("description", ""),
                    embedding=embedding,  # Используем тот же embedding
                    embedding_text=prompt.text,
                    query_text=prompt.text
                )
                db.add(db_roadmap)
                db.commit()
                db.refresh(db_roadmap)
                
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
                logger.info(f"Successfully created roadmap from prompt: {prompt.text}")
            
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
    """Находит похожие промпты на основе косинусного сходства"""
    try:
        # Генерируем embedding для запроса
        query_embedding = generate_embedding(text)
        
        # Получаем все промпты
        prompts = db.query(PromptInDB).all()
        
        # Вычисляем сходство и сортируем
        similar_prompts = []
        for prompt in prompts:
            if prompt.embedding:
                similarity = cosine_similarity(query_embedding, prompt.embedding)
                if similarity >= threshold:
                    similar_prompts.append((prompt, similarity))
        
        # Сортируем по убыванию сходства и берем top-N
        similar_prompts.sort(key=lambda x: x[1], reverse=True)
        return [prompt for prompt, _ in similar_prompts[:limit]]
        
    except Exception as e:
        logger.error(f"Error finding similar prompts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find similar prompts"
        )

