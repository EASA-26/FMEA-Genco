"""Workbook upload, report JSON and PDF endpoints (fake parser and renderer)."""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from backend.api.routes_report import MSG_EXPORT_BLOCKED, MSG_NO_REPORT, MSG_PDF_FAILED
from backend.api.upload import (
    MSG_INCOMPLETE,
    MSG_NO_FILE,
    UploadRejected,
    clean_filename,
    read_single_file,
)
from backend.main import MSG_SERVER_ERROR
from backend.tests.test_api_support import (
    SYNTHETIC_OPEN_ERROR,
    SYNTHETIC_PDF,
    FakeServices,
    login,
    make_client,
    make_report,
    make_settings,
    multipart_body,
    upload,
)

MSG_WRONG_TYPE = "Please upload an Excel workbook (.xlsx or .xlsm)."
MB = 1024 * 1024


def _signed_in(services: FakeServices | None = None, settings=None, **client_kwargs):
    services = services if services is not None else FakeServices()
    client = make_client(settings, services, **client_kwargs)
    assert login(client).status_code == 200
    return client, services


# --------------------------------------------------------------------------- #
# Upload: file type
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "filename",
    [
        "SYNTHETIC.xls",
        "SYNTHETIC.csv",
        "SYNTHETIC.pdf",
        "SYNTHETIC.xlsx.exe",
        "SYNTHETIC_no_extension",
        ".xlsx",
        "SYNTHETIC.xlsx.bak",
    ],
)
def test_upload_wrong_extension_is_rejected(filename):
    client, services = _signed_in()
    response = upload(client, filename=filename)
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_WRONG_TYPE}
    assert services.build_calls == []


def test_upload_form_sent_without_choosing_a_file():
    client, services = _signed_in()
    body, content_type = multipart_body([("file", "", b"")])
    response = client.post("/api/workbook", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_NO_FILE}
    assert services.build_calls == []


@pytest.mark.parametrize("filename", ["SYNTHETIC.xlsx", "SYNTHETIC.XLSX", "SYNTHETIC macro.xlsm"])
def test_upload_accepted_extensions(filename):
    client, services = _signed_in()
    response = upload(client, filename=filename)
    assert response.status_code == 200
    assert services.build_calls[0][0] == filename


def test_upload_filename_folders_are_removed():
    client, services = _signed_in()
    body, content_type = multipart_body(
        [("file", "D:\\SYNTHETIC\\Desktop\\SYNTHETIC_plant.xlsx", b"SYNTHETIC data")]
    )
    response = client.post("/api/workbook", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 200
    assert services.build_calls == [("SYNTHETIC_plant.xlsx", b"SYNTHETIC data")]
    assert clean_filename("../../etc/SYNTHETIC.xlsx") == "SYNTHETIC.xlsx"


def test_upload_without_file_field():
    client, services = _signed_in()
    body, content_type = multipart_body([("notes", None, b"SYNTHETIC text only")])
    response = client.post("/api/workbook", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_NO_FILE}

    response = client.post("/api/workbook", json={"file": "SYNTHETIC"})
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_NO_FILE}
    assert services.build_calls == []


