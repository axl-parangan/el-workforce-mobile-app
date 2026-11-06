from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CurrentUserSerializer


class CurrentUserView(APIView):
    """Returns the authenticated user. The mobile app uses ``role`` to pick its route group."""

    def get(self, request: Request) -> Response:
        return Response(CurrentUserSerializer(request.user).data)
