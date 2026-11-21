import random
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Assignment, Attempt, StudentGroup
from .services import build_results, submit_attempt

def staff_required(view):
    """
    Страница только для преподавателя (пользователь со статусом «персонал»).
    Незалогиненного отправляет на вход, а ученику показывает «доступ запрещён».
    """
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def home(request):
    """Стартовая страница: отправляет каждого туда, где ему нужно быть."""
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_staff:
        return redirect('quiz:results')
    return redirect('quiz:cabinet')


# ---------------------------------------------------------------- ученик

@login_required
def cabinet(request):
    """Личный кабинет ученика: задания, сроки, долги, баллы."""
    if request.user.is_staff:
        return redirect('quiz:results')

    now = timezone.now()
    assignments = list(
        Assignment.objects
        .filter(group__students=request.user)
        .select_related('test', 'group')
        .distinct()
    )
    attempts = {}
    for at in (Attempt.objects
               .filter(user=request.user, assignment__in=assignments)
               .select_related('assignment').order_by('created_at')):
        attempts[at.assignment_id] = at

    items = []
    debts = waiting = 0
    score_sum = max_sum = 0
    for a in assignments:
        attempt = attempts.get(a.id)
        if attempt:
            status = 'late' if attempt.is_late else 'done'
            score_sum += attempt.score
            max_sum += attempt.max_score
        elif a.due_date < now:
            status = 'debt'
            debts += 1
        else:
            status = 'waiting'
            waiting += 1
        items.append({'assignment': a, 'attempt': attempt, 'status': status})

    # Сначала долги, потом то, что ещё нужно сдать, в конце сданное
    order = {'debt': 0, 'waiting': 1, 'late': 2, 'done': 2}
    items.sort(key=lambda i: (order[i['status']], i['assignment'].due_date))

    return render(request, 'quiz/cabinet.html', {
        'items': items,
        'debts': debts,
        'waiting': waiting,
        'avg_percent': round(score_sum / max_sum * 100) if max_sum else None,
    })


@login_required
def take_assignment(request, assignment_id):
    """Прохождение назначенного теста."""
    if request.user.is_staff:
        return redirect('quiz:results')

    # Открыть можно только задание своей группы
    assignment = get_object_or_404(
        Assignment.objects.select_related('test', 'group'),
        id=assignment_id, group__students=request.user,
    )
    test = assignment.test

    # Каждое задание сдаётся один раз: повторно открыть можно только разбор
    existing = Attempt.objects.filter(user=request.user, assignment=assignment).first()
    if existing:
        return redirect('quiz:attempt_result', attempt_id=existing.id)

    questions = list(
        test.questions.prefetch_related('choices', 'pairs', 'accepted_answers')
    )

    if request.method == 'POST':
        attempt = submit_attempt(request.user, assignment, request.POST, questions)
        return redirect('quiz:attempt_result', attempt_id=attempt.id)

    # Для соотнесения перемешиваем правые части, чтобы они не шли по порядку
    for q in questions:
        if q.qtype == 'match':
            pairs = list(q.pairs.all())
            q.shuffled_rights = random.sample(pairs, len(pairs))

    return render(request, 'quiz/test_detail.html', {
        'test': test,
        'assignment': assignment,
        'questions': questions,
        'is_overdue': assignment.due_date < timezone.now(),
    })


@login_required
def attempt_result(request, attempt_id):
    """Разбор попытки. Видит только сам ученик и преподаватель."""
    attempt = get_object_or_404(
        Attempt.objects.select_related('test', 'assignment'), id=attempt_id
    )
    if not request.user.is_staff and attempt.user_id != request.user.id:
        raise Http404

    answers = attempt.answers.select_related('question').order_by(
        'question__order', 'question__id'
    )
    return render(request, 'quiz/attempt_result.html', {
        'attempt': attempt,
        'answers': answers,
        'percent': attempt.percent,
    })


# ---------------------------------------------------------- преподаватель

def _selected_group(request):
    """Читает ?group=<id> из адреса. Возвращает группу или None."""
    group_id = request.GET.get('group', '')
    if group_id.isdigit():
        return StudentGroup.objects.filter(id=int(group_id)).first()
    return None


@staff_required
def results(request):
    """Таблица результатов: ученики × тесты."""
    group = _selected_group(request)
    data = build_results(group)
    return render(request, 'quiz/results.html', {
        'group': group,
        'groups': StudentGroup.objects.all(),
        'tests': data['tests'],
        'rows': data['rows'],
    })


@staff_required
def export_results(request):
    """Скачивание таблицы результатов в Excel."""
    try:
        from .exports import build_workbook
    except ImportError:
        messages.error(request, 'Не установлена библиотека openpyxl. В терминале выполните: pip install openpyxl')
        return redirect('quiz:results')

    group = _selected_group(request)
    content = build_workbook(build_results(group))

    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    filename = f'results_{timezone.localdate().isoformat()}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
