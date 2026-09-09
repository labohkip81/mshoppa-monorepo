from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "email", "first_name", "last_name", "email_verified", "is_staff"]


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default="")
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists. Please sign in."
            )
        return value

    def validate(self, attrs):
        user = get_user_model()(
            email=attrs["email"], username=attrs["email"], first_name=attrs["first_name"]
        )
        validate_password(attrs["password"], user)
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class CodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$")


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class LoginResultSerializer(serializers.Serializer):
    user = UserSerializer(required=False)
    requires_mfa = serializers.BooleanField(required=False)
    requires_mfa_setup = serializers.BooleanField(required=False)


class MfaSetupSerializer(serializers.Serializer):
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()
