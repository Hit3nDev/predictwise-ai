"""
Settings that come from AWS Secrets Manager when running in the cloud.

Must run before `database` and `llm_provider` are imported, because both read
their settings from environment variables at import time.

  PW_DB_SECRET_ID   secret written by CloudFormation for the RDS database
                    (username, password, host, port, dbname) -> DATABASE_URL
  PW_APP_SECRET_ID  secret holding optional API keys, e.g.
                    {"GROQ_API_KEY": "...", "ANTHROPIC_API_KEY": "..."}

Locally, the same settings can live in a .env file (backend/.env or the repo
root); load_env_file() reads it. Values already set in the environment win, so
an exported variable or a cloud secret always beats the file.
"""

import json
import os


def load_env_file() -> None:
    """
    Read KEY=VALUE lines from backend/.env, then the repo-root .env, into the
    environment. Blank lines, comments and quotes around values are ignored.
    PW_SKIP_ENV_FILE=1 turns this off; the test suite sets it so a developer's
    real key never changes what the tests see.
    """
    if os.environ.get("PW_SKIP_ENV_FILE"):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"), os.path.join(os.path.dirname(here), ".env")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:].strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                name, value = name.strip(), value.strip().strip("\"'")
                if name and value and not os.environ.get(name):
                    os.environ[name] = value


def _read_secret(secret_id: str) -> dict:
    import boto3  # only needed in the cloud
    raw = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
    return json.loads(raw)


def database_url(secret: dict) -> str:
    from sqlalchemy.engine import URL
    return URL.create(
        "postgresql+psycopg2",
        username=secret["username"],
        password=secret["password"],      # URL.create escapes special characters
        host=secret["host"],
        port=int(secret.get("port", 5432)),
        database=secret.get("dbname", "predictwise"),
    ).render_as_string(hide_password=False)


def load_secrets(reader=_read_secret) -> None:
    load_env_file()
    db_id = os.environ.get("PW_DB_SECRET_ID", "").strip()
    if db_id and not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = database_url(reader(db_id))

    app_id = os.environ.get("PW_APP_SECRET_ID", "").strip()
    if app_id:
        for name, value in reader(app_id).items():
            if value and not os.environ.get(name):
                os.environ[name] = str(value)
