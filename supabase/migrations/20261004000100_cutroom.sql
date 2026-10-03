create table public.video_jobs (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  status text not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);
create table public.video_voices (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);
do $$ declare t text; begin
  foreach t in array array['video_jobs','video_voices'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy "Own video workspace" on public.%I for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)', t);
    execute format('create index %I on public.%I(user_id, created_at desc)', t || '_workspace', t);
  end loop;
end $$;
insert into storage.buckets (id, name, public, file_size_limit)
  values ('videos', 'videos', false, 209715200) on conflict(id) do nothing;
create policy "Own video files" on storage.objects for all to authenticated
  using (bucket_id = 'videos' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'videos' and (storage.foldername(name))[1] = (select auth.uid())::text);
alter publication supabase_realtime add table public.video_jobs;
