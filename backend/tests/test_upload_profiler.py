"""The S3-triggered Lambda in infra/lambda, run locally with fake AWS clients."""

import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "infra", "lambda")))

import upload_profiler  # noqa: E402


class FakeS3:
    def __init__(self, files):
        self.files, self.written = files, {}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.files[Key])}

    def put_object(self, Bucket, Key, Body, **kw):
        self.written[Key] = json.loads(Body)


class FakeCloudWatch:
    def __init__(self):
        self.metrics = {}

    def put_metric_data(self, Namespace, MetricData):
        assert Namespace == "PredictWise"
        self.metrics.update({m["MetricName"]: m["Value"] for m in MetricData})


def _event(key):
    return {"detail": {"bucket": {"name": "pw-bucket"}, "object": {"key": key}}}


def test_profiles_a_csv_and_publishes_metrics():
    csv_bytes = "﻿item,qty,price\nrice,2,\ndal,,80\n\nsugar,1,\"1,200\"\n".encode("utf-8")
    s3, cw = FakeS3({"uploads/ab12.csv": csv_bytes}), FakeCloudWatch()
    out = upload_profiler.handler(_event("uploads/ab12.csv"), None, s3=s3, cloudwatch=cw)

    assert out == {"profile_key": "profiles/ab12.json", "rows": 3}
    p = s3.written["profiles/ab12.json"]
    assert (p["rows"], p["columns"], p["missing_cells"]) == (3, 3, 2)
    assert [c["name"] for c in p["column_profile"]] == ["item", "qty", "price"]   # BOM stripped
    assert [c["numeric"] for c in p["column_profile"]] == [False, True, True]
    assert cw.metrics == {"UploadsProfiled": 1, "UploadedRows": 3, "UploadMissingPct": 22.22}


def test_excel_uploads_are_skipped():
    s3, cw = FakeS3({}), FakeCloudWatch()
    out = upload_profiler.handler(_event("uploads/x.xlsx"), None, s3=s3, cloudwatch=cw)
    assert out["skipped"] == "uploads/x.xlsx" and s3.written == {} and cw.metrics == {}


def test_empty_file():
    assert upload_profiler.profile_csv("")["rows"] == 0
