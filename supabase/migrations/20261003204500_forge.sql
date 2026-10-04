create table public.datasets (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  source text not null,
  profile jsonb not null,
  created_at timestamptz not null default now()
);

create table public.runs (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  name text not null,
  status text not null check (status in ('queued', 'training', 'ready', 'failed')),
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table public.predictions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null references public.runs(id) on delete cascade,
  inputs jsonb not null,
  result jsonb not null,
  actual jsonb,
  created_at timestamptz not null default now()
);

alter table public.datasets enable row level security;
alter table public.runs enable row level security;
alter table public.predictions enable row level security;

create policy "Own datasets" on public.datasets for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Own runs" on public.runs for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and exists (
    select 1 from public.datasets d where d.id = dataset_id and d.user_id = (select auth.uid())
  ));
create policy "Own predictions" on public.predictions for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and exists (
    select 1 from public.runs r where r.id = run_id and r.user_id = (select auth.uid())
  ));

insert into storage.buckets (id, name, public, file_size_limit)
  values ('forge', 'forge', false, 52428800)
  on conflict (id) do nothing;
create policy "Own artifacts" on storage.objects for all to authenticated
  using (bucket_id = 'forge' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'forge' and (storage.foldername(name))[1] = (select auth.uid())::text);

create index datasets_user_id on public.datasets(user_id);
create index runs_user_id on public.runs(user_id);
create index predictions_run_id on public.predictions(run_id);
alter publication supabase_realtime add table public.runs;
