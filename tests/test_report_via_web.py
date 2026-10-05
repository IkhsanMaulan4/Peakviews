import io
import zipfile

import pytest

from report import generate_report
from tests.test_webserver import req
from tests.webfixtures import make_context, warm
from webserver import WebServer


@pytest.fixture
def web_dir(tmp_path):
    d = tmp_path / "web"
    d.mkdir()
    (d / "index.html").write_text("x", encoding="utf-8")
    return d


def _server(tmp_path, monkeypatch, web_dir, with_data):
    holder = {}

    def build():
        ctx = holder["ctx"]
        return generate_report(
            ctx.store.snapshot(), list(ctx.sources), list(ctx.segments),
            tmp_path / "out" / "laporan.xlsx", ctx.timeline.path,
        )

    ctx = make_context(tmp_path, monkeypatch, report_builder=build)
    holder["ctx"] = ctx
    if with_data:
        warm(ctx)
    srv = WebServer(ctx, web_dir, host="127.0.0.1")
    srv.start()
    return srv


def test_real_report_downloads_as_valid_xlsx(tmp_path, monkeypatch, web_dir):
    srv = _server(tmp_path, monkeypatch, web_dir, with_data=True)
    try:
        status, body, hdrs = req(srv, "/api/report.xlsx", raw=True)
        assert status == 200
        assert "spreadsheetml" in hdrs["Content-Type"]
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        assert any(n.startswith("xl/worksheets/") for n in names)
    finally:
        srv.stop()


def test_real_report_without_data_is_409(tmp_path, monkeypatch, web_dir):
    srv = _server(tmp_path, monkeypatch, web_dir, with_data=False)
    try:
        assert req(srv, "/api/report.xlsx")[0] == 409
    finally:
        srv.stop()
