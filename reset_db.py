from sqlalchemy import create_engine, text
from config import SQLALCHEMY_DATABASE_URL, init_db
import os
import logging
from pinecone import Pinecone
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    logger.info("Resetting PostgreSQL database...")
    
    # Drop all tables and recreate schema
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    try:
        with engine.connect() as connection:
            logger.info("Dropping public schema...")
            connection.execute(text("DROP SCHEMA public CASCADE;"))
            connection.commit()
            logger.info("Recreating public schema...")
            connection.execute(text("CREATE SCHEMA public;"))
            # Optional: Grant permissions if needed, adjust user/role as necessary
            # connection.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
            # connection.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            connection.commit()
            logger.info("Schema reset complete.")
    except Exception as e:
        logger.error(f"Error dropping/creating schema: {str(e)}", exc_info=True)
        # Decide if you want to proceed or stop if schema reset fails
        # return # Optional: stop here if schema reset fails

    # Recreate tables based on SQLAlchemy models
    try:
        logger.info("Recreating tables from models...")
        init_db() # This should call Base.metadata.create_all(engine)
        logger.info("Tables recreated successfully.")
    except Exception as e:
        logger.error(f"Error recreating tables: {str(e)}", exc_info=True)

def reset_pinecone():
    logger.info("Resetting Pinecone index...")
    load_dotenv()
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "roadmaps")

    if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
        logger.warning("Pinecone API Key or Index Name not configured. Skipping Pinecone reset.")
        return

    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        logger.info(f"Checking if index '{PINECONE_INDEX_NAME}' exists...")
        if PINECONE_INDEX_NAME in [idx.name for idx in pc.list_indexes()]:
            index = pc.Index(PINECONE_INDEX_NAME)
            logger.info(f"Deleting all vectors from index '{PINECONE_INDEX_NAME}'...")
            try:
                # Attempt to delete all vectors
                index.delete(delete_all=True) 
                logger.info("Deletion complete.")
            except Exception as delete_err:
                logger.error(f"Failed to delete all vectors: {delete_err}. Manual deletion might be required.")
        else:
            logger.info(f"Index '{PINECONE_INDEX_NAME}' not found. No vectors to delete.")
    except Exception as e:
        logger.error(f"An error occurred during Pinecone reset: {str(e)}", exc_info=True)

if __name__ == "__main__":
    reset_database()
    reset_pinecone() 