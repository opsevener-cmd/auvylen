"""Generate credentials for a disposable local simulation, never a public deployment."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env.cloud.local"
password = secrets.token_hex(32)
content = (root / ".env.cloud.example").read_text(encoding="utf-8")
content = content.replace("APP_ENV=production", "APP_ENV=staging")
content = content.replace("your-domain.example", "localhost")
content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={password}\n")
content = content.replace(
    "DATABASE_URL=\n", f"DATABASE_URL=postgresql+psycopg://aevyra:{password}@postgres:5432/aevyra\n"
)
content = content.replace("REPLACE_WITH_SECURE_RANDOM_SECRET", secrets.token_hex(48))
content = content.replace("CORS_ORIGINS=[]", 'CORS_ORIGINS=["https://localhost:18443"]')
content = content.replace("APPLY_MIGRATIONS=false", "APPLY_MIGRATIONS=true")
content = content.replace("RESEARCH_MODE=false", "RESEARCH_MODE=true")
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
    file.write(content)
print(
    "Created ignored .env.cloud.local; preserve it for this volume set. Secrets were not printed."
)
