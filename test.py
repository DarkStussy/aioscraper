import asyncio
from httpx import AsyncClient
from tests.mocks.client import patch_httpx
from tests.mocks.server import MockResponse, MockServer


async def main():
    async with MockServer(patch_httpx) as server:
        server.add(url=r"api.test.com/v\d+", method="GET", handler=lambda _: MockResponse(json={"status": "OK"}))
        async with AsyncClient() as client:
            response = await client.get("http://api.test.com/v1")
            assert response.json() == {"status": "OK"}

        server.assert_all_routes_handled()


if __name__ == "__main__":
    asyncio.run(main())
