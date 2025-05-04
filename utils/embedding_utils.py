import os
import openai
import logging
from typing import List, Optional

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag to indicate if embeddings are supported
EMBEDDINGS_SUPPORTED = True

# Azure OpenAI configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "text-embedding-ada-002")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

# Configure Azure OpenAI client
client = None
try:
    from openai import AzureOpenAI
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        logger.info("Azure OpenAI client initialized successfully")
    else:
        logger.warning("Azure OpenAI credentials not found. Embeddings will be disabled.")
        EMBEDDINGS_SUPPORTED = False
except ImportError:
    logger.warning("OpenAI module not installed. Embeddings will be disabled.")
    EMBEDDINGS_SUPPORTED = False
except Exception as e:
    logger.error(f"Error initializing Azure OpenAI client: {str(e)}")
    EMBEDDINGS_SUPPORTED = False

# Model configurations
EMBEDDING_DIMENSIONS = 1536  # Dimensions for text embeddings

def generate_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector for the provided text using Azure OpenAI.
    
    Args:
        text: The text to generate an embedding for
        
    Returns:
        A list of floats representing the embedding vector
    """
    if not EMBEDDINGS_SUPPORTED or not client:
        logger.warning("Embeddings are not supported, returning empty vector")
        return [0.0] * EMBEDDING_DIMENSIONS
        
    try:
        # Clean and prepare text
        text = text.replace("\n", " ").strip()
        
        # Generate embedding using Azure OpenAI
        response = client.embeddings.create(
            input=[text],
            deployment_id=AZURE_OPENAI_DEPLOYMENT_NAME
        )
        
        # Extract embedding vector
        embedding = response.data[0].embedding
        logger.info(f"Generated embedding with {len(embedding)} dimensions")
        
        return embedding
    
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}", exc_info=True)
        # Return empty vector as fallback
        return [0.0] * EMBEDDING_DIMENSIONS

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