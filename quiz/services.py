from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .checking import check_question
from .models import Assignment, Attempt, AttemptAnswer, StudentGroup


def display_name(user):
    """Как показывать ученика: «Имя Фамилия», а если не заполнено, то логин."""
    return user.get_full_name() or user.username


def build_results(group=None):
    """
    Собирает данные для таблицы «ученик × тест».

    Статусы ячейки:
      done    - сдано вовремя
      late    - сдано после срока
      debt    - не сдано, срок прошёл (задолженность)
      waiting - не сдано, срок ещё не наступил
      none    - тест этому ученику не назначен
    """
    User = get_user_model()
    now = timezone.now()

    if group:
        students = group.students.filter(is_active=True)
        assignments = Assignment.objects.filter(group=group)
    else:
        students = User.objects.filter(is_active=True, is_staff=False)
        assignments = Assignment.objects.all()

    students = list(students.order_by('last_name', 'first_name', 'username'))
    assignments = list(assignments.select_related('test', 'group'))
    student_ids = [s.id for s in students]

    # В каких группах состоит каждый ученик
    group_ids_of = defaultdict(set)
    group_names_of = defaultdict(list)
    for g in StudentGroup.objects.prefetch_related('students'):
        for u in g.students.all():
            group_ids_of[u.id].add(g.id)
            group_names_of[u.id].append(g.name)

    # Какие тесты попадают в таблицу и когда их нужно сдать
    tests_by_id = {}
    due_by_group_test = {}
    for a in assignments:
        tests_by_id[a.test_id] = a.test
        due_by_group_test[(a.group_id, a.test_id)] = a.due_date
    tests = sorted(tests_by_id.values(), key=lambda t: t.title.lower())

    # Последняя попытка каждого ученика по каждому тесту
    attempts = list(
        Attempt.objects
        .filter(user_id__in=student_ids, test_id__in=list(tests_by_id))
        .select_related('test', 'assignment', 'user')
        .order_by('created_at')
    )
    last_attempt = {}
    for at in attempts:
        last_attempt[(at.user_id, at.test_id)] = at

    rows = []
    for s in students:
        cells = []
        total = total_max = debts = 0
        for t in tests:
            dues = [
                due_by_group_test[(gid, t.id)]
                for gid in group_ids_of[s.id]
                if (gid, t.id) in due_by_group_test
            ]
            due = min(dues) if dues else None
            attempt = last_attempt.get((s.id, t.id))

            if attempt:
                status = 'late' if attempt.is_late else 'done'
                total += attempt.score
                total_max += attempt.max_score
            elif due and due < now:
                status = 'debt'
                debts += 1
            elif due:
                status = 'waiting'
            else:
                status = 'none'

            cells.append({'test': t, 'status': status, 'attempt': attempt, 'due': due})

        rows.append({
            'student': s,
            'name': display_name(s),
            'groups': ', '.join(group_names_of[s.id]),
            'cells': cells,
            'total': round(total, 2),
            'total_max': round(total_max, 2),
            'debts': debts,
        })

    attempts.sort(key=lambda a: a.created_at, reverse=True)
    return {'tests': tests, 'rows': rows, 'attempts': attempts}


def submit_attempt(user, assignment, post, questions=None):
    """
    Сохраняет сдачу теста: проверяет каждый вопрос, считает баллы, записывает ответы.
    `post` это данные формы (request.POST). Возвращает созданную попытку.
    """
    test = assignment.test
    if questions is None:
        questions = list(test.questions.prefetch_related('choices', 'pairs', 'accepted_answers'))

    with transaction.atomic():
        attempt = Attempt.objects.create(
            test=test,
            user=user,
            assignment=assignment,
            student_name=display_name(user)[:100],
        )
        total = 0
        max_total = 0
        for q in questions:
            earned, given, correct = check_question(q, post)
            AttemptAnswer.objects.create(
                attempt=attempt, question=q,
                given=given, correct_text=correct, earned=earned,
            )
            total += earned
            max_total += q.points

        attempt.score = round(total, 2)
        attempt.max_score = max_total
        attempt.save()
    return attempt
