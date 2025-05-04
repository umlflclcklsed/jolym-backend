import os
import json
import logging
from typing import Dict, List, Any, Optional

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Azure OpenAI configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_CHAT", "gpt-4")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

# Configure Azure OpenAI client
client = None
AI_GENERATION_SUPPORTED = True
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
        logger.warning("Azure OpenAI credentials not found. AI generation will be disabled.")
        AI_GENERATION_SUPPORTED = False
except ImportError:
    logger.warning("OpenAI module not installed. AI generation will be disabled.")
    AI_GENERATION_SUPPORTED = False
except Exception as e:
    logger.error(f"Error initializing Azure OpenAI client: {str(e)}")
    AI_GENERATION_SUPPORTED = False

def generate_roadmap(query: str) -> Optional[Dict[str, Any]]:
    """
    Generate a learning roadmap based on a user query using Azure OpenAI.
    
    Args:
        query: User's query text (e.g., "How to become a backend developer")
        
    Returns:
        A dictionary containing the generated roadmap or None if generation failed
    """
    if not AI_GENERATION_SUPPORTED or not client:
        logger.warning("AI generation is not supported, returning None")
        return None
        
    try:
        logger.info(f"Generating roadmap for query: {query}")
        
        # System message with instructions for roadmap generation
        system_message = """
        You are an expert in creating educational roadmaps for various fields.
        Generate a comprehensive learning roadmap in JSON format based on the user's query.
        
        The roadmap should follow this structure:
        {
            "name": "Title of the roadmap",
            "description": "Description of what this roadmap covers",
            "steps": [
                {
                    "id": "1-1", // Format: "section-number"
                    "title": "Step title",
                    "description": "Detailed description of this step",
                    "icon": "Icon name",
                    "iconColor": "text-blue-600",
                    "iconBg": "bg-blue-100",
                    "timeToComplete": "Estimated time (e.g., 2-4 weeks)",
                    "difficulty": 1, // 1 = beginner, 2 = intermediate, 3 = advanced
                    "resources": [
                        {
                            "title": "Resource title",
                            "url": "URL to the resource",
                            "source": "Source name",
                            "description": "Brief description of the resource"
                        }
                    ],
                    "tips": "Helpful tips for completing this step"
                }
            ]
        }
        
        Include 3-5 steps per section, with each step having 2-3 resources.
        For icons, select from this list: Code, Server, Database, Globe, Terminal, Cpu, Cloud, Lock
        Make sure all JSON is properly formatted and valid.
        Only return the JSON object, with no additional text or comments.
        """
        
        # Generate roadmap using Azure OpenAI Chat API
        response = client.chat.completions.create(
            deployment_id=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": query}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        
        # Extract and parse the generated content
        content = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        roadmap_data = json.loads(content)
        
        logger.info(f"Successfully generated roadmap with {len(roadmap_data.get('steps', []))} steps")
        return roadmap_data
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error generating roadmap: {str(e)}", exc_info=True)
        return None 