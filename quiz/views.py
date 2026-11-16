import random

from django.shortcuts import render, redirect, get_object_or_404

from .checking import check_question
from .models import Test, Attempt, AttemptAnswer


def test_list(request):
    tests = Test.objects.all()
    return render(request, 'quiz/test_list.html', {'tests': tests})


def test_detail(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    questions = list(
        test.questions.prefetch_related('choices', 'pairs', 'accepted_answers')
    )

    if request.method == 'POST':
        attempt = Attempt.objects.create(
            test=test,
            student_name=request.POST.get('student_name', '').strip()[:100],
        )
        total = 0
        max_total = 0
        for q in questions:
            earned, given, correct = check_question(q, request.POST)
            AttemptAnswer.objects.create(
                attempt=attempt, question=q,
                given=given, correct_text=correct, earned=earned,
            )
            total += earned
            max_total += q.points

        attempt.score = round(total, 2)
        attempt.max_score = max_total
        attempt.save()
        return redirect('quiz:attempt_result', attempt_id=attempt.id)

    # Для соотнесения перемешиваем правые части, чтобы они не шли по порядку
    for q in questions:
        if q.qtype == 'match':
            pairs = list(q.pairs.all())
            q.shuffled_rights = random.sample(pairs, len(pairs))

    return render(request, 'quiz/test_detail.html', {
        'test': test,
        'questions': questions,
    })


def attempt_result(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    answers = attempt.answers.select_related('question').order_by(
        'question__order', 'question__id'
    )
    percent = round(attempt.score / attempt.max_score * 100) if attempt.max_score else 0
    return render(request, 'quiz/attempt_result.html', {
        'attempt': attempt,
        'answers': answers,
        'percent': percent,
    })