def test_upload_ignores_other_fields_and_uses_file_field():
    client, services = _signed_in()
    body, content_type = multipart_body(
        [
            ("comment", None, b"SYNTHETIC comment"),
            ("other", "SYNTHETIC_other.xlsx", b"SYNTHETIC wrong part"),
            ("file", "SYNTHETIC_right.xlsx", b"SYNTHETIC right part"),
        ]
    )
    response = client.post("/api/workbook", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 200
    assert services.build_calls == [("SYNTHETIC_right.xlsx", b"SYNTHETIC right part")]


# --------------------------------------------------------------------------- #
# Upload: size
# --------------------------------------------------------------------------- #
def test_upload_over_limit_is_413():
    client, services = _signed_in(settings=make_settings(max_upload_mb=1))
    response = upload(client, data=b"x" * (MB + 1))
    assert response.status_code == 413
    assert response.json() == {"detail": "The file is larger than 1 MB. Please upload a smaller workbook."}
    assert services.build_calls == []


def test_upload_exactly_at_limit_is_accepted():
    client, services = _signed_in(settings=make_settings(max_upload_mb=1))
    assert upload(client, data=b"x" * MB).status_code == 200
    assert len(services.build_calls[0][1]) == MB


def test_upload_size_enforced_without_content_length():
    client, services = _signed_in(settings=make_settings(max_upload_mb=1))
    body, content_type = multipart_body([("file", "SYNTHETIC.xlsx", b"x" * (MB + 10))])

    def chunks():  # streamed body: no Content-Length header is sent
        for start in range(0, len(body), 64 * 1024):
            yield body[start:start + 64 * 1024]

    response = client.post("/api/workbook", content=chunks(), headers={"Content-Type": content_type})
    assert response.status_code == 413
    assert services.build_calls == []


def test_upload_size_enforced_when_content_length_lies():
    client, services = _signed_in(settings=make_settings(max_upload_mb=1))
    body, content_type = multipart_body([("file", "SYNTHETIC.xlsx", b"x" * (MB + 10))])
    response = client.post(
        "/api/workbook",
        content=body,
        headers={"Content-Type": content_type, "Content-Length": "200"},
    )
    assert response.status_code == 413
    assert services.build_calls == []


def _run(coro):
    return asyncio.run(coro)


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


def test_declared_content_length_rejects_before_reading_body():
    async def must_not_be_read():
        raise AssertionError("body should not be read")
        yield b""  # pragma: no cover

    headers = {
        "content-type": "multipart/form-data; boundary=abc",
        "content-length": str(50 * MB),
    }
    with pytest.raises(UploadRejected) as info:
        _run(read_single_file(headers, must_not_be_read(), field_name="file", max_bytes=MB, extensions=(".xlsx",)))
    assert info.value.status_code == 413


def test_parser_handles_tiny_chunks():
    content = bytes(range(256)) * 8 + b"\r\n--notTheBoundary\r\n" + b"SYNTHETIC tail"
    body, content_type = multipart_body([("file", "SYNTHETIC.xlsx", content)])
    chunks = [body[i:i + 1] for i in range(len(body))]
    received = _run(
        read_single_file(
            {"content-type": content_type},
            _stream(chunks),
            field_name="file",
            max_bytes=MB,
            extensions=(".xlsx",),
        )
    )
    assert received.filename == "SYNTHETIC.xlsx"
    assert received.data == content


def test_parser_rejects_truncated_body():
    body, content_type = multipart_body([("file", "SYNTHETIC.xlsx", b"SYNTHETIC" * 100)])
    with pytest.raises(UploadRejected) as info:
        _run(
            read_single_file(
                {"content-type": content_type},
                _stream([body[: len(body) // 2]]),
                field_name="file",
                max_bytes=MB,
                extensions=(".xlsx",),
            )
        )
    assert info.value.status_code == 400
    assert info.value.message == MSG_INCOMPLETE


def test_wrong_extension_wins_over_size_once_filename_seen():
    body, content_type = multipart_body([("file", "SYNTHETIC.pdf", b"x" * (3 * MB))])
    with pytest.raises(UploadRejected) as info:
        _run(
            read_single_file(
                {"content-type": content_type},
                _stream([body[i:i + 65536] for i in range(0, len(body), 65536)]),
                field_name="file",
                max_bytes=MB,
                extensions=(".xlsx", ".xlsm"),
            )
        )
    assert info.value.status_code == 400
    assert info.value.message == MSG_WRONG_TYPE


# --------------------------------------------------------------------------- #
# Upload: parsing results
# --------------------------------------------------------------------------- #
def test_unreadable_workbook_returns_400_with_its_message():
    client, services = _signed_in()
    response = upload(client, data=b"NOT-A-WORKBOOK SYNTHETIC")
    assert response.status_code == 400
    assert response.json() == {"detail": SYNTHETIC_OPEN_ERROR}


def test_failed_upload_keeps_previous_report():
    client, services = _signed_in()
    assert upload(client).status_code == 200
    assert upload(client, data=b"NOT-A-WORKBOOK SYNTHETIC").status_code == 400
    assert client.get("/api/report").status_code == 200


def test_successful_upload_returns_report_json():
    client, services = _signed_in()
    data = b"SYNTHETIC \x00\x01\xff binary workbook bytes"
    response = upload(client, data=data, filename="SYNTHETIC_S9.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["station"] == "SYNTHETIC Station"
    assert body["source_filename"] == "SYNTHETIC_S9.xlsx"
    assert body["analysis_date"] == "2026-01-15"
    assert body["can_export"] is True
    assert body["issues"][0]["code"] == "SYNTHETIC_WARNING"
    assert services.build_calls == [("SYNTHETIC_S9.xlsx", data)]

    report = client.get("/api/report")
    assert report.status_code == 200
    assert report.json() == body


def test_get_report_404_before_upload():
    client, _ = _signed_in()
    response = client.get("/api/report")
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_NO_REPORT}


def test_new_upload_replaces_report():
    client, services = _signed_in()
    services.next_report = make_report(station="SYNTHETIC First")
    upload(client)
    services.next_report = make_report(station="SYNTHETIC Second")
    upload(client)
    assert client.get("/api/report").json()["station"] == "SYNTHETIC Second"


def test_delete_workbook_clears_report():
    client, _ = _signed_in()
    upload(client)
    response = client.delete("/api/workbook")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/report").status_code == 404
    assert client.get("/api/report/pdf").status_code == 404


def test_reports_are_isolated_between_sessions():
    client, services = _signed_in()
    upload(client)
    from fastapi.testclient import TestClient

    other = TestClient(client.app)
    assert login(other).status_code == 200
    assert other.get("/api/report").status_code == 404


def test_unexpected_parser_failure_is_plain_500():
    services = FakeServices()
    services.build_error = RuntimeError("SYNTHETIC secret internal detail C:\\path\\builder.py line 42")
    client, _ = _signed_in(services, raise_server_exceptions=False)
    response = upload(client)
    assert response.status_code == 500
    assert response.json() == {"detail": MSG_SERVER_ERROR}
    assert "secret" not in response.text and "Traceback" not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def test_pdf_404_before_upload():
    client, services = _signed_in()
    response = client.get("/api/report/pdf")
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_NO_REPORT}
    assert services.render_calls == 0


def test_pdf_409_when_report_has_errors():
    client, services = _signed_in()
    services.next_report = make_report(errors=3)
    upload(client)
    for query in ("", "?download=1"):
        response = client.get("/api/report/pdf" + query)
        assert response.status_code == 409
        assert response.json() == {"detail": MSG_EXPORT_BLOCKED, "error_count": 3}
    assert services.render_calls == 0


@pytest.mark.parametrize(
    "query,disposition",
    [("", "inline"), ("?download=0", "inline"), ("?download=1", "attachment"), ("?download=true", "attachment")],
)
def test_pdf_headers(query, disposition):
    client, services = _signed_in()
    upload(client)
    response = client.get("/api/report/pdf" + query)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'{disposition}; filename="FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.content.startswith(SYNTHETIC_PDF)


def test_pdf_invalid_download_value_is_plain_422():
    client, _ = _signed_in()
    upload(client)
    response = client.get("/api/report/pdf?download=maybe")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_pdf_filename_is_sanitised_for_header():
    client, services = _signed_in()
    services.next_report = make_report(pdf_filename='SYNTHETIC"bad\r\nname;.pdf')
    upload(client)
    header = client.get("/api/report/pdf").headers["content-disposition"]
    assert "\r" not in header and "\n" not in header
    # Quoted ASCII fallback first, then the percent-encoded real name (RFC 5987).
    match = re.fullmatch(r"""inline; filename="([^"]*)"; filename\*=UTF-8''([A-Za-z0-9%!#$&+\-.^_`|~]+)""", header)
    assert match, header
    inner = match.group(1)
    assert ";" not in inner and "\\" not in inner
    assert inner.endswith(".pdf")


def test_pdf_cache_reused_until_next_upload():
    client, services = _signed_in()
    upload(client)
    preview = client.get("/api/report/pdf?download=0")
    download = client.get("/api/report/pdf?download=1")
    assert services.render_calls == 1
    assert preview.content == download.content

    upload(client)
    fresh = client.get("/api/report/pdf")
    assert services.render_calls == 2
    assert fresh.content != preview.content
    client.get("/api/report/pdf?download=1")
    assert services.render_calls == 2

    client.delete("/api/workbook")
    upload(client)
    client.get("/api/report/pdf")
    assert services.render_calls == 3


def test_pdf_render_failure_is_plain_500_and_not_cached():
    services = FakeServices()
    services.render_error = RuntimeError("SYNTHETIC reportlab internals")
    client, _ = _signed_in(services)
    upload(client)
    response = client.get("/api/report/pdf")
    assert response.status_code == 500
    assert response.json() == {"detail": MSG_PDF_FAILED}
    assert "reportlab" not in response.text

    services.render_error = None
    assert client.get("/api/report/pdf").status_code == 200
    assert services.render_calls == 2


def test_report_json_is_valid_json_with_iso_datetimes():
    client, _ = _signed_in()
    body = json.loads(upload(client).content)
    assert body["generated_at"].startswith("2026-01-15T09:30")
