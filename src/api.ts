import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Config } from './types';

let client: SupabaseClient | null = null;
let config: Config;
let initPromise: Promise<Config> | undefined;

export function initialize(): Promise<Config> {
  if (!initPromise)
    initPromise = (async () => {
      const response = await fetch('/api/config');
      if (!response.ok)
        throw new Error('The Forge server is unavailable. Start the API server and refresh.');
      config = await response.json();
      if (!config.configured)
        throw new Error(
          'Start Supabase and run python3 scripts/local_env.py, then restart the API server.',
        );
      if (config.mode === 'supabase') {
        client = createClient(config.supabase_url, config.supabase_key);
        const { data, error: sessionError } = await client.auth.getSession();
        if (sessionError) throw sessionError;
        if (!data.session) {
          const { error } = await client.auth.signInAnonymously();
          if (error)
            throw new Error(
              `Unable to create a workspace: ${error.message}. Enable anonymous sign-ins in Supabase Auth.`,
            );
        }
      }
      return config;
    })();
  return initPromise;
}

export async function accessToken(): Promise<string> {
  await initialize();
  if (!client) return 'local-demo';
  const { data } = await client.auth.getSession();
  if (!data.session) throw new Error('Your session expired. Refresh the page.');
  return data.session.access_token;
}

export function supabaseClient() {
  return client;
}

export async function api<T>(path: string, body?: unknown, form?: FormData): Promise<T> {
  const token = await accessToken();
  const response = await fetch(path, {
    method: body !== undefined || form ? 'POST' : 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      ...(!form && body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: form || (body !== undefined ? JSON.stringify(body) : undefined),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed (${response.status}). Check the task settings and try again.`,
    );
  return data;
}

export async function downloadDataset(id: string) {
  const response = await fetch(`/api/datasets/${id}/download`, {
    headers: { Authorization: `Bearer ${await accessToken()}` },
  });
  if (!response.ok) throw new Error('Unable to download the dataset.');
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'forge-dataset.csv';
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
