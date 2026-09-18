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