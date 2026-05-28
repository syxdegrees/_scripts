import pytest
import requests
from unittest.mock import patch, MagicMock
from shared.retry import with_retry


def _http_error(status):
    resp = MagicMock()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


def test_succeeds_first_attempt():
    fn = MagicMock(return_value={"ok": True})
    assert with_retry(fn) == {"ok": True}
    assert fn.call_count == 1


def test_retries_on_429_then_succeeds():
    fn = MagicMock(side_effect=[_http_error(429), {"ok": True}])
    with patch("shared.retry.time.sleep"):
        assert with_retry(fn) == {"ok": True}
    assert fn.call_count == 2


def test_retries_on_503_then_succeeds():
    fn = MagicMock(side_effect=[_http_error(503), {"ok": True}])
    with patch("shared.retry.time.sleep"):
        assert with_retry(fn) == {"ok": True}
    assert fn.call_count == 2


def test_raises_after_4_attempts_on_429():
    fn = MagicMock(side_effect=_http_error(429))
    with patch("shared.retry.time.sleep"):
        with pytest.raises(requests.exceptions.HTTPError):
            with_retry(fn)
    assert fn.call_count == 4


def test_does_not_retry_on_400():
    fn = MagicMock(side_effect=_http_error(400))
    with pytest.raises(requests.exceptions.HTTPError):
        with_retry(fn)
    assert fn.call_count == 1


def test_does_not_retry_on_401():
    fn = MagicMock(side_effect=_http_error(401))
    with pytest.raises(requests.exceptions.HTTPError):
        with_retry(fn)
    assert fn.call_count == 1


def test_retries_on_connection_error():
    fn = MagicMock(side_effect=[requests.exceptions.ConnectionError(), {"ok": True}])
    with patch("shared.retry.time.sleep"):
        assert with_retry(fn) == {"ok": True}
    assert fn.call_count == 2


def test_raises_connection_error_after_4_attempts():
    fn = MagicMock(side_effect=requests.exceptions.ConnectionError())
    with patch("shared.retry.time.sleep"):
        with pytest.raises(requests.exceptions.ConnectionError):
            with_retry(fn)
    assert fn.call_count == 4


def test_backoff_sequence():
    fn = MagicMock(side_effect=[_http_error(429), _http_error(429), {"ok": True}])
    with patch("shared.retry.time.sleep") as mock_sleep:
        with_retry(fn)
    assert mock_sleep.call_args_list[0][0][0] == 2
    assert mock_sleep.call_args_list[1][0][0] == 4
