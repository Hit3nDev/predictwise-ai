"""
Settings that come from AWS Secrets Manager when running in the cloud.

Must run before `database` and `llm_provider` are imported, because both read
their settings from environment variables at import time.

  PW_DB_SECRET_ID   secret written by CloudFormation for the RDS database
                    (username, password, host, port, dbname) -> DATABASE_URL
  PW_APP_SECRET_ID  secret holding optional API keys, e.g.
                    {"GROQ_API_KEY": "...", "ANTHROPIC_API_KEY": "..."}

Values already set in the environment win, so a local .env keeps working.
Nothing here runs unless one of the two variables is set.
"""

import json
import os


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
    db_id = os.environ.get("PW_DB_SECRET_ID", "").strip()
    if db_id and not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = database_url(reader(db_id))

    app_id = os.environ.get("PW_APP_SECRET_ID", "").strip()
    if app_id:
        for name, value in reader(app_id).items():
            if value and not os.environ.get(name):
                os.environ[name] = str(value)
