import hashlib
import time

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import EmailChallenge
from .serializers import (
    CodeSerializer,
    DetailSerializer,
    LoginResultSerializer,
    LoginSerializer,
    MfaSetupSerializer,
    RegisterSerializer,
    TokenSerializer,
    UserSerializer,
)
from .services import verification_email


class CsrfAPIView(APIView):
    def initial(self, request, *args, **kwargs):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            SessionAuthentication().enforce_csrf(request)
        super().initial(request, *args, **kwargs)


class AuthView(CsrfAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class PlatformPermission(BasePermission):
    message = "Platform access requires a verified staff account and MFA."

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.is_staff
            and request.user.email_verified
            and request.session.get("mfa_user") == request.user.pk
            and request.session.get("mfa_at", 0) > time.time() - 12 * 3600
        )


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=TokenSerializer)
    def get(self, request):
        return Response({"token": get_token(request)})


class RegisterView(AuthView):
    @extend_schema(request=RegisterSerializer, responses={201: DetailSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(username=data["email"], **data)
                verification_email(user)
        except IntegrityError:
            raise ValidationError({"email": "An account with this email already exists."})
        return Response({"detail": "Check your email to verify your account."}, status=201)


class VerifyEmailView(AuthView):
    @extend_schema(request=TokenSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        digest = hashlib.sha256(serializer.validated_data["token"].encode()).hexdigest()
        with transaction.atomic():
            challenge = EmailChallenge.objects.filter(
                digest=digest, used_at=None, expires_at__gt=timezone.now()
            ).first()
            if not challenge:
                raise ValidationError("This verification link is invalid or has expired.")
            challenge.used_at = timezone.now()
            challenge.save(update_fields=["used_at"])
            get_user_model().objects.filter(pk=challenge.user_id).update(email_verified=True)
        return Response({"detail": "Email verified. You can now sign in."})


class LoginView(AuthView):
    @extend_schema(request=LoginSerializer, responses=LoginResultSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"].strip().lower(),
            password=serializer.validated_data["password"],
        )
        if not user:
            raise AuthenticationFailed("The email or password is incorrect.")
        if not user.email_verified:
            raise PermissionDenied("Please verify your email before signing in.")
        logout(request)
        if user.is_staff:
            request.session["pending_mfa_user"] = user.pk
            request.session["pending_mfa_at"] = time.time()
            return Response({"requires_mfa": True, "requires_mfa_setup": not bool(user.mfa_secret)})
        login(request, user)
        return Response({"user": UserSerializer(user).data})


def pending_mfa(request):
    if request.session.get("pending_mfa_at", 0) < time.time() - 300:
        raise PermissionDenied("Sign in again to continue verification.")
    user = (
        get_user_model()
        .objects.filter(pk=request.session.get("pending_mfa_user"), is_active=True, is_staff=True)
        .first()
    )
    if not user:
        raise PermissionDenied("Sign in again to continue verification.")
    return user


class MfaSetupView(AuthView):
    @extend_schema(request=None, responses=MfaSetupSerializer)
    def post(self, request):
        user = pending_mfa(request)
        if user.mfa_secret:
            raise PermissionDenied("An authenticator is already configured.")
        key = request.session.get("enrolling_secret") or pyotp.random_base32()
        request.session["enrolling_secret"] = key
        return Response(
            {
                "secret": key,
                "provisioning_uri": pyotp.TOTP(key).provisioning_uri(
                    user.email, issuer_name="MSHOPPA"
                ),
            }
        )


class MfaVerifyView(AuthView):
    @extend_schema(request=CodeSerializer, responses=LoginResultSerializer)
    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pending = pending_mfa(request)
        with transaction.atomic():
            user = get_user_model().objects.get(pk=pending.pk)
            key = (
                Fernet(settings.ENCRYPTION_KEY.encode()).decrypt(user.mfa_secret.encode()).decode()
                if user.mfa_secret
                else request.session.get("enrolling_secret")
            )
            if not key:
                raise ValidationError("Set up your authenticator first.")
            counter = int(time.time()) // 30
            totp = pyotp.TOTP(key)
            matches = [
                c
                for c in (counter - 1, counter, counter + 1)
                if c > user.last_mfa_counter
                and pyotp.utils.strings_equal(totp.at(c * 30), serializer.validated_data["code"])
            ]
            if not matches:
                raise ValidationError("The authenticator code is invalid or has already been used.")
            user.mfa_secret = (
                Fernet(settings.ENCRYPTION_KEY.encode()).encrypt(key.encode()).decode()
            )
            user.last_mfa_counter = matches[0]
            user.save(update_fields=["mfa_secret", "last_mfa_counter"])
        login(request, user)
        request.session["mfa_user"] = user.pk
        request.session["mfa_at"] = time.time()
        for name in ("pending_mfa_user", "pending_mfa_at", "enrolling_secret"):
            request.session.pop(name, None)
        return Response({"user": UserSerializer(user).data})


class MeView(CsrfAPIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(CsrfAPIView):
    @extend_schema(request=None, responses=DetailSerializer)
    def post(self, request):
        logout(request)
        return Response({"detail": "Signed out."})
