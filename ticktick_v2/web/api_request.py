import json

import requests

from ticktick_v2.utils.logger import create_logger

log = create_logger("Request Helper")


def get_request(url, headers=None, catch_exception=False) -> dict | None:
    """
    Send a POST request to the given URL with the given data and headers.
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as e:
        if catch_exception:
            return None
        else:
            raise RuntimeError(f"Error sending POST request to {url}: {e}") from e


def post_request(url, payload, headers=None, raise_exception=False) -> dict | None:
    """
    Send a POST request to the given URL with the given data and headers.
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        return response.json()
    except Exception as e:
        if raise_exception:
            raise RuntimeError(f"Error sending POST request to {url}: {e}") from e
        else:
            return None
