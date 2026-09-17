from immich_frames.immich_client import ImmichClient


class Response:
    headers = {"content-type": "application/json"}
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def json(self):
        return self.payload

    async def text(self):
        return ""


class ErrorResponse(Response):
    status = 503

    async def text(self):
        return "temporary outage"


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return Response(next(self.responses))


async def test_metadata_search_follows_cursor() -> None:
    first = {"assets": {"items": [{"id": "a", "width": 100, "height": 100, "originalFileName": "a.jpg"}], "nextCursor": "next"}}
    second = {"assets": {"items": [{"id": "b", "width": 100, "height": 100, "originalFileName": "b.jpg"}], "nextCursor": None}}
    session = Session([first, second])
    async with ImmichClient("http://immich.test", "secret", session) as client:
        photos = await client.search({"type": {"eq": "IMAGE"}}, size=2)
    assert [photo.id for photo in photos] == ["a", "b"]
    assert session.requests[1][2]["json"]["cursor"] == "next"


async def test_server_errors_are_retried() -> None:
    class FlakySession(Session):
        def request(self, method, url, **kwargs):
            self.requests.append((method, url, kwargs))
            return ErrorResponse(None) if len(self.requests) < 3 else Response({"version": "3.2.0"})

    session = FlakySession([])
    async with ImmichClient("http://immich.test", "secret", session) as client:
        assert await client.version() == "3.2.0"
    assert len(session.requests) == 3
