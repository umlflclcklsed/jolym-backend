from sqlalchemy import create_engine, text
from config import SQLALCHEMY_DATABASE_URL, init_db
import os
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    logger.info("Resetting database...")
    
    # Drop all tables
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    with engine.connect() as connection:
        # Drop all tables with CASCADE in a single SQL command
        connection.execute(text("DROP SCHEMA public CASCADE;"))
        connection.execute(text("CREATE SCHEMA public;"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        connection.commit()
    
    # Apply pgvector setup
    try:
        logger.info("Setting up pgvector extension...")
        script_path = os.path.join(os.path.dirname(__file__), 'setup_pgvector.sql')
        
        with open(script_path, 'r') as f:
            sql_commands = f.read()
        
        with engine.connect() as connection:
            connection.execute(text(sql_commands))
            connection.commit()
            logger.info("pgvector setup completed")
    except Exception as e:
        logger.error(f"Error setting up pgvector: {str(e)}", exc_info=True)
    
    # Recreate tables
    init_db()
    
    logger.info("Database reset successfully.")

if __name__ == "__main__":
    reset_database() 