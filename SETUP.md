# Setup Instructions

## Environment Variables

### Backend Environment Variables (`backend/.env`)

Update these variables with your new Supabase project credentials:

```bash
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
SUPABASE_STORAGE_BUCKET=appraisal-artifacts

OPENAI_API_KEY=your-openai-api-key
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_TEXT_MODEL=gpt-4o-mini
OPENAI_REQUEST_TIMEOUT_SECONDS=60

ENABLE_RAG=true

PORT=8000
SIGNED_URL_EXPIRATION=3600
CORS_ORIGINS=

AGENT_MAX_ITERATIONS=50
AGENT_EXECUTION_TIMEOUT_SECONDS=300
```

**Where to find Supabase credentials:**
1. Go to your Supabase project dashboard
2. Click **Settings** → **API**
3. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role key** (secret) → `SUPABASE_SERVICE_ROLE_KEY`

### Frontend Environment Variables (`frontend/.env`)

```bash
API_BASE_URL=http://localhost:8001
API_TIMEOUT_SECONDS=60
```

**Note**: For local Docker testing, use `http://localhost:8001` (port 8001, not 8000).

## Supabase Database Setup

### Step 1: Access Supabase SQL Editor

1. Go to your Supabase project dashboard: https://supabase.com/dashboard
2. Navigate to **SQL Editor** in the left sidebar
3. Click **New Query**

### Step 2: Run Database Migrations

Run these migrations **in order**:

#### Migration 1: Core Schema (`migrations/001_core.sql`)

```sql
-- Core schema for Vehicle Appraisal Pre-Check System
-- Enable UUID generation
create extension if not exists "pgcrypto";

-- appraisals
create table if not exists appraisals (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    metadata_json jsonb not null,
    notes_raw text,
    latest_run_id uuid,
    short_id text unique
);

-- pipeline_runs
create table if not exists pipeline_runs (
    id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisals(id),
    status text not null check (status in ('PENDING','RUNNING','COMPLETED','FAILED')),
    idempotency_key text unique,
    outputs_version text not null default 'v1',
    outputs_json jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

-- back-reference from appraisals.latest_run_id to pipeline_runs
alter table appraisals
    add constraint appraisals_latest_run_fk
    foreign key (latest_run_id) references pipeline_runs(id);

-- ledger_events (append-only)
create table if not exists ledger_events (
    id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisals(id),
    pipeline_run_id uuid not null references pipeline_runs(id),
    node_name text not null,
    schema_version text not null,
    input_refs jsonb not null default '{}'::jsonb,
    output jsonb,
    confidence_summary jsonb,
    status text not null check (status in ('ok','fail')),
    error text,
    timestamp timestamptz not null default now()
);

create index if not exists idx_ledger_events_appraisal_run_ts
    on ledger_events (appraisal_id, pipeline_run_id, timestamp);

-- artifacts (photos)
create table if not exists artifacts (
    id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisals(id),
    storage_path text not null,
    content_type text not null,
    size_bytes integer not null,
    vision_output_json jsonb,
    vision_extraction_status text,
    created_at timestamptz not null default now()
);

create index if not exists idx_artifacts_appraisal_id
    on artifacts (appraisal_id);
```

#### Migration 2: RAG Embeddings (`migrations/002_rag_embeddings.sql`)

```sql
-- RAG (Retrieval-Augmented Generation) support
-- Enable pgvector extension for vector similarity search
create extension if not exists vector;

-- appraisal_embeddings table for storing embeddings
create table if not exists appraisal_embeddings (
    id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisals(id),
    pipeline_run_id uuid references pipeline_runs(id),
    content_type text not null,  -- 'metadata', 'notes', 'vision_summary', 'risk_flags'
    content_text text not null,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    created_at timestamptz not null default now()
);

create index if not exists idx_appraisal_embeddings_appraisal_id
    on appraisal_embeddings (appraisal_id);

-- Vector similarity search index (HNSW for fast approximate search)
create index if not exists idx_appraisal_embeddings_embedding_hnsw
    on appraisal_embeddings
    using hnsw (embedding vector_cosine_ops);

-- Function for similarity search
create or replace function match_appraisal_embeddings(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    content_types text[] default null
)
returns table (
    id uuid,
    appraisal_id uuid,
    content_type text,
    content_text text,
    similarity float,
    metadata_json jsonb
)
language plpgsql
as $$
begin
    return query
    select
        ae.id,
        ae.appraisal_id,
        ae.content_type,
        ae.content_text,
        1 - (ae.embedding <=> query_embedding) as similarity,
        a.metadata_json
    from appraisal_embeddings ae
    join appraisals a on a.id = ae.appraisal_id
    where
        (content_types is null or ae.content_type = any(content_types))
        and 1 - (ae.embedding <=> query_embedding) >= match_threshold
    order by ae.embedding <=> query_embedding
    limit match_count;
end;
$$;

-- Enhanced function with historical outcomes
create or replace function match_appraisals_with_outcomes(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    content_types text[] default null
)
returns table (
    id uuid,
    appraisal_id uuid,
    content_type text,
    content_text text,
    similarity float,
    metadata_json jsonb,
    latest_run_outputs jsonb
)
language plpgsql
as $$
begin
    return query
    select
        ae.id,
        ae.appraisal_id,
        ae.content_type,
        ae.content_text,
        1 - (ae.embedding <=> query_embedding) as similarity,
        a.metadata_json,
        pr.outputs_json as latest_run_outputs
    from appraisal_embeddings ae
    join appraisals a on a.id = ae.appraisal_id
    left join pipeline_runs pr on pr.id = a.latest_run_id
    where
        (content_types is null or ae.content_type = any(content_types))
        and 1 - (ae.embedding <=> query_embedding) >= match_threshold
    order by ae.embedding <=> query_embedding
    limit match_count;
end;
$$;
```

