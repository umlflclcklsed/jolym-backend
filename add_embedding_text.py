from sqlalchemy import create_engine, text
from config import SQLALCHEMY_DATABASE_URL

def add_embedding_text_column():
    """
    Add embedding_text column to the roadmaps table.
    This is an alternative approach to using pgvector when vector extension is not available.
    """
    print("Connecting to database...")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    conn = engine.connect()
    
    try:
        print("Adding embedding_text column to roadmaps table...")
        conn.execute(text("ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS embedding_text TEXT"))
        conn.commit()
        print("Column embedding_text added successfully!")
    except Exception as e:
        print(f"Error adding column: {str(e)}")
        conn.rollback()
    finally:
        conn.close()
        print("Database connection closed")

if __name__ == "__main__":
    add_embedding_text_column() 