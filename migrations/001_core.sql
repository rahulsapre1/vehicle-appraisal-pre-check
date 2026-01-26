-- Core schema for Vehicle Appraisal Pre-Check System
-- Run via Supabase SQL Editor

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- appraisals
create table if not exists appraisals (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    metadata_json jsonb not null,
    notes_raw text,
    latest_run_id uuid
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

-- artifacts (storage metadata)
create table if not exists artifacts (
    id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisals(id),
    storage_path text not null,
    content_type text,
    size_bytes bigint,
    vision_output_json jsonb, -- Vision extraction results
    vision_extraction_status text default 'pending' check (vision_extraction_status in ('pending','processing','completed','failed')),
    created_at timestamptz not null default now()
);

create index if not exists idx_artifacts_appraisal
    on artifacts (appraisal_id);

-- test_cases (synthetic cases)
create table if not exists test_cases (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    description text,
    input_payload jsonb not null,
    expected_readiness text,
    expected_escalation boolean,
    created_at timestamptz not null default now()
);

-- eval_runs (evaluation executions)
create table if not exists eval_runs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'running' check (status in ('running','completed','failed')),
    summary jsonb,
    metrics jsonb,
    test_case_ids uuid[]
);
