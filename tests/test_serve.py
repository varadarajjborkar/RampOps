"""End-to-end over a real socket: the dev server serves static files and the API."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from rampops import serve


@pytest.fixture()
def base(tmp_path):
    (tmp_path / "index.html").write_text("<h1>hi</h1>")
    srv = serve.make_server("127.0.0.1", 0, tmp_path)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_static_and_api(base):
    assert b"<h1>hi</h1>" in urllib.request.urlopen(base + "/").read()
    data = json.load(urllib.request.urlopen(base + "/api/health"))
    assert data["status"] == "ok"


def test_api_errors_keep_status_codes(base):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/api/plan?fe_capacity=0")
    assert e.value.code == 400
    assert json.load(e.value)["error"]


def test_head_and_post_over_the_wire(base):
    head = urllib.request.urlopen(urllib.request.Request(base + "/api/health", method="HEAD"))
    assert head.status == 200 and head.read() == b""
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(base + "/api/health", method="POST", data=b"x"))
    assert e.value.code == 405
