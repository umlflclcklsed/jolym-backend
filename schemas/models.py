from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSON, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

Base = declarative_base()

class UserInDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)


class RoadmapInDB(Base):
    __tablename__ = "roadmaps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    embedding = Column(ARRAY(Float))  # Vector embedding from OpenAI
    query_text = Column(String)  # Original query text used to generate this roadmap
    
    steps = relationship("RoadmapStepInDB", back_populates="roadmap")

class RoadmapStepInDB(Base):
    __tablename__ = "roadmap_steps"
    
    id = Column(String, primary_key=True)  # Using string ID like "1-1" from example
    title = Column(String, index=True)
    description = Column(String)
    icon = Column(String)
    icon_color = Column(String)
    icon_bg = Column(String)
    time_to_complete = Column(String)
    difficulty = Column(Integer)
    tips = Column(String)
    
    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"))
    roadmap = relationship("RoadmapInDB", back_populates="steps")
    
    resources = relationship("ResourceInDB", back_populates="step")

class ResourceInDB(Base):
    __tablename__ = "resources"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String)
    source = Column(String)
    description = Column(String)
    
    step_id = Column(String, ForeignKey("roadmap_steps.id"))
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
    step_id: str
    
    class Config:
        from_attributes = True

class RoadmapStepBase(BaseModel):
    id: str
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
    roadmap_id: int
    resources: List[Resource] = []
    
    class Config:
        from_attributes = True

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
    step_id = Column(String, ForeignKey("roadmap_steps.id"))
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("UserInDB")
    step = relationship("RoadmapStepInDB")
