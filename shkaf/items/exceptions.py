from rest_framework import status
from rest_framework.exceptions import APIException


class StateConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'The action is not allowed in the current item status.'
    default_code = 'state_conflict'
