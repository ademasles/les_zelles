import time

import pytest
from fastapi.testclient import TestClient

from zelles.api.app import create_app
from zelles.config import Settings


@pytest.fixture
def client(settings: Settings):  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as c:
        yield c


def _wait(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_full_flow(client: TestClient, sample_bytes: bytes, sample_pdf: bytes) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/info").json()["llm"] == "rules"

    res = client.post(
        "/api/v1/documents", files={"file": ("cctp.pdf", sample_pdf, "application/pdf")}
    )
    assert res.status_code == 202
    body = res.json()
    assert _wait(client, body["job_id"])["status"] == "done"
    doc_id = body["document_id"]

    again = client.post(
        "/api/v1/documents", files={"file": ("cctp.pdf", sample_pdf, "application/pdf")}
    )
    assert again.status_code == 200 and again.json()["cached"] is True

    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["paginated"] is True
    assert detail["sheet"]["title"].startswith("Construction de 24 logements collectifs")
    listed = client.get("/api/v1/documents").json()
    assert listed[0]["title"] == detail["sheet"]["title"]
    reqs = detail["sheet"]["requirements"]
    uw = next(r for r in reqs if r["field"] == "uw")
    assert uw["citation"]["page"] >= 1

    png = client.get(
        f"/api/v1/documents/{doc_id}/pages/{uw['citation']['page']}.png",
        params={"chunk_id": uw["citation"]["chunk_id"], "quote": uw["citation"]["quote"]},
    )
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")

    xlsx = client.get(f"/api/v1/documents/{doc_id}/export.xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert "field,label" in client.get(f"/api/v1/documents/{doc_id}/export.csv").text.replace(
        "category,", ""
    )

    answer = client.post(
        f"/api/v1/documents/{doc_id}/ask", json={"question": "volets roulants manoeuvre"}
    ).json()
    assert answer["found"] and answer["citations"]

    graph = client.get(f"/api/v1/documents/{doc_id}/graph").json()
    assert graph["nodes"] and graph["links"]
    assert client.get(f"/api/v1/documents/{doc_id}/clarifications").status_code == 200
    tool = client.post("/api/v1/tools/find_conflicts", json={"document_id": doc_id})
    assert tool.status_code == 200
    fb = client.post(
        f"/api/v1/documents/{doc_id}/feedback",
        json={"field": "uw", "value": "1,3", "verdict": "correct"},
    )
    assert fb.status_code == 201
    assert client.post("/api/v1/agent", json={"question": "Quel Uw ?"}).status_code == 409
    assert client.get("/").status_code == 200


def test_rejects_bad_uploads(client: TestClient) -> None:
    res = client.post(
        "/api/v1/documents", files={"file": ("x.exe", b"MZ\x90\x00", "application/octet-stream")}
    )
    assert res.status_code == 415
    assert client.get("/api/v1/documents/../../etc").status_code == 404
    assert client.get("/api/v1/documents/0123456789abcdef").status_code == 404


def test_api_key(tmp_path, sample_bytes: bytes) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(data_dir=tmp_path, llm_model="none", api_key="s3cret")
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/v1/documents").status_code == 401
        assert c.get("/api/v1/documents", headers={"X-API-Key": "s3cret"}).status_code == 200
        assert c.get("/health").status_code == 200
