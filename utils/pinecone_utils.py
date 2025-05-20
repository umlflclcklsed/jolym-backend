import os
import logging
import sys
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pinecone import Pinecone  

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Initializing Pinecone utils...")

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "roadmaps")

# Initialize Pinecone client and index
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)
    PINECONE_SUPPORTED = True
except Exception as e:
    logger.error(f"Failed to initialize Pinecone: {str(e)}")
    PINECONE_SUPPORTED = False
    pc = None
    index = None

def list_available_indexes() -> List[str]:
    """
    List all available indexes in your Pinecone account
    
    Returns:
        List of index names
    """
    if not PINECONE_SUPPORTED or pc is None:
        logger.warning("Pinecone not available, cannot list indexes")
        return []
        
    try:
        # Get list of all indexes
        indexes = pc.list_indexes()
        index_names = [index.name for index in indexes]
        return index_names
    except Exception as e:
        logger.error(f"Error listing Pinecone indexes: {str(e)}")
        return []

def store_roadmap_embedding(roadmap_id: int, embedding: List[float], metadata: Dict[str, Any]) -> bool:
    """
    Store roadmap embedding in Pinecone
    
    Args:
        roadmap_id: The ID of the roadmap
        embedding: Vector embedding of the roadmap
        metadata: Additional metadata (name, description, etc)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not PINECONE_SUPPORTED or index is None:
        logger.warning("Pinecone not available, skipping embedding storage")
        return False
    
    try:
        # Create vector ID
        vector_id = f"roadmap-{roadmap_id}"
        
        # Create vector with metadata
        vector = {
            "id": vector_id,
            "values": embedding,
            "metadata": metadata or {}
        }
        
        # Upsert the vector
        index.upsert(vectors=[vector])
        logger.info(f"Successfully stored embedding for roadmap ID: {roadmap_id}")
        return True
    except Exception as e:
        logger.error(f"Error storing embedding for roadmap ID {roadmap_id}: {str(e)}")
        return False

def find_similar_roadmap(query_embedding: List[float], threshold: float = 0.85) -> Optional[Dict]:
    """
    Find similar roadmap in Pinecone using vector similarity
    
    Args:
        query_embedding: The query embedding to compare against
        threshold: Minimum similarity threshold (0-1)
        
    Returns:
        Dict with metadata of most similar roadmap, or None if no match found
    """
    if not PINECONE_SUPPORTED or index is None:
        logger.warning("Pinecone not available, skipping similarity search")
        return None
    
    try:
        # Query Pinecone for similar vectors
        results = index.query(
            vector=query_embedding,
            top_k=3,
            include_metadata=True
        )
        
        # Check if we have matches above threshold
        if results.matches and len(results.matches) > 0 and results.matches[0].score >= threshold:
            matches = results.matches
            result = []

            for match in matches:
                result.append({
                "id": match.id,
                "score": match.score,
                "roadmap_id": match.metadata.get("roadmap_id"),
                "metadata": match.metadata
            })
            # logger.info(f"Found similar roadmap with ID: {match.metadata.get('roadmap_id')} (score: {match.score})")
            
            # Return the metadata
            return result 
        
        logger.info(f"No similar roadmaps found above threshold: {threshold}")
        return None
    except Exception as e:
        logger.error(f"Error searching for similar roadmap: {str(e)}")
        return None

def delete_roadmap_embedding(roadmap_id: int) -> bool:
    """
    Delete a roadmap embedding from Pinecone
    
    Args:
        roadmap_id: The ID of the roadmap to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not PINECONE_SUPPORTED or index is None:
        logger.warning("Pinecone not available, skipping embedding deletion")
        return False
    
    try:
        vector_id = f"roadmap-{roadmap_id}"
        index.delete(ids=[vector_id])
        logger.info(f"Successfully deleted embedding for roadmap ID: {roadmap_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting embedding for roadmap ID {roadmap_id}: {str(e)}")
        return False