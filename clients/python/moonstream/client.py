from dataclasses import dataclass, field
import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)
log_level = logging.INFO
if os.environ.get("DEBUG", "").lower() in ["true", "1"]:
    log_level = logging.DEBUG
logger.setLevel(log_level)


def moonstream_endpoints(url: str) -> Dict[str, str]:
    """
    Creates a dictionary of Moonstream API endpoints at the given Moonstream API URL.
    """
    url_with_protocol = url
    if not (
        url_with_protocol.startswith("http://")
        or url_with_protocol.startswith("https://")
    ):
        url_with_protocol = f"http://{url_with_protocol}"

    normalized_url = url_with_protocol.rstrip("/")

    endpoints = ["/ping", "/version", "/now"]

    return {endpoint: f"{normalized_url}{endpoint}" for endpoint in endpoints}


class UnexpectedResponse(Exception):
    """
    Raised when a server response cannot be parsed into the appropriate/expected Python structure.
    """


@dataclass(frozen=True)
class APISpec:
    url: str
    endpoints: Dict[str, str]


class Moonstream:
    """
    A Moonstream client configured to communicate with a given Moonstream API server.
    """

    def __init__(
        self, url: str = "https://api.moonstream.to", timeout: Optional[float] = None
    ):
        endpoints = moonstream_endpoints(url)
        self.api = APISpec(url=url, endpoints=endpoints)
        self.timeout = timeout
        self._session = requests.Session()

    def ping(self) -> Dict[str, Any]:
        r = self._session.get(self.api.endpoints["/ping"])
        r.raise_for_status()
        return r.json()

    def version(self) -> Dict[str, Any]:
        r = self._session.get(self.api.endpoints["/version"])
        r.raise_for_status()
        return r.json()

    def server_time(self) -> float:
        r = self._session.get(self.api.endpoints["/now"])
        r.raise_for_status()
        result = r.json()
        raw_epoch_time = result.get("epoch_time")
        if raw_epoch_time is None:
            raise UnexpectedResponse(
                f'Server response does not contain "epoch_time": {result}'
            )

        try:
            epoch_time = float(raw_epoch_time)
        except:
            raise UnexpectedResponse(
                f"Could not process epoch time as a float: {raw_epoch_time}"
            )

        return epoch_time
