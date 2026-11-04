from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .authentication import clear_auth_cookies, set_auth_cookies
from .permissions import IsSelfOrAdmin
from .serializers import (
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    """Вход: токены приходят в HttpOnly-куках, в ответе только данные пользователя."""

    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(responses={200: UserSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as error:
            raise InvalidToken(error.args[0]) from error

        response = Response(UserSerializer(serializer.user, context={'request': request}).data)
        set_auth_cookies(
            response, serializer.validated_data['access'], serializer.validated_data['refresh']
        )
        return response


class RefreshView(TokenRefreshView):
    """Обновление токенов: refresh-токен берётся из куки."""

    @extend_schema(request=None, responses={
        200: OpenApiResponse(description='Новые токены установлены в куки'),
        401: OpenApiResponse(description='Refresh-токен отсутствует, истёк или отозван'),
    })
    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not raw_token:
            raise InvalidToken('Refresh token cookie is missing')

        serializer = self.get_serializer(data={'refresh': raw_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as error:
            raise InvalidToken(error.args[0]) from error

        response = Response({'message': 'Tokens refreshed'})
        set_auth_cookies(
            response, serializer.validated_data['access'], serializer.validated_data['refresh']
        )
        return response


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer


class AccountDeletionMixin:
    def perform_destroy(self, instance):
        for token in OutstandingToken.objects.filter(user=instance):
            BlacklistedToken.objects.get_or_create(token=token)
        instance.anonymize()

    def destroy(self, request, *args, **kwargs):
        # У /me нет pk в адресе: там пользователь всегда удаляет себя
        is_self = kwargs.get('pk') in (None, request.user.pk)
        response = super().destroy(request, *args, **kwargs)
        if is_self:
            clear_auth_cookies(response)
        return response


class MeView(AccountDeletionMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_object(self):
        return self.request.user


class UserDetailView(AccountDeletionMixin, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = User.objects.filter(deleted_at__isnull=True)
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated, IsSelfOrAdmin,)
    http_method_names = ['patch', 'delete', 'head', 'options']


class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            serializer.update(user, serializer.validated_data)
            return Response(
                {"message": "Password updated successfully"},
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class UserListView(generics.ListAPIView):
    queryset = User.objects.filter(deleted_at__isnull=True)
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)


class LogoutView(APIView):
    """
    Выход: отзывает refresh-токен и удаляет куки.
    Работает и с истёкшим access-токеном, иначе пользователь не сможет выйти.
    """
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    @extend_schema(request=None, responses={205: OpenApiResponse(description='Куки удалены')})
    def post(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_205_RESET_CONTENT)
        clear_auth_cookies(response)
        return response
