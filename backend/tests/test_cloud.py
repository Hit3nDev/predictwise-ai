"""Cloud mode: S3-mirrored storage and Secrets Manager settings, tested with in-memory fakes."""

import os
import shutil

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import cloud
import storage


class FakeS3:
    """Just the three S3 calls storage.py makes, backed by a dict."""

    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        assert ExtraArgs == {"ServerSideEncryption": "AES256"}      # every object encrypted at rest
        with open(path, "rb") as f:
            self.objects[(bucket, key)] = f.read()

    def download_file(self, bucket, key, path):
        if (bucket, key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        with open(path, "wb") as f:
            f.write(self.objects[(bucket, key)])

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "BUCKET", "pw-test-bucket")
    monkeypatch.setattr(storage, "_client", fake)
    return fake


def test_local_only_when_no_bucket(monkeypatch):
    monkeypatch.setattr(storage, "BUCKET", "")
    assert not storage.enabled()
    assert storage.exists("uploads/never-written.csv") is False
    storage.put("anything")                                       # no-op, no AWS call


def test_keys_match_on_every_os():
    assert storage._key(os.path.join("uploads", "a.csv")) == "uploads/a.csv"
    assert storage._key("./artifacts/model_1.joblib") == "artifacts/model_1.joblib"


def test_file_missing_locally_comes_back_from_s3(s3):
    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", "roundtrip.csv")
    with open(path, "w") as f:
        f.write("a,b\n1,2\n")
    storage.put(path)
    os.remove(path)                       # a different server would not have it
    assert storage.exists(path)
    assert open(path).read() == "a,b\n1,2\n"
    storage.delete(path)
    assert not os.path.exists(path) and s3.objects == {}


def test_second_server_can_predict_with_a_model_trained_on_the_first(s3):
    import main
    client = TestClient(main.app)
    d = client.post("/samples/customers/load").json()
    client.post(f"/datasets/{d['id']}/clean", json={})
    model_id = client.post(f"/datasets/{d['id']}/train", json={"target": "purchased"}).json()["best_model_id"]
    keys = {k for _, k in s3.objects}
    assert any(k.startswith("uploads/") for k in keys)
    assert any(k.startswith("cleaned/") for k in keys)
    assert f"artifacts/model_{model_id}.joblib" in keys

    for folder in ("uploads", "cleaned", "artifacts"):           # wipe this server's disk
        shutil.rmtree(folder)
        os.makedirs(folder)

    eda = client.get(f"/datasets/{d['id']}/eda").json()
    assert eda["source"] == "cleaned"                            # the cleaned copy was found in S3
    r = client.get(f"/models/{model_id}/rank")                   # loads the model and the data from S3
    assert r.status_code == 200, r.text


def test_health_reports_cloud_mode(s3, monkeypatch):
    import main
    monkeypatch.setenv("PW_SERVER_NAME", "i-0abc")
    body = TestClient(main.app).get("/health").json()
    assert body == {"status": "ok", "server": "i-0abc", "storage": "s3", "database": "sqlite"}


def test_rds_secret_becomes_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PW_DB_SECRET_ID", "predictwise/db")
    monkeypatch.delenv("PW_APP_SECRET_ID", raising=False)
    secret = {"username": "pwadmin", "password": "p@ss:w/rd", "host": "db.example.rds.amazonaws.com",
              "port": 5432, "dbname": "predictwise", "engine": "postgres"}
    cloud.load_secrets(reader=lambda sid: secret)
    url = os.environ["DATABASE_URL"]
    assert url.startswith("postgresql+psycopg2://pwadmin:")
    assert "p%40ss%3Aw%2Frd@db.example.rds.amazonaws.com:5432/predictwise" in url


def test_api_keys_from_secret_never_override_local_ones(monkeypatch):
    monkeypatch.delenv("PW_DB_SECRET_ID", raising=False)
    monkeypatch.setenv("PW_APP_SECRET_ID", "predictwise/app")
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cloud.load_secrets(reader=lambda sid: {"GROQ_API_KEY": "from-secret", "ANTHROPIC_API_KEY": "sk-x"})
    assert os.environ["GROQ_API_KEY"] == "from-env"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-x"


def test_nothing_happens_outside_the_cloud(monkeypatch):
    monkeypatch.delenv("PW_DB_SECRET_ID", raising=False)
    monkeypatch.delenv("PW_APP_SECRET_ID", raising=False)
    cloud.load_secrets(reader=lambda sid: pytest.fail("must not call AWS"))
