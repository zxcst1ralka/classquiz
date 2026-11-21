from django.conf import settings
from django.db import models


class Test(models.Model):
    title = models.CharField('Название', max_length=200)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        verbose_name = 'Тест'
        verbose_name_plural = 'Тесты'

    def __str__(self):
        return self.title


class Question(models.Model):
    SINGLE = 'single'
    MULTIPLE = 'multiple'
    TEXT = 'text'
    NUMBER = 'number'
    MATCH = 'match'
    TYPES = [
        (SINGLE, 'Один ответ'),
        (MULTIPLE, 'Несколько ответов'),
        (TEXT, 'Ввод слова'),
        (NUMBER, 'Ввод числа'),
        (MATCH, 'Соотнесение'),
    ]

    test = models.ForeignKey(
        Test, on_delete=models.CASCADE,
        related_name='questions', verbose_name='Тест'
    )
    text = models.TextField('Текст вопроса')
    qtype = models.CharField('Тип вопроса', max_length=10, choices=TYPES, default=SINGLE)
    points = models.PositiveIntegerField('Баллы за вопрос', default=1)
    comment = models.TextField('Комментарий преподавателя', blank=True)
    order = models.PositiveIntegerField('Порядок', default=1)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.text[:50]} ({self.get_qtype_display()})'


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name='choices', verbose_name='Вопрос'
    )
    text = models.CharField('Вариант ответа', max_length=300)
    is_correct = models.BooleanField('Правильный', default=False)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответа'

    def __str__(self):
        return self.text


class AcceptedAnswer(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name='accepted_answers', verbose_name='Вопрос'
    )
    value = models.CharField('Допустимый ответ', max_length=200)

    class Meta:
        verbose_name = 'Допустимый ответ'
        verbose_name_plural = 'Допустимые ответы'

    def __str__(self):
        return self.value


class MatchPair(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name='pairs', verbose_name='Вопрос'
    )
    left = models.CharField('Левая часть', max_length=200)
    right = models.CharField('Правая часть', max_length=200)

    class Meta:
        verbose_name = 'Пара'
        verbose_name_plural = 'Пары для соотнесения'

    def __str__(self):
        return f'{self.left} → {self.right}'


class StudentGroup(models.Model):
    """Группа учеников. Тест назначается группе целиком."""
    name = models.CharField('Название группы', max_length=100, unique=True)
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name='student_groups', verbose_name='Ученики',
        limit_choices_to={'is_staff': False},
    )

    class Meta:
        verbose_name = 'Группа учеников'
        verbose_name_plural = 'Группы учеников'
        ordering = ['name']

    def __str__(self):
        return self.name


class Assignment(models.Model):
    """Назначение: «этот тест нужно сдать этой группе до такого-то срока»."""
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE,
        related_name='assignments', verbose_name='Тест'
    )
    group = models.ForeignKey(
        StudentGroup, on_delete=models.CASCADE,
        related_name='assignments', verbose_name='Группа'
    )
    due_date = models.DateTimeField('Сдать до')
    created_at = models.DateTimeField('Назначено', auto_now_add=True)

    class Meta:
        verbose_name = 'Назначение теста'
        verbose_name_plural = 'Назначения тестов'
        ordering = ['due_date']
        constraints = [
            models.UniqueConstraint(
                fields=['test', 'group'], name='unique_test_per_group'
            ),
        ]

    def __str__(self):
        return f'{self.test.title} → {self.group.name} (до {self.due_date:%d.%m.%Y})'


class Attempt(models.Model):
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE,
        related_name='attempts', verbose_name='Тест'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Пользователь'
    )
    assignment = models.ForeignKey(
        Assignment, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='attempts',
        verbose_name='Задание'
    )
    student_name = models.CharField('Имя ученика', max_length=100, blank=True)
    score = models.FloatField('Набрано баллов', default=0)
    max_score = models.FloatField('Максимум баллов', default=0)
    created_at = models.DateTimeField('Сдан', auto_now_add=True)

    class Meta:
        verbose_name = 'Попытка'
        verbose_name_plural = 'Попытки'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student_name} — {self.test.title}'

    @property
    def percent(self):
        return round(self.score / self.max_score * 100) if self.max_score else 0

    @property
    def is_late(self):
        """Сдано после срока (только для попыток, привязанных к заданию)."""
        return bool(self.assignment_id and self.created_at > self.assignment.due_date)


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE,
        related_name='answers', verbose_name='Попытка'
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, verbose_name='Вопрос'
    )
    given = models.TextField('Ответ ученика', blank=True)
    correct_text = models.TextField('Правильный ответ', blank=True)
    earned = models.FloatField('Баллы', default=0)

    class Meta:
        verbose_name = 'Ответ на вопрос'
        verbose_name_plural = 'Ответы на вопросы'
