from django.contrib import admin, messages

from .checking import validate_question
from .models import (
    AcceptedAnswer, Assignment, Attempt, AttemptAnswer,
    Choice, MatchPair, Question, StudentGroup, Test,
)


# ---------------------------------------------------------------- тесты

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
    search_fields = ('title',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'test', 'qtype', 'points', 'order')
    list_filter = ('test', 'qtype')
    search_fields = ('text',)
    inlines = [ChoiceInline, AcceptedAnswerInline, MatchPairInline]

    def save_related(self, request, form, formsets, change):
        """После сохранения проверяем, что вопрос заполнен правильно, и предупреждаем преподавателя."""
        super().save_related(request, form, formsets, change)
        problem = validate_question(form.instance)
        if problem:
            self.message_user(
                request,
                f'Вопрос сохранён, но есть проблема: {problem}',
                level=messages.WARNING,
            )


# ------------------------------------------------- группы и назначения

@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'students_count')
    search_fields = ('name',)
    filter_horizontal = ('students',)

    @admin.display(description='Учеников')
    def students_count(self, obj):
        return obj.students.count()


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('test', 'group', 'due_date')
    list_filter = ('group', 'test')
    date_hierarchy = 'due_date'


# ------------------------------------------------------------ попытки

class AttemptAnswerInline(admin.TabularInline):
    model = AttemptAnswer
    extra = 0
    can_delete = False
    readonly_fields = ('question', 'given', 'correct_text', 'earned')


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'test', 'score', 'max_score', 'created_at')
    list_filter = ('test', 'assignment__group')
    inlines = [AttemptAnswerInline]
