import json
import threading
import urllib.error
import urllib.request

import pytest

from report import NoDataError
from tests.webfixtures import make_context, warm
from webserver import WebServer, lan_ip


@pytest.fixture
def web_dir(tmp_path):
    d = tmp_path / "web"
    (d / "vendor").mkdir(parents=True)
    (d / "index.html").write_text("<html>hi</html>", encoding="utf-8")
    (d / "app.js").write_text("//js", encoding="utf-8")
    (d / "vendor" / "chart.min.js").write_text("//chart", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    return d


@pytest.fixture
def server(tmp_path, monkeypatch, web_dir):
    ctx = make_context(tmp_path, monkeypatch)
    warm(ctx)
    srv = WebServer(ctx, web_dir, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _maybe_json(payload):
    try:
        return json.loads(payload)
    except ValueError:
        return payload


def req(srv, path, method="GET", body=None, token="auto", headers=None, cookie=None, raw=False):
    url = f"http://127.0.0.1:{srv.port}{path}"
    hdrs = dict(headers or {})
    if token == "auto":
        token = srv.token
    if token:
        hdrs["X-Token"] = token
    if cookie:
        hdrs["Cookie"] = cookie
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=5) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else _maybe_json(payload)), resp.headers
    except urllib.error.HTTPError as err:
        payload = err.read()
        return err.code, (payload if raw else _maybe_json(payload)), err.headers


def test_port_is_auto_assigned(server):
    assert server.port > 0


def test_two_servers_get_different_ports(tmp_path, monkeypatch, web_dir):
    a = WebServer(make_context(tmp_path, monkeypatch), web_dir, host="127.0.0.1")
    b = WebServer(make_context(tmp_path, monkeypatch), web_dir, host="127.0.0.1")
    a.start()
    b.start()
    try:
        assert a.port != b.port
        assert a.token != b.token
    finally:
        a.stop()
        b.stop()


@pytest.mark.parametrize(
    "path", ["/api/state", "/api/summary", "/api/timeline", "/api/report.xlsx", "/", "/app.js"]
)
def test_no_token_is_forbidden(server, path):
    assert req(server, path, token=None)[0] == 403


@pytest.mark.parametrize("path", ["/api/state", "/api/summary", "/api/timeline", "/"])
def test_wrong_token_is_forbidden(server, path):
    assert req(server, path, token="wrong")[0] == 403


def test_post_without_token_is_forbidden_and_changes_nothing(server):
    assert req(server, "/api/segment", "POST", {"name": "TVC"}, token=None)[0] == 403
    assert server.ctx.session.index == 0


def test_state_with_header_token(server):
    status, body, hdrs = req(server, "/api/state")
    assert status == 200
    assert body["segment"] == "Waiting Screen"
    assert hdrs["Cache-Control"] == "no-store"


def test_token_in_query_sets_cookie_and_redirects_clean(server):
    status, _, hdrs = req(server, f"/?t={server.token}", token=None)
    assert status == 302
    assert hdrs["Location"] == "/"
    cookie = hdrs["Set-Cookie"]
    assert f"pv_{server.port}={server.token}" in cookie
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_cookie_authenticates_page_and_api(server):
    ck = f"pv_{server.port}={server.token}"
    status, body, _ = req(server, "/", token=None, cookie=ck, raw=True)
    assert status == 200 and b"hi" in body
    assert req(server, "/api/state", token=None, cookie=ck)[0] == 200


def test_static_assets_served(server):
    assert req(server, "/app.js", raw=True)[0] == 200
    status, body, _ = req(server, "/vendor/chart.min.js", raw=True)
    assert status == 200 and body == b"//chart"


@pytest.mark.parametrize(
    "path",
    ["/../secret.txt", "/%2e%2e/secret.txt", "/vendor/../../secret.txt", "/..%5csecret.txt"],
)
def test_path_traversal_blocked(server, path):
    status, body, _ = req(server, path, raw=True)
    assert status in (403, 404)
    assert b"nope" not in body


def test_unknown_route_404(server):
    assert req(server, "/api/nothing")[0] == 404


def test_set_segment_by_name(server):
    status, body, _ = req(server, "/api/segment", "POST", {"name": "TVC"})
    assert status == 200
    assert body["state"]["segment"] == "TVC"
    assert server.ctx.session.current_name() == "TVC"


def test_set_segment_next(server):
    status, body, _ = req(server, "/api/segment", "POST", {"action": "next"})
    assert status == 200 and body["changed"] is True


def test_set_segment_invalid_name_400(server):
    assert req(server, "/api/segment", "POST", {"name": "nope"})[0] == 400
    assert server.ctx.session.index == 0


def test_set_segment_malformed_json_400(server):
    assert req(server, "/api/segment", "POST", b"{not json")[0] == 400


def test_set_segment_wrong_content_type_rejected(server):
    status, _, _ = req(
        server, "/api/segment", "POST", b'{"name":"TVC"}', headers={"Content-Type": "text/plain"}
    )
    assert status == 415
    assert server.ctx.session.index == 0


def test_set_segment_oversized_body_413(server):
    big = b'{"name":"' + b"a" * 10000 + b'"}'
    assert req(server, "/api/segment", "POST", big)[0] == 413


def test_get_on_segment_not_allowed(server):
    assert req(server, "/api/segment")[0] in (404, 405)


def test_other_methods_rejected(server):
    assert req(server, "/api/state", "DELETE")[0] in (404, 405, 501)


def test_timeline_since(server):
    _, first, _ = req(server, "/api/timeline?since=0")
    assert len(first["points"]) == 8
    _, again, _ = req(server, f"/api/timeline?since={first['next']}")
    assert again["points"] == []


def test_timeline_bad_since_treated_as_zero(server):
    status, body, _ = req(server, "/api/timeline?since=abc")
    assert status == 200 and len(body["points"]) == 8


def test_report_without_builder_404(server):
    assert req(server, "/api/report.xlsx")[0] == 404


def _server_with_report(tmp_path, monkeypatch, web_dir, builder):
    srv = WebServer(
        make_context(tmp_path, monkeypatch, report_builder=builder), web_dir, host="127.0.0.1"
    )
    srv.start()
    return srv


def test_report_download(tmp_path, monkeypatch, web_dir):
    out = tmp_path / "r.xlsx"
    out.write_bytes(b"PKfake")
    srv = _server_with_report(tmp_path, monkeypatch, web_dir, lambda: out)
    try:
        status, body, hdrs = req(srv, "/api/report.xlsx", raw=True)
        assert status == 200 and body == b"PKfake"
        assert "attachment" in hdrs["Content-Disposition"]
    finally:
        srv.stop()


def test_report_no_data_409(tmp_path, monkeypatch, web_dir):
    def no_data():
        raise NoDataError("x")

    srv = _server_with_report(tmp_path, monkeypatch, web_dir, no_data)
    try:
        assert req(srv, "/api/report.xlsx")[0] == 409
    finally:
        srv.stop()


def test_report_failure_500_without_leaking(tmp_path, monkeypatch, web_dir):
    def broken():
        raise RuntimeError("C:/secret/path")

    srv = _server_with_report(tmp_path, monkeypatch, web_dir, broken)
    try:
        status, body, _ = req(srv, "/api/report.xlsx", raw=True)
        assert status == 500 and b"secret" not in body
    finally:
        srv.stop()


def test_start_is_idempotent_and_stop_ends_thread(tmp_path, monkeypatch, web_dir):
    srv = WebServer(make_context(tmp_path, monkeypatch), web_dir, host="127.0.0.1")
    srv.start()
    port = srv.port
    srv.start()
    assert srv.port == port
    assert srv.running
    srv.stop()
    assert not srv.running
    assert not any(t.name == "peakview-web" for t in threading.enumerate())
    srv.stop()  # safe twice


def test_url_uses_given_host_and_token(server):
    assert server.url("192.168.1.5") == f"http://192.168.1.5:{server.port}/?t={server.token}"


def test_lan_ip_returns_an_address():
    assert lan_ip().count(".") == 3
