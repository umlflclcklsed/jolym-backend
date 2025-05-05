from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload as orm_selectinload
from sqlalchemy import func
import logging
from typing import List, Optional
from datetime import datetime

from config import get_db
from schemas.models import (
    UserInDB,
    RoadmapInDB,
    RoadmapStepInDB,
    UserFavoriteRoadmap,
    UserRoadmapProgress,
    DashboardResponse,
    DashboardRoadmapItem,
    DashboardStepProgress,
    RoadmapDetailResponse,
    RoadmapDetailStep,
    Resource,
    UpdateProgressRequest,
    ProgressUpdateResponse
)
from auth_utils import verify_access_token # Assuming get_current_user is based on this
from routes.roadmap import get_current_user # Import the dependency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/me", response_model=DashboardResponse)
async def get_user_dashboard(
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Получает данные для дашборда текущего пользователя (избранные роадмапы и прогресс)."""
    try:
        # 1. Найти избранные роадмапы пользователя
        favorite_associations = db.query(UserFavoriteRoadmap).filter(
            UserFavoriteRoadmap.user_id == current_user.id
        ).all()
        
        if not favorite_associations:
            return DashboardResponse(tracked_roadmaps=[])
            
        favorite_roadmap_ids = [fav.roadmap_id for fav in favorite_associations]

        # 2. Получить детали этих роадмапов
        favorite_roadmaps = db.query(RoadmapInDB).filter(
            RoadmapInDB.id.in_(favorite_roadmap_ids)
        ).all()
        
        # 3. Получить ВЕСЬ прогресс пользователя по ВСЕМ шагам
        # Оптимизация: Загружаем весь прогресс один раз
        user_progress_all = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == current_user.id
        ).all()
        
        # Преобразуем прогресс в словарь для быстрого доступа: {(roadmap_id, step_id): progress_obj}
        progress_map = {
            (progress.step_roadmap_id, progress.step_id): progress 
            for progress in user_progress_all
        }
        
        dashboard_items = []
        for roadmap in favorite_roadmaps:
            # 4. Получить шаги для каждого избранного роадмапа
            steps = db.query(RoadmapStepInDB).filter(
                RoadmapStepInDB.roadmap_id == roadmap.id
            ).all()
            
            total_steps = len(steps)
            completed_steps_count = 0
            step_progress_list = []
            
            # 5. Собрать прогресс для шагов ЭТОГО роадмапа
            for step in steps:
                progress_record = progress_map.get((roadmap.id, step.id))
                if progress_record:
                    step_prog = DashboardStepProgress.model_validate(progress_record)
                    step_progress_list.append(step_prog)
                    if step_prog.completed:
                        completed_steps_count += 1
                else:
                     # Если записи прогресса нет, считаем шаг не пройденным
                     step_progress_list.append(DashboardStepProgress(step_id=step.id, completed=False))
            
            dashboard_items.append(
                DashboardRoadmapItem(
                    id=roadmap.id,
                    name=roadmap.name,
                    description=roadmap.description,
                    total_steps=total_steps,
                    completed_steps=completed_steps_count,
                    progress=step_progress_list
                )
            )
            
        return DashboardResponse(tracked_roadmaps=dashboard_items)
        
    except Exception as e:
        logger.error(f"Error fetching dashboard data for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard data"
        )

@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapDetailResponse)
async def get_roadmap_details_with_progress(
    roadmap_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Получает детальную информацию о роадмапе и прогресс пользователя по его шагам."""
    try:
        # 1. Найти роадмап по ID
        roadmap = db.query(RoadmapInDB).filter(RoadmapInDB.id == roadmap_id).first()
        if not roadmap:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")

        # 2. Получить все шаги для этого роадмапа, включая ресурсы
        steps = db.query(RoadmapStepInDB).filter(
            RoadmapStepInDB.roadmap_id == roadmap_id
        ).options(
            # Eager load resources to avoid N+1 query problem
            orm_selectinload(RoadmapStepInDB.resources)
        ).all()

        # 3. Получить прогресс пользователя ТОЛЬКО для шагов этого роадмапа
        user_progress_specific = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == current_user.id,
            UserRoadmapProgress.step_roadmap_id == roadmap_id
        ).all()

        # Создать словарь прогресса для быстрого доступа по step_id
        progress_map = {progress.step_id: progress for progress in user_progress_specific}

        # 4. Сформировать ответ
        detailed_steps = []
        for step in steps:
            step_progress_record = progress_map.get(step.id)
            step_progress_data: Optional[DashboardStepProgress] = None
            if step_progress_record:
                step_progress_data = DashboardStepProgress.model_validate(step_progress_record)
            
            # Важно: используем `Resource.model_validate` для каждого ресурса
            validated_resources = [Resource.model_validate(res) for res in step.resources]

            detailed_steps.append(
                RoadmapDetailStep(
                    id=step.id,
                    title=step.title,
                    description=step.description,
                    icon=step.icon,
                    icon_color=step.icon_color,
                    icon_bg=step.icon_bg,
                    time_to_complete=step.time_to_complete,
                    difficulty=step.difficulty,
                    tips=step.tips,
                    resources=validated_resources,
                    progress=step_progress_data
                )
            )
        
        return RoadmapDetailResponse(
            id=roadmap.id,
            name=roadmap.name,
            description=roadmap.description,
            steps=detailed_steps
        )

    except HTTPException as he: # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Error fetching details for roadmap {roadmap_id} for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch roadmap details"
        )

@router.post("/roadmaps/{roadmap_id}/progress", response_model=ProgressUpdateResponse)
async def update_step_progress(
    roadmap_id: int,
    progress_update: UpdateProgressRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Обновляет статус прохождения конкретного шага роадмапа для пользователя."""
    try:
        # 1. Проверить, существует ли такой шаг в указанном роадмапе
        step_exists = db.query(RoadmapStepInDB).filter(
            RoadmapStepInDB.roadmap_id == roadmap_id,
            RoadmapStepInDB.id == progress_update.step_id
        ).first()
        
        if not step_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{progress_update.step_id}' not found in roadmap '{roadmap_id}'"
            )

        # 2. Найти или создать запись о прогрессе для этого пользователя и шага
        progress_record = db.query(UserRoadmapProgress).filter(
            UserRoadmapProgress.user_id == current_user.id,
            UserRoadmapProgress.step_roadmap_id == roadmap_id,
            UserRoadmapProgress.step_id == progress_update.step_id
        ).first()

        current_time = datetime.utcnow()

        if progress_record:
            # Обновить существующую запись
            progress_record.completed = progress_update.completed
            progress_record.completed_at = current_time if progress_update.completed else None
            logger.info(f"Updating progress for user {current_user.id}, roadmap {roadmap_id}, step {progress_update.step_id} to completed={progress_update.completed}")
        else:
            # Создать новую запись
            progress_record = UserRoadmapProgress(
                user_id=current_user.id,
                step_roadmap_id=roadmap_id,
                step_id=progress_update.step_id,
                completed=progress_update.completed,
                completed_at = current_time if progress_update.completed else None
            )
            db.add(progress_record)
            logger.info(f"Creating new progress record for user {current_user.id}, roadmap {roadmap_id}, step {progress_update.step_id} with completed={progress_update.completed}")

        # 3. Сохранить изменения
        db.commit()
        db.refresh(progress_record)

        # 4. Вернуть обновленную запись прогресса (немного дополненную для контекста)
        # Так как ProgressUpdateResponse наследует от DashboardStepProgress, 
        # нужно добавить roadmap_id для полного соответствия
        response_data = ProgressUpdateResponse(
            roadmap_id=progress_record.step_roadmap_id, 
            step_id=progress_record.step_id, 
            completed=progress_record.completed, 
            completed_at=progress_record.completed_at
        )
        return response_data

    except HTTPException as he:
        db.rollback() # Откатываем транзакцию при HTTP ошибках, вызванных нами
        raise he
    except Exception as e:
        db.rollback() # Откатываем транзакцию при любых других ошибках
        logger.error(f"Error updating progress for user {current_user.id}, roadmap {roadmap_id}, step {progress_update.step_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update progress"
        )
