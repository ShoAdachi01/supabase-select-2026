-- Trace is independent of the archived Forge tables. Existing data is retained.
create table public.trace_assets (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  unique(id, user_id)
);
create table public.trace_scans (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  asset_id uuid not null,
  status text not null check(status in ('queued','searching','complete','failed')),
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  unique(id, user_id),
  foreign key(asset_id, user_id) references public.trace_assets(id, user_id) on delete cascade
);
create table public.trace_findings (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  asset_id uuid not null,
  scan_id uuid not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  unique(id, user_id),
  foreign key(asset_id, user_id) references public.trace_assets(id, user_id) on delete cascade,
  foreign key(scan_id, user_id) references public.trace_scans(id, user_id) on delete cascade
);
create table public.trace_licenses (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  asset_id uuid not null,
  status text not null check(status in ('pending','approved','needs_information','declined')),
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  foreign key(asset_id, user_id) references public.trace_assets(id, user_id) on delete cascade
);
create table public.trace_grants (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  asset_id uuid not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  foreign key(asset_id, user_id) references public.trace_assets(id, user_id) on delete cascade
);
create table public.trace_reviews (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  asset_id uuid not null,
  finding_id uuid not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  foreign key(asset_id, user_id) references public.trace_assets(id, user_id) on delete cascade,
  foreign key(finding_id, user_id) references public.trace_findings(id, user_id) on delete cascade
);
do $$ declare t text; begin
  foreach t in array array['trace_assets','trace_scans','trace_findings','trace_licenses','trace_grants','trace_reviews'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy "Own workspace" on public.%I for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)', t);
    execute format('create index %I on public.%I(user_id, created_at desc)', t || '_workspace', t);
  end loop;
end $$;
insert into storage.buckets (id, name, public, file_size_limit)
  values ('trace', 'trace', false, 10485760) on conflict(id) do nothing;
create policy "Own Trace evidence" on storage.objects for all to authenticated
  using (bucket_id = 'trace' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'trace' and (storage.foldername(name))[1] = (select auth.uid())::text);
alter publication supabase_realtime add table public.trace_scans;
