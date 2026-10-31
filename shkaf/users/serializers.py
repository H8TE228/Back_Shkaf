from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from users.models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email        
        return token
    
    def validate(self, attrs):
        data = super().validate(attrs)
        
        user = self.user
        data['user'] = {
            'id': user.id,
            'email': user.email,
        }
        
        return data

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'phone_number',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at',)

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            'email', 
            'username', 
            'password', 
            'password2', 
            'phone_number',
            'first_name',
            'last_name',
        )

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({
                "password": "Password fields don't match."
            })
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        
        if not validated_data['username']:
            validated_data['username'] = validated_data['email'].split('@')[0]
        
        user = User.objects.create_user(**validated_data)
        return user

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True, validators=[validate_password]
    )
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value
    
    def update(self, instance, validated_data):
        instance.set_password(validated_data['new_password'])
        instance.save()
        return instance

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text='Refresh JWT token for adding to blacklist')
