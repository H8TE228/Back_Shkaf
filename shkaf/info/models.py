from django.conf import settings
from django.db import models


class Article(models.Model):
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=200)
    body = models.JSONField(default=list)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-published_at', 'slug')

    def __str__(self):
        return self.title


class ArticleMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Изображение'
        VIDEO = 'video', 'Видео'

    article = models.ForeignKey(Article, related_name='media', on_delete=models.CASCADE)
    media_type = models.CharField(max_length=5, choices=MediaType.choices)
    url = models.URLField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('position', 'pk')
