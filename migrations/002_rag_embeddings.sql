-- RAG (Retrieval-Augmented Generation) Support
-- Enables semantic search over historical appraisals using vector embeddings
-- Run via Supabase SQL Editor

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings table to store vector embeddings for appraisals
CREATE TABLE IF NOT EXISTS appraisal_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appraisal_id UUID NOT NULL REFERENCES appraisals(id) ON DELETE CASCADE,
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL, -- 'metadata', 'notes', 'vision_summary', 'risk_flags'
    content_text TEXT NOT NULL,
    embedding vector(1536), -- OpenAI text-embedding-ada-002 dimension
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for vector similarity search using IVFFlat (Inverted File with Flat compression)
-- This enables fast approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS appraisal_embeddings_embedding_idx 
ON appraisal_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for fast lookups by appraisal_id
CREATE INDEX IF NOT EXISTS appraisal_embeddings_appraisal_id_idx 
ON appraisal_embeddings(appraisal_id);

-- Index for content type filtering
CREATE INDEX IF NOT EXISTS appraisal_embeddings_content_type_idx 
ON appraisal_embeddings(content_type);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS appraisal_embeddings_appraisal_type_idx 
ON appraisal_embeddings(appraisal_id, content_type);

-- Function for vector similarity search
-- This function performs cosine similarity search on embeddings
CREATE OR REPLACE FUNCTION match_appraisal_embeddings(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    content_types text[] DEFAULT ARRAY[]::text[]
)
RETURNS TABLE (
    id uuid,
    appraisal_id uuid,
    content_type text,
    content_text text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ae.id,
        ae.appraisal_id,
        ae.content_type,
        ae.content_text,
        1 - (ae.embedding <=> query_embedding) AS similarity
    FROM appraisal_embeddings ae
    WHERE 
        -- Filter by content types if provided
        (array_length(content_types, 1) IS NULL OR ae.content_type = ANY(content_types))
        -- Only return results above similarity threshold
        AND (1 - (ae.embedding <=> query_embedding)) >= match_threshold
    ORDER BY ae.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Enhanced function that includes appraisal outcomes (for better RAG context)
CREATE OR REPLACE FUNCTION match_appraisals_with_outcomes(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    content_types text[] DEFAULT ARRAY[]::text[]
)
RETURNS TABLE (
    appraisal_id uuid,
    appraisal_short_id text,
    content_type text,
    content_text text,
    similarity float,
    metadata_json jsonb,
    latest_run_outputs jsonb,
    latest_run_status text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (ae.appraisal_id)
        ae.appraisal_id,
        a.short_id AS appraisal_short_id,
        ae.content_type,
        ae.content_text,
        1 - (ae.embedding <=> query_embedding) AS similarity,
        a.metadata_json,
        pr.outputs_json AS latest_run_outputs,
        pr.status AS latest_run_status
    FROM appraisal_embeddings ae
    JOIN appraisals a ON ae.appraisal_id = a.id
    LEFT JOIN pipeline_runs pr ON a.latest_run_id = pr.id
    WHERE 
        -- Filter by content types if provided
        (array_length(content_types, 1) IS NULL OR ae.content_type = ANY(content_types))
        -- Only return results above similarity threshold
        AND (1 - (ae.embedding <=> query_embedding)) >= match_threshold
    ORDER BY ae.appraisal_id, ae.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Add comment for documentation
COMMENT ON TABLE appraisal_embeddings IS 'Stores vector embeddings for semantic search over historical appraisals';
COMMENT ON FUNCTION match_appraisal_embeddings IS 'Performs cosine similarity search on appraisal embeddings';
