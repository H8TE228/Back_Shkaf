from django.test import TestCase, override_settings


@override_settings(CORS_ALLOWED_ORIGINS=['http://localhost:5173'])
class CorsTests(TestCase):
    def preflight(self, origin):
        return self.client.options(
            '/api/v1/me', HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET'
        )

    def test_frontend_origin_is_allowed_with_credentials(self):
        response = self.preflight('http://localhost:5173')
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:5173')
        self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')

    def test_other_origin_is_not_allowed(self):
        response = self.preflight('https://evil.example')
        self.assertNotIn('Access-Control-Allow-Origin', response)
