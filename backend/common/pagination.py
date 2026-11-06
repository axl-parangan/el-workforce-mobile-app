from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default page-number pagination for list endpoints.

    Response shape: ``{"count", "next", "previous", "results"}``.

    Append-only, fast-growing collections (punch events, attendance history)
    should prefer cursor pagination once they exist, because it stays stable
    while new rows are being inserted.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
