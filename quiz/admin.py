from django.contrib import admin
from .models import Test, Question, Choice, AcceptedAnswer, MatchPair


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 3


class AcceptedAnswerInline(admin.TabularInline):
    model = AcceptedAnswer
    extra = 1


class MatchPairInline(admin.TabularInline):
    model = MatchPair
    extra = 3


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'test', 'qtype', 'points', 'order')
    list_filter = ('test', 'qtype')
    inlines = [ChoiceInline, AcceptedAnswerInline, MatchPairInline]