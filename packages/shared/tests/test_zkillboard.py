import httpx
import respx

from gank_shared.zkillboard import fetch_current_labels


@respx.mock
def test_fetch_current_labels_returns_labels():
    respx.get("https://zkillboard.com/api/kills/killID/137021750/").mock(
        return_value=httpx.Response(
            200, json=[{"killmail_id": 137021750, "zkb": {"labels": ["loc:highsec", "ganked"]}}]
        )
    )

    assert fetch_current_labels(137021750) == ["loc:highsec", "ganked"]


@respx.mock
def test_fetch_current_labels_empty_response_returns_empty_list():
    respx.get("https://zkillboard.com/api/kills/killID/999999999/").mock(return_value=httpx.Response(200, json=[]))

    assert fetch_current_labels(999999999) == []


@respx.mock
def test_fetch_current_labels_http_error_returns_empty_list():
    respx.get("https://zkillboard.com/api/kills/killID/1/").mock(return_value=httpx.Response(500))

    assert fetch_current_labels(1) == []


@respx.mock
def test_fetch_current_labels_network_error_returns_empty_list():
    respx.get("https://zkillboard.com/api/kills/killID/1/").mock(side_effect=httpx.ConnectError("boom"))

    assert fetch_current_labels(1) == []
