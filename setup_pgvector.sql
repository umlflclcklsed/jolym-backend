-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create index on roadmaps embeddings column (execute after tables are created)
-- ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS embedding_idx vector(1536);
-- CREATE INDEX IF NOT EXISTS roadmaps_embedding_idx ON roadmaps USING ivfflat (embedding_idx vector_cosine_ops) WITH (lists = 100);

-- Create a function to calculate cosine similarity between two vectors
CREATE OR REPLACE FUNCTION cosine_similarity(a float[], b float[]) 
RETURNS float AS $$
DECLARE
  dot_product float := 0;
  norm_a float := 0;
  norm_b float := 0;
BEGIN
  -- Calculate dot product
  FOR i IN 1..array_length(a, 1) LOOP
    dot_product := dot_product + (a[i] * b[i]);
  END LOOP;
  
  -- Calculate magnitude of vector a
  FOR i IN 1..array_length(a, 1) LOOP
    norm_a := norm_a + (a[i] * a[i]);
  END LOOP;
  norm_a := sqrt(norm_a);
  
  -- Calculate magnitude of vector b
  FOR i IN 1..array_length(b, 1) LOOP
    norm_b := norm_b + (b[i] * b[i]);
  END LOOP;
  norm_b := sqrt(norm_b);
  
  -- Return cosine similarity
  IF norm_a = 0 OR norm_b = 0 THEN
    RETURN 0;
  ELSE
    RETURN dot_product / (norm_a * norm_b);
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Create a function to find similar roadmaps
CREATE OR REPLACE FUNCTION find_similar_roadmaps(query_embedding float[], similarity_threshold float)
RETURNS TABLE(id int, similarity float) AS $$
BEGIN
  RETURN QUERY
  SELECT r.id, cosine_similarity(r.embedding, query_embedding) as similarity
  FROM roadmaps r
  WHERE r.embedding IS NOT NULL
  AND cosine_similarity(r.embedding, query_embedding) > similarity_threshold
  ORDER BY similarity DESC;
END;
$$ LANGUAGE plpgsql; 