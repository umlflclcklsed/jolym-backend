from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, ARRAY, PrimaryKeyConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

Base = declarative_base()

class PromptInDB(Base):
    __tablename__ = "prompts"
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, index=True)
    embedding = Column(ARRAY(Float))  # Временно храним embedding для поиска похожих промптов
    created_at = Column(DateTime, default=datetime.utcnow)
    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"), nullable=True)
    
    roadmap = relationship("RoadmapInDB", back_populates="prompt")

class UserInDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("UserInDB")


class RoadmapInDB(Base):
    __tablename__ = "roadmaps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    query_text = Column(String)  # Original query text used to generate this roadmap
    
    steps = relationship("RoadmapStepInDB", back_populates="roadmap", cascade="all, delete-orphan")
    prompt = relationship("PromptInDB", back_populates="roadmap", uselist=False)

class RoadmapStepInDB(Base):
    __tablename__ = "roadmap_steps"
    
    # Define columns first
    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"), nullable=False)
    id = Column(String, nullable=False) # Step ID like "1-1", "1-2"
    
    title = Column(String, index=True)
    description = Column(String)
    icon = Column(String)
    icon_color = Column(String)
    icon_bg = Column(String)
    time_to_complete = Column(String)
    difficulty = Column(Integer)
    tips = Column(String)
    
    # Define composite primary key
    __table_args__ = (
        PrimaryKeyConstraint('roadmap_id', 'id'),
        {},
    )
    
    roadmap = relationship("RoadmapInDB", back_populates="steps")
    resources = relationship("ResourceInDB", back_populates="step", cascade="all, delete-orphan")

class ResourceInDB(Base):
    __tablename__ = "resources"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String)
    source = Column(String)
    description = Column(String)
    
    # Foreign key columns referencing the composite key of roadmap_steps
    step_roadmap_id = Column(Integer, nullable=False)
    step_id = Column(String, nullable=False) 
    
    # Define composite foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ['step_roadmap_id', 'step_id'], 
            ['roadmap_steps.roadmap_id', 'roadmap_steps.id']
        ),
        {},
    )

    step = relationship("RoadmapStepInDB", back_populates="resources")

# Pydantic models for API requests/responses

class CreateUser(BaseModel):
    name: str
    email: str
    password: str

class CreateStudent(BaseModel):
    name: str
    email: str

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    type: str

class ResourceBase(BaseModel):
    title: str
    url: str
    source: str
    description: str

class ResourceCreate(ResourceBase):
    pass

class Resource(ResourceBase):
    id: int
    step_roadmap_id: int # Ensure Pydantic model includes the composite FK parts
    step_id: str
    
    class Config:
        from_attributes = True

class RoadmapStepBase(BaseModel):
    id: str # This is the step's string ID like "1-1"
    title: str
    description: str
    icon: str
    icon_color: str
    icon_bg: str
    time_to_complete: str
    difficulty: int
    tips: str

class RoadmapStepCreate(RoadmapStepBase):
    resources: List[ResourceCreate]

class RoadmapStep(RoadmapStepBase):
    roadmap_id: int # Include roadmap_id as part of the step identifier
    resources: List[Resource] = []
    
    class Config:
        from_attributes = True # Allows mapping from ORM model

class RoadmapBase(BaseModel):
    name: str
    description: str

class RoadmapCreate(RoadmapBase):
    steps: List[RoadmapStepCreate]

class Roadmap(RoadmapBase):
    id: int
    steps: List[RoadmapStep] = []
    
    class Config:
        from_attributes = True

class UserFavoriteRoadmap(Base):
    __tablename__ = "user_favorite_roadmaps"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"))
    
    user = relationship("UserInDB")
    roadmap = relationship("RoadmapInDB")

class UserRoadmapProgress(Base):
    __tablename__ = "user_roadmap_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    step_roadmap_id = Column(Integer) # References composite key
    step_id = Column(String)          # References composite key
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Define composite foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ['step_roadmap_id', 'step_id'], 
            ['roadmap_steps.roadmap_id', 'roadmap_steps.id']
        ),
        {},
    )
    
    user = relationship("UserInDB")
    # step = relationship("RoadmapStepInDB") # Check relationship if needed

# --- Dashboard Models --- 

class DashboardStepProgress(BaseModel):
    step_id: str
    completed: bool
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DashboardRoadmapItem(BaseModel):
    id: int
    name: str
    description: str
    total_steps: int
    completed_steps: int
    progress: List[DashboardStepProgress] # Progress for specific steps in this roadmap

    class Config:
        from_attributes = True # Allows mapping from ORM model if needed

class DashboardResponse(BaseModel):
    tracked_roadmaps: List[DashboardRoadmapItem]

# --- Roadmap Detail Models --- 

class RoadmapDetailStep(RoadmapStepBase): # Reuse base step info
    resources: List[Resource] = [] # Include resources for the step
    progress: Optional[DashboardStepProgress] = None # User's progress on this step

    class Config:
        from_attributes = True

class RoadmapDetailResponse(RoadmapBase):
    id: int
    steps: List[RoadmapDetailStep] = [] 

    class Config:
        from_attributes = True

# --- Progress Update Models --- 

class UpdateProgressRequest(BaseModel):
    step_id: str # The string ID of the step (e.g., "1-1")
    completed: bool # True to mark as completed, False to mark as incomplete

class ProgressUpdateResponse(DashboardStepProgress): # Reuse the progress model
    roadmap_id: int # Add roadmap_id for context
    
    class Config:
        from_attributes = True

# Password Reset Models
class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

class PasswordResetResponse(BaseModel):
    message: str
    success: bool
