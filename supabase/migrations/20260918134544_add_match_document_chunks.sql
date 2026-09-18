create extension if not exists vector;

create table if not exists public.document_chunks (
    id uuid primary key default gen_random_uuid(),
    source_document text not null,
    content text not null,
    embedding vector(1536),
    metadata jsonb,
    created_at timestamptz default now()
);

create index if not exists document_chunks_embedding_idx
    on public.document_chunks using ivfflat (embedding vector_cosine_ops);

create or replace function match_document_chunks(
  query_embedding vector(1536),
  match_count int,
  filter_source text
)
returns table (
  content text,
  metadata jsonb,
  similarity float
)
language sql stable
as $$
  select
    content,
    metadata,
    1 - (embedding <=> query_embedding) as similarity
  from document_chunks
  where source_document = filter_source
  order by embedding <=> query_embedding
  limit match_count;
$$;
