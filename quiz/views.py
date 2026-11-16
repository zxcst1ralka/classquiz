import random

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

from .models import Test


def test_list(request):
    tests = Test.objects.all()
    return render(request, 'quiz/test_list.html', {'tests': tests})


def test_detail(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if request.method == 'POST':
        # Временная заглушка, проверку сделаем на шаге 3
        return HttpResponse('Ответы получены. Проверку добавим на следующем шаге.')

    questions = list(
        test.questions.prefetch_related('choices', 'pairs')
    )
    # Для соотнесения перемешиваем правые части, чтобы они не шли по порядку
    for q in questions:
        if q.qtype == 'match':
            q.shuffled_rights = random.sample(list(q.pairs.all()), len(q.pairs.all()))

    return render(request, 'quiz/test_detail.html', {
        'test': test,
        'questions': questions,
    })