#### Migration 3: Short IDs (`migrations/003_short_ids.sql`)

```sql
-- Short ID support (4-character alphanumeric IDs for user-friendly references)
-- Function to generate short IDs
create or replace function generate_short_id()
returns text
language plpgsql
as $$
declare
    chars text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';  -- Excludes I, O, 0, 1 for clarity
    result text := '';
    i int;
    random_char text;
begin
    for i in 1..4 loop
        random_char := substr(chars, floor(random() * length(chars) + 1)::int, 1);
        result := result || random_char;
    end loop;
    
    -- Check if ID already exists, regenerate if needed
    while exists (select 1 from appraisals where short_id = result) loop
        result := '';
        for i in 1..4 loop
            random_char := substr(chars, floor(random() * length(chars) + 1)::int, 1);
            result := result || random_char;
        end loop;
    end loop;
    
    return result;
end;
$$;

-- Add short_id column if it doesn't exist (already added in 001_core.sql, but safe to run)
do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_name = 'appraisals' and column_name = 'short_id'
    ) then
        alter table appraisals add column short_id text unique;
    end if;
end $$;

-- Create index on short_id for fast lookups
create index if not exists idx_appraisals_short_id
    on appraisals (short_id);
```

### Step 3: Create Storage Bucket

1. Go to **Storage** in Supabase dashboard
2. Click **New bucket**
3. Name: `appraisal-artifacts`
4. Set as **Public bucket**: No (private)
5. Click **Create bucket**

### Step 4: Set Storage Policies (Optional but Recommended)

For the `appraisal-artifacts` bucket, you can set policies in **Storage** → **Policies**:

- **Upload policy**: Allow service role to upload
- **Download policy**: Allow authenticated users or specific conditions

Since we're using service role key, the default policies should work, but you can customize as needed.

## Local Testing with Docker

### Start Services

```bash
cd vehicle-appraisal-app
docker-compose up -d
```

This will start:
- **API**: http://localhost:8001
- **UI**: http://localhost:8502

### Check Service Health

```bash
# API health check
curl http://localhost:8001/healthz

# API readiness check (checks Supabase, OpenAI, RAG)
curl http://localhost:8001/readyz

# View logs
docker-compose logs -f api
docker-compose logs -f ui
```

### Stop Services

```bash
docker-compose down
```

### Rebuild After Code Changes

```bash
docker-compose build
docker-compose up -d
```

## Testing the Application

1. **Open the UI**: http://localhost:8502
2. **Create an appraisal**:
   - Go to "Submit Appraisal"
   - Enter vehicle details (year, make, model)
   - Upload 1-3 photos
   - Click "Start AI Analysis"
3. **View results**:
   - Wait ~2 minutes for analysis
   - Go to "View Appraisal"
   - Enter the 4-character reference ID
   - View readiness score, risk flags, and evidence breakdown

## Troubleshooting

### API shows "degraded" status

- Check Supabase connection: Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env`
- Ensure migrations have been run in Supabase SQL Editor
- Check API logs: `docker-compose logs api`

### Photos not uploading

- Verify storage bucket `appraisal-artifacts` exists in Supabase
- Check storage policies allow service role access
- Check API logs for storage errors

### RAG not working

- Verify `ENABLE_RAG=true` in `backend/.env`
- Check that `pgvector` extension is enabled in Supabase
- Verify migration `002_rag_embeddings.sql` was run successfully
- RAG will gracefully degrade if unavailable (check logs)

### Agent execution fails

- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI API quota/limits
- Review agent logs in pipeline run outputs
- Check `AGENT_MAX_ITERATIONS` and `AGENT_EXECUTION_TIMEOUT_SECONDS` settings

## Next Steps

Once local testing is successful:

1. **Deploy to Render.com**:
   - Push code to GitHub
   - Connect repository to Render
   - Use `render.yaml` blueprint
   - Set environment variables in Render dashboard

2. **Update CORS settings**:
   - Set `CORS_ORIGINS` in Render to your UI service URL
   - Or use the `fromService` reference in `render.yaml`

3. **Monitor**:
   - Check Render service logs
   - Monitor Supabase database usage
   - Track OpenAI API usage
