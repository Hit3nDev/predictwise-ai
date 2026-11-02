"""
AWS Lambda: profile every CSV the moment it lands in S3.

Trigger: EventBridge rule "Object Created" on the data bucket, prefix uploads/
(see infra/3-app.yaml). For each file it writes profiles/<name>.json with row,
column and missing-value counts, and publishes CloudWatch metrics so the
dashboard shows upload volume and data quality without touching the web
servers. Standard library + boto3 only (both built into the Lambda runtime).
"""

import csv
import io
import json
import os

import boto3

NAMESPACE = os.environ.get("METRIC_NAMESPACE", "PredictWise")
_s3 = None
_cw = None


def profile_csv(text: str) -> dict:
    rows = csv.reader(io.StringIO(text))
    header = next(rows, [])
    missing = [0] * len(header)
    numeric = [True] * len(header)
    n = 0
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue                                  # blank line, not a record
        n += 1
        for i in range(len(header)):
            cell = row[i].strip() if i < len(row) else ""
            if cell == "":
                missing[i] += 1
            elif numeric[i]:
                try:
                    float(cell.replace(",", ""))
                except ValueError:
                    numeric[i] = False
    cells = n * len(header)
    return {
        "rows": n,
        "columns": len(header),
        "missing_cells": sum(missing),
        "missing_pct": round(100 * sum(missing) / cells, 2) if cells else 0.0,
        "column_profile": [
            {"name": name, "missing": missing[i], "numeric": numeric[i] and missing[i] < n}
            for i, name in enumerate(header)
        ],
    }


def handler(event, context, s3=None, cloudwatch=None):
    global _s3, _cw
    s3 = s3 or _s3 or boto3.client("s3")
    cloudwatch = cloudwatch or _cw or boto3.client("cloudwatch")
    _s3, _cw = s3, cloudwatch

    bucket = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]
    if not key.lower().endswith(".csv"):
        return {"skipped": key, "reason": "only CSV files are profiled"}

    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    profile = profile_csv(body.decode("utf-8-sig", errors="replace"))
    profile["source_key"] = key

    out_key = "profiles/" + os.path.basename(key).rsplit(".", 1)[0] + ".json"
    s3.put_object(Bucket=bucket, Key=out_key, Body=json.dumps(profile, indent=2).encode(),
                  ContentType="application/json", ServerSideEncryption="AES256")

    cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=[
        {"MetricName": "UploadsProfiled", "Value": 1, "Unit": "Count"},
        {"MetricName": "UploadedRows", "Value": profile["rows"], "Unit": "Count"},
        {"MetricName": "UploadMissingPct", "Value": profile["missing_pct"], "Unit": "Percent"},
    ])
    print(json.dumps({"profiled": key, "rows": profile["rows"], "missing_pct": profile["missing_pct"]}))
    return {"profile_key": out_key, "rows": profile["rows"]}
