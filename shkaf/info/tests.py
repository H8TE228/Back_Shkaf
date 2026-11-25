from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Article


class ArticleApiTests(APITestCase):
    def test_public_list_and_detail_only_include_published_articles(self):
        Article.objects.create(slug='draft', title='Draft')
        Article.objects.create(slug='scheduled', title='Scheduled',
                               published_at=timezone.now() + timedelta(days=1))
        response = self.client.get('/api/v1/info')
        self.assertEqual(response.status_code, 200)
        entries = response.data
        self.assertEqual(len(entries), 10)
        self.assertNotIn('body', entries[0])
        article = self.client.get(f"/api/v1/info/{entries[0]['slug']}")
        self.assertEqual(article.status_code, 200)
        self.assertTrue(article.data['body'])
        for slug in ('draft', 'scheduled'):
            self.assertEqual(self.client.get(f'/api/v1/info/{slug}').status_code, 404)
        self.assertEqual(self.client.post('/api/v1/info', {}).status_code, 405)
