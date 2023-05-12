import aiohttp


class OobaClientError(Exception):
    pass


class SerializedHttpClient:
    """
    Purpose: Limits the number of connections to a single host
    to one, so that we don't overwhelm the server.
    """

    HTTP_CLIENT_TIMEOUT_SECONDS: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
        total=None,
        connect=None,
        sock_connect=5.0,
        sock_read=5.0,
    )

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._session = None

    def get_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise OobaClientError("Session not initialized")
        return self._session

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit_per_host=1)
        self._session = aiohttp.ClientSession(
            base_url=self.base_url,
            connector=connector,
            timeout=self.HTTP_CLIENT_TIMEOUT_SECONDS,
        )
        return self

    async def __aexit__(self, *_err):
        if self._session:
            await self._session.close()
        self._session = None
