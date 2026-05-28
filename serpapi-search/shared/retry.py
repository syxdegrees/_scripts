import time
import requests

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_BACKOFF = [2, 4, 8]


def with_retry(fn):
    """Call fn(), retrying on retryable HTTP errors or connection errors with exponential backoff."""
    last_exc = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return fn()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF[attempt])
                last_exc = e
            else:
                raise
        except requests.exceptions.ConnectionError as e:
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF[attempt])
                last_exc = e
            else:
                raise
    raise last_exc
