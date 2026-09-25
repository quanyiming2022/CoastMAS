"""Isolated UI stress fixtures; generated engineering data, never business evidence."""

import argparse
import json
import time
from pathlib import Path

import httpx
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

parser = argparse.ArgumentParser()
parser.add_argument("--access", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Use a new evidence filename")
access = json.loads(args.access.read_text())
client = httpx.Client(base_url="http://127.0.0.1:58012/api", timeout=60)


def call(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


session = call("POST", "/session", json={k: access[k] for k in ("email", "password")})
client.headers["X-CSRF-Token"] = session["csrf"]
project = call(
    "POST", "/projects", json={"name": "面板压力验收 · 合成工程数据 " + str(time.time_ns())}
)["id"]


def upload_grid(empty=False):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=32,
            height=32,
            count=14,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(113, 23, 0.01, 0.01),
            nodata=-9999,
        ) as ds:
            for band in range(1, 15):
                ds.write(np.full((32, 32), -9999 if empty else band, dtype="float32"), band)
        name = ("无有效像元" if empty else "压力验收_长文件名与完整科学标识_" * 5) + ".tif"
        return call(
            "POST",
            f"/projects/{project}/assets",
            files={"file": (name, memory.read(), "image/tiff")},
        )["asset"]


asset = upload_grid()
csv = call(
    "POST",
    f"/projects/{project}/assets",
    files={"file": ("独立表格参考.csv", b"id,value\n001,5\n002,9\n", "text/csv")},
)["asset"]
method = call(
    "POST",
    f"/projects/{project}/templates",
    json={
        "title": "14指标数值压力方法",
        "purpose": "method",
        "profiles": ["geotiff"],
        "basis": "明确工程测试：14个已知常量波段，各范围0—20、同权重，不是实际科研结论。",
        "configuration": {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": f"工程指标_{i}",
                    "unit": "1",
                    "lower": 0,
                    "upper": 20,
                    "positive": True,
                    "weight": 1 / 14,
                }
                for i in range(1, 15)
            ],
        },
    },
)
call("POST", f"/templates/{method['id']}/approve", json={"revision": 1})


def task_for(a, title):
    task = call(
        "POST", "/tasks", json={"project_id": project, "title": title, "purpose": "assessment"}
    )
    task = call(
        "POST",
        f"/tasks/{task['id']}/sources",
        json={"expected_revision": task["revision"], "assets": [a["id"]]},
    )
    draft = task["draft"]
    draft["method_id"] = method["id"]
    draft["options"] = {"method_revision": 1}
    for i, mapping in enumerate(draft["mapping"], 1):
        mapping.update(concept=f"工程指标_{i}", unit="1", support="grid", role="feature")
    return call(
        "PUT", f"/tasks/{task['id']}", json={"expected_revision": task["revision"], "draft": draft}
    )


def execute(task, key):
    job = call(
        "POST",
        f"/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": key},
    )
    for _ in range(180):
        job = call("GET", f"/jobs/{job['id']}")
        if job["status"] not in ("running", "queued"):
            return job
        time.sleep(0.2)
    raise AssertionError("worker did not finish")


task = task_for(asset, "30图层与多页运行压力验收")
jobs = [execute(task, f"stress-{i}") for i in range(12)]
assert all(job["status"] == "succeeded" for job in jobs)
last = jobs[-1]
result = call("GET", f"/jobs/{last['id']}/result")
assert len(result["data"]["files"]) == 30
assert abs(result["data"]["statistics"]["mean"] - 0.375) < 1e-12
# Multi-type draft uses existing registered sources; binding does not compute.
multitype = call(
    "POST",
    "/tasks",
    json={"project_id": project, "title": "多类型输入 · 无成果", "purpose": "inspect"},
)
multitype = call(
    "POST",
    f"/tasks/{multitype['id']}/sources",
    json={"expected_revision": multitype["revision"], "assets": [asset["id"], csv["id"]]},
)
failed_task = task_for(upload_grid(True), "无有效像元 · 真实失败")
failed = execute(failed_task, "empty-grid")
assert failed["status"] == "failed" and failed["error"]["code"] == "NO_JOINT_VALID_CELLS", (
    failed.get("error")
)
output = {
    "project": project,
    "task": task["id"],
    "run": last["id"],
    "run_ids": [job["id"] for job in jobs],
    "multitype_task": multitype["id"],
    "failed_task": failed_task["id"],
    "failed_run": failed["id"],
    "failure": failed["error"],
    "asset": asset["id"],
    "asset_name": asset["name"],
    "csv": csv["id"],
    "expected_mean": 0.375,
    "generated_engineering_fixture": True,
}
args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
print(
    json.dumps(
        {"outputs": 30, "runs": 12, "valid_mean": 0.375, "actual_failure": failed["error"]["code"]}
    )
)
