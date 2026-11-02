"""
File storage: local disk, optionally mirrored to Amazon S3.

Uploads, cleaned copies and trained models are written to local paths like
"uploads/ab12.csv" exactly as before. When PW_S3_BUCKET is set, every write is
also copied to S3 under the same key, and a read of a file that is missing
locally pulls it down first. The local folder then acts as a cache, so any
number of servers behind a load balancer see the same files and a server can
be replaced without losing anything.

Without PW_S3_BUCKET this module does nothing beyond the local checks, so
development and the test suite run with no AWS account.
"""

import os

BUCKET = os.environ.get("PW_S3_BUCKET", "").strip()
_client = None


def enabled() -> bool:
    return bool(BUCKET)


def _s3():
    global _client
    if _client is None:
        import boto3  # only needed when S3 is switched on
        _client = boto3.client("s3")
    return _client


def _key(path: str) -> str:
    # "uploads\\ab12.csv" on Windows and "./uploads/ab12.csv" both map to "uploads/ab12.csv".
    return os.path.normpath(path).replace("\\", "/")


def put(path: str) -> None:
    """Copy a file that was just written locally up to S3."""
    if enabled():
        _s3().upload_file(path, BUCKET, _key(path), ExtraArgs={"ServerSideEncryption": "AES256"})


def exists(path: str) -> bool:
    """True if the file is available, downloading it from S3 when only S3 has it."""
    if not path:
        return False
    if os.path.exists(path):
        return True
    if not enabled():
        return False
    from botocore.exceptions import ClientError
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _s3().download_file(BUCKET, _key(path), path)
        return True
    except ClientError:
        return False


def fetch(path: str) -> str:
    """Return a local path for reading, pulling the file from S3 if needed."""
    exists(path)
    return path


def delete(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    if enabled():
        _s3().delete_object(Bucket=BUCKET, Key=_key(path))
