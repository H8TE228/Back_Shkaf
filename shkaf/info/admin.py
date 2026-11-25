from django.contrib import admin

from .models import Article, ArticleMedia


class ArticleMediaInline(admin.TabularInline):
    model = ArticleMedia
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'published_at')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    inlines = (ArticleMediaInline,)
