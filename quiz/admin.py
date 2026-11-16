from django.contrib import admin
from .models import Test, Question, Choice, AcceptedAnswer, MatchPair, Attempt, AttemptAnswer


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

class AttemptAnswerInline(admin.TabularInline):
    model = AttemptAnswer
    extra = 0
    can_delete = False
    readonly_fields = ('question', 'given', 'correct_text', 'earned')

@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'test', 'score', 'max_score', 'created_at')
    list_filter = ('test',)
    inlines = [AttemptAnswerInline]