from yarl import URL

from ..types import QueryParams


def parse_url(url: str, params: QueryParams | None) -> URL:
    parsed_url = URL(url)
    if params:
        return parsed_url.update_query(params)

    return parsed_url
