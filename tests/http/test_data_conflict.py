import pytest

from aioscraper.exceptions import InvalidRequestData
from aioscraper.types import Request, File



def test_json_and_data_raises():
    with pytest.raises(InvalidRequestData, match="data and json_data"):
        Request(
            url="https://api.test.com/bad",
            method="POST",
            data={"x": 1},
            json_data={"y": 2},
        )


def test_json_and_files_raises():
    with pytest.raises(InvalidRequestData, match="files and json_data"):
        Request(
            url="https://api.test.com/bad",
            method="POST",
            files={"file": File("name", b"content")},
            json_data={"y": 2},
        )
