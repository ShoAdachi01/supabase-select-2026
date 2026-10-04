"""Write local development settings without printing credentials."""

import json
import subprocess
from pathlib import Path

status = subprocess.run(
    ["supabase", "status", "-o", "json"], capture_output=True, text=True, check=True
)
settings = json.loads(status.stdout)
path = Path(".env")
existing = path.read_text() if path.exists() else ""
preserve = [
    line
    for line in existing.splitlines()
    if not line.startswith(("SUPABASE_URL=", "SUPABASE_ANON_KEY=", "LOCAL_DEMO_MODE="))
]
path.write_text(
    "\n".join(
        preserve
        + [
            f"SUPABASE_URL={settings['API_URL']}",
            f"SUPABASE_ANON_KEY={settings['ANON_KEY']}",
            "LOCAL_DEMO_MODE=false",
        ]
    )
    + "\n"
)
path.chmod(0o600)
print("Local Supabase configuration written to .env (credentials hidden).")
