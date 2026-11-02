from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()
PASSWORD = 'Xk29-test-Qz'


def make_user(email='user@example.test', username='user', **kwargs):
    return User.objects.create_user(email=email, username=username, password=PASSWORD, **kwargs)


class RegisterTests(APITestCase):
    url = '/api/v1/users/register'

    def payload(self, **kwargs):
        return {
            'email': 'new@example.test',
            'username': 'new',
            'phone_number': '+79990000000',
            'password': PASSWORD,
            'password2': PASSWORD,
            **kwargs,
        }

    def test_register_returns_contract_fields(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {'id', 'username', 'email', 'created_at'})
        self.assertTrue(User.objects.get(email='new@example.test').check_password(PASSWORD))

    def test_passwords_must_match(self):
        response = self.client.post(self.url, self.payload(password2='Other-Xk29-Qz'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_and_phone_are_unique(self):
        make_user(email='new@example.test', phone_number='+79991111111')
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

        response = self.client.post(
            self.url, self.payload(email='other@example.test', phone_number='+79991111111')
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)

    def test_several_users_without_phone(self):
        for number in range(2):
            response = self.client.post(self.url, self.payload(
                email=f'nophone{number}@example.test', username=f'nophone{number}', phone_number='',
            ))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class AuthTests(APITestCase):
    def setUp(self):
        self.user = make_user()

    def login(self):
        return self.client.post(
            '/api/v1/users/auth', {'email': self.user.email, 'password': PASSWORD}
        )

    def test_login_returns_tokens(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access', 'refresh'})

    def test_wrong_password(self):
        response = self.client.post(
            '/api/v1/users/auth', {'email': self.user.email, 'password': 'wrong'}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_and_logout(self):
        tokens = self.login().data
        response = self.client.post('/api/v1/users/auth/refresh', {'refresh': tokens['refresh']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        refresh = response.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        response = self.client.post('/api/v1/users/logout', {'refresh': refresh})
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        response = self.client.post('/api/v1/users/auth/refresh', {'refresh': refresh})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTests(APITestCase):
    url = '/api/v1/me'

    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_profile(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['points_balance'], 0)

    def test_patch_profile(self):
        response = self.client.patch(self.url, {'city': 'Екатеринбург', 'district': 'Кировский'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.city, 'Екатеринбург')

    def test_role_and_points_are_read_only(self):
        self.client.patch(self.url, {'role': 'admin', 'points_balance': 1000})
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.USER)
        self.assertEqual(self.user.points_balance, 0)

    def test_put_is_not_allowed(self):
        response = self.client.put(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_anonymizes_account(self):
        self.client.force_authenticate(None)
        tokens = self.client.post(
            '/api/v1/users/auth', {'email': self.user.email, 'password': PASSWORD}
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertIsNotNone(self.user.deleted_at)
        self.assertNotIn('user@example.test', self.user.email)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        response = self.client.post(
            '/api/v1/users/auth', {'email': 'user@example.test', 'password': PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post('/api/v1/users/auth/refresh', {'refresh': tokens['refresh']})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password(self):
        response = self.client.patch(
            '/api/v1/me/change-password', {'old_password': PASSWORD, 'new_password': 'Zq48-new-Lm'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Zq48-new-Lm'))


class UserDetailTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user(email='other@example.test', username='other')
        self.url = f'/api/v1/users/{self.user.pk}'

    def test_anonymous_is_rejected(self):
        response = self.client.patch(self.url, {'city': 'X'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_user_is_forbidden(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(self.url, {'city': 'X'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_update(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(self.url, {'city': 'X'}).status_code, status.HTTP_200_OK)

    def test_admin_can_delete(self):
        admin = make_user(email='admin@example.test', username='admin', is_staff=True)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.patch(self.url, {'city': 'X'}).status_code, status.HTTP_404_NOT_FOUND)

    def test_user_list_is_admin_only(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/v1/users/').status_code, status.HTTP_403_FORBIDDEN)


class UserModelTests(APITestCase):
    def test_points_balance_cannot_be_negative(self):
        user = make_user()
        user.points_balance = -1
        with self.assertRaises(IntegrityError), transaction.atomic():
            user.save()

    def test_approx_location_is_rounded(self):
        user = make_user(approx_location=Point(60.60571, 56.83892, srid=4326))
        user.refresh_from_db()
        self.assertAlmostEqual(user.approx_location.x, 60.605)
        self.assertAlmostEqual(user.approx_location.y, 56.84)
