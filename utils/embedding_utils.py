import os
import requests
import logging
from typing import List, Optional, Dict, Union
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

class ClipEmbedder:
    def __init__(self):
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.deployment = "openai-clip-image-text-embed-11"
        
        if not all([self.endpoint, self.api_key, self.deployment]):
            logger.error("Missing required environment variables for CLIP API")
            raise ValueError("Missing required environment variables")
            
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "azureml-model-deployment": self.deployment
        }

    def get_text_embeddings(self, texts: List[str]) -> List[Dict]:
        """Получает эмбеддинги для списка текстов"""
        try:
            payload = {
                "input_data": {
                    "columns": ["image", "text"],
                    "index": list(range(len(texts))),
                    "data": [["", text] for text in texts]
                }
            }

            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=15
            )

            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"API Error: {str(e)}")
            raise

    def get_text_embedding(self, text: str) -> List[float]:
        """Получает эмбеддинг для одного текста"""
        try:
            results = self.get_text_embeddings([text])
            return results[0]['text_features']
        except Exception as e:
            logger.error(f"Error getting embedding for text: {str(e)}")
            return [0.0] * 512  # CLIP обычно возвращает 512-мерные векторы

# Глобальный экземпляр embedder
try:
    embedder = ClipEmbedder()
    EMBEDDINGS_SUPPORTED = True
except Exception as e:
    logger.error(f"Failed to initialize CLIP embedder: {str(e)}")
    embedder = None
    EMBEDDINGS_SUPPORTED = False

def generate_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector for the provided text using CLIP API.
    
    Args:
        text: The text to generate an embedding for
        
    Returns:
        A list of floats representing the embedding vector
    """
    if not EMBEDDINGS_SUPPORTED or not embedder:
        logger.warning("Embeddings are not supported, returning empty vector")
        return [0.0] * 512
        
    try:
        # Clean and prepare text
        text = text.replace("\n", " ").strip()
        
        # Generate embedding
        embedding = embedder.get_text_embedding(text)
        logger.info(f"Generated embedding with {len(embedding)} dimensions")
        
        return embedding
    
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}", exc_info=True)
        return [0.0] * 512

def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        Similarity score between 0 and 1 (1 = most similar)
    """
    if not embedding1 or not embedding2:
        return 0.0
    
    # Calculate dot product
    dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
    
    # Calculate magnitudes
    magnitude1 = sum(a * a for a in embedding1) ** 0.5
    magnitude2 = sum(b * b for b in embedding2) ** 0.5
    
    # Prevent division by zero
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    # Calculate cosine similarity
    similarity = dot_product / (magnitude1 * magnitude2)
    
    return similarity

def find_similar_roadmap(
    query_text: str, 
    db_session, 
    roadmap_model,
    similarity_threshold: float = 0.85
) -> Optional[int]:
    """
    Find a similar roadmap in the database based on embedding similarity.
    
    Args:
        query_text: The query text to find similar roadmaps for
        db_session: SQLAlchemy database session
        roadmap_model: The roadmap model class
        similarity_threshold: Threshold for considering roadmaps similar (default: 0.85)
        
    Returns:
        ID of the most similar roadmap if similarity is above threshold, else None
    """
    if not EMBEDDINGS_SUPPORTED:
        logger.warning("Embeddings are not supported, skipping similarity search")
        return None
        
    try:
        # Generate embedding for the query
        query_embedding = generate_embedding(query_text)
        
        # Query all roadmaps (in production, use pgvector for efficient similarity search)
        roadmaps = db_session.query(roadmap_model).all()
        
        best_similarity = 0.0
        best_roadmap_id = None
        
        # Calculate similarity with each roadmap
        for roadmap in roadmaps:
            if roadmap.embedding:
                similarity = cosine_similarity(query_embedding, roadmap.embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_roadmap_id = roadmap.id
        
        logger.info(f"Best similarity score: {best_similarity}")
        
        # Return the ID if similarity is above threshold
        if best_similarity >= similarity_threshold:
            return best_roadmap_id
        
        return None
    
    except Exception as e:
        logger.error(f"Error finding similar roadmap: {str(e)}", exc_info=True)
        return None 