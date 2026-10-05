import sys

import pytest

import web_launcher
from tests.webfixtures import make_context
from web_launcher import WebController, qr_image


@pytest.fixture
def web_dir(tmp_path):
    d = tmp_path / "web"
    d.mkdir()
    (d / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    return d


@pytest.fixture
def controller(tmp_path, monkeypatch, web_dir):
    c = WebController(make_context(tmp_path, monkeypatch), web_dir=web_dir)
    yield c
    c.stop()


def test_not_running_initially(controller):
    assert controller.running is False
    assert controller.local_url() is None
    assert controller.share_url() is None


def test_ensure_started_is_idempotent(controller):
    first = controller.ensure_started()
    second = controller.ensure_started()
    assert first is second
    assert controller.running


def test_local_url_is_loopback_with_token(controller):
    controller.ensure_started()
    url = controller.local_url()
    assert url.startswith("http://127.0.0.1:")
    assert f"?t={controller.server.token}" in url


def test_share_url_uses_lan_ip_when_enabled(controller, monkeypatch):
    monkeypatch.setattr(web_launcher, "lan_ip", lambda: "192.168.9.9")
    controller.ensure_started(lan=True)
    assert controller.share_url().startswith("http://192.168.9.9:")


def test_share_url_is_loopback_when_lan_disabled(controller, monkeypatch):
    monkeypatch.setattr(web_launcher, "lan_ip", lambda: "192.168.9.9")
    controller.ensure_started(lan=False)
    assert controller.share_url().startswith("http://127.0.0.1:")
    assert controller.lan is False


def test_set_lan_restarts_with_new_token(controller):
    controller.ensure_started(lan=True)
    old_token = controller.server.token
    controller.set_lan(False)
    assert controller.running
    assert controller.lan is False
    assert controller.server.token != old_token


def test_set_lan_same_value_keeps_server(controller):
    controller.ensure_started(lan=True)
    token = controller.server.token
    controller.set_lan(True)
    assert controller.server.token == token


def test_stop_then_start_gives_fresh_token(controller):
    controller.ensure_started()
    old = controller.server.token
    controller.stop()
    assert controller.running is False
    controller.ensure_started()
    assert controller.server.token != old


def test_stop_without_start_is_safe(controller):
    controller.stop()


def test_default_web_dir_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert web_launcher.default_web_dir() == tmp_path / "web"


def test_default_web_dir_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    d = web_launcher.default_web_dir()
    assert (d / "index.html").is_file()


def test_qr_image_is_square_and_scannable_size():
    img = qr_image("http://192.168.1.5:5000/?t=abc", scale=6)
    assert img.width == img.height
    assert img.width >= 100
    assert img.mode in ("1", "L", "RGB")


def test_qr_image_differs_per_url():
    a = qr_image("http://1.1.1.1:1/?t=a", scale=4)
    b = qr_image("http://2.2.2.2:2/?t=b", scale=4)
    assert a.tobytes() != b.tobytes()
