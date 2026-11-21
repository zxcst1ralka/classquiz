from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone

from quiz.models import (
    AcceptedAnswer, Assignment, Attempt, Choice, MatchPair,
    Question, StudentGroup, Test,
)
from quiz.services import submit_attempt

User = get_user_model()

DEMO_TITLE = 'Демо: общий тест'
OLD_TITLE = 'Демо: прошлая тема'


def make_post(questions, wrong=()):
    """Собирает «ответы ученика»: правильные, а для типов из `wrong` намеренно неправильные."""
    post = QueryDict(mutable=True)
    for q in questions:
        bad = q.qtype in wrong
        if q.qtype == 'single':
            pick = next(c for c in q.choices.all() if c.is_correct != bad)
            post[f'q_{q.id}'] = str(pick.id)
        elif q.qtype == 'multiple':
            correct = [str(c.id) for c in q.choices.all() if c.is_correct]
            post.setlist(f'q_{q.id}', correct[:1] if bad else correct)
        elif q.qtype in ('text', 'number'):
            post[f'q_{q.id}'] = 'не знаю' if bad else q.accepted_answers.first().value
        elif q.qtype == 'match':
            pairs = list(q.pairs.all())
            for i, p in enumerate(pairs):
                target = p
                if bad and i < 2:                 # путаем первые две пары
                    target = pairs[1 - i]
                post[f'q_{q.id}_{p.id}'] = str(target.id)
    return post


class Command(BaseCommand):
    help = 'Создаёт демонстрационные данные: тесты, группу, учеников и несколько сданных работ.'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='demo12345', help='Пароль для демо-аккаунтов.')

    @transaction.atomic
    def handle(self, *args, **options):
        if Test.objects.filter(title=DEMO_TITLE).exists():
            self.stdout.write('Демо-данные уже созданы, ничего не делаю.')
            return

        password = options['password']
        now = timezone.now()

        teacher, _ = User.objects.get_or_create(
            username='teacher',
            defaults={'first_name': 'Преподаватель', 'is_staff': True, 'is_superuser': True},
        )
        teacher.set_password(password)
        teacher.save()

        students = []
        for username, first, last in [('ivan', 'Иван', 'Петров'),
                                      ('maria', 'Мария', 'Соколова'),
                                      ('oleg', 'Олег', 'Смирнов')]:
            user, _ = User.objects.get_or_create(
                username=username, defaults={'first_name': first, 'last_name': last})
            user.set_password(password)
            user.save()
            students.append(user)
        ivan, maria, oleg = students

        group = StudentGroup.objects.create(name='Группа А')
        group.students.set(students)

        # ---- Тест 1: все пять типов вопросов ----
        t1 = Test.objects.create(title=DEMO_TITLE, description='Пример теста со всеми пятью типами вопросов.')

        q = Question.objects.create(test=t1, order=1, qtype='single', points=1,
                                    text='Какая планета ближе всего к Солнцу?',
                                    comment='Меркурий — самая близкая к Солнцу планета.')
        for text, ok in [('Меркурий', True), ('Венера', False), ('Марс', False)]:
            Choice.objects.create(question=q, text=text, is_correct=ok)

        q = Question.objects.create(test=t1, order=2, qtype='multiple', points=2,
                                    text='Выберите все простые числа.',
                                    comment='Простые числа делятся только на 1 и на себя: 2, 3 и 5.')
        for text, ok in [('2', True), ('3', True), ('4', False), ('5', True), ('9', False)]:
            Choice.objects.create(question=q, text=text, is_correct=ok)

        q = Question.objects.create(test=t1, order=3, qtype='text', points=1,
                                    text='Как называется столица России?',
                                    comment='Регистр букв не важен.')
        AcceptedAnswer.objects.create(question=q, value='Москва')

        q = Question.objects.create(test=t1, order=4, qtype='number', points=1,
                                    text='Сколько будет 12 × 7?',
                                    comment='12 × 7 = 10 × 7 + 2 × 7 = 70 + 14 = 84.')
        AcceptedAnswer.objects.create(question=q, value='84')

        q = Question.objects.create(test=t1, order=5, qtype='match', points=3,
                                    text='Соотнесите страны и их столицы.',
                                    comment='Франция — Париж, Япония — Токио, Египет — Каир.')
        for left, right in [('Франция', 'Париж'), ('Япония', 'Токио'), ('Египет', 'Каир')]:
            MatchPair.objects.create(question=q, left=left, right=right)

        # ---- Тест 2: «прошлая тема», срок уже прошёл ----
        t2 = Test.objects.create(title=OLD_TITLE, description='Короткий тест, срок сдачи которого уже прошёл.')
        q = Question.objects.create(test=t2, order=1, qtype='single', points=1,
                                    text='Сколько градусов в прямом угле?')
        for text, ok in [('45', False), ('90', True), ('180', False)]:
            Choice.objects.create(question=q, text=text, is_correct=ok)
        q = Question.objects.create(test=t2, order=2, qtype='number', points=1,
                                    text='Чему равен корень из 144?')
        AcceptedAnswer.objects.create(question=q, value='12')

        a1 = Assignment.objects.create(test=t1, group=group, due_date=now + timedelta(days=5))
        a2 = Assignment.objects.create(test=t2, group=group, due_date=now - timedelta(days=2))

        def qs(test):
            return list(test.questions.prefetch_related('choices', 'pairs', 'accepted_answers'))

        # Иван: первый тест почти идеально (путает соотнесение), второй сдал с опозданием
        submit_attempt(ivan, a1, make_post(qs(t1), wrong=('match',)), qs(t1))
        late = submit_attempt(ivan, a2, make_post(qs(t2)), qs(t2))
        Attempt.objects.filter(pk=late.pk).update(created_at=now - timedelta(hours=5))

        # Мария: первый тест на 4 из 8, второй не сдала (долг)
        submit_attempt(maria, a1, make_post(qs(t1), wrong=('single', 'multiple', 'text')), qs(t1))

        # Олег: ничего не сдавал (первый ещё можно сдать, по второму долг)

        self.stdout.write(self.style.SUCCESS(
            'Демо-данные созданы. Преподаватель: teacher. Ученики: ivan, maria, oleg. '
            f'Пароль у всех: {password}'))
