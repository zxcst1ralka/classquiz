import math


def normalize_text(value):
    """Приводит текст к единому виду: без лишних пробелов, в нижнем регистре, ё -> е."""
    value = (value or '').strip().lower().replace('ё', 'е')
    return ' '.join(value.split())


def parse_number(value):
    """Превращает строку в число. Понимает и запятую, и точку. Если не число, вернёт None."""
    try:
        number = float((value or '').strip().replace(',', '.').replace(' ', ''))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _check_choices(q, post, multiple):
    key = f'q_{q.id}'
    raw = post.getlist(key) if multiple else [post.get(key, '')]
    given_ids = {int(x) for x in raw if x.isdigit()}

    choices = list(q.choices.all())
    correct_ids = {c.id for c in choices if c.is_correct}

    given_text = '; '.join(c.text for c in choices if c.id in given_ids) or '— нет ответа —'
    correct_text = '; '.join(c.text for c in choices if c.id in correct_ids)
    earned = q.points if correct_ids and given_ids == correct_ids else 0
    return earned, given_text, correct_text


def _check_text(q, post):
    given = post.get(f'q_{q.id}', '').strip()
    accepted = [a.value for a in q.accepted_answers.all()]
    allowed = {normalize_text(a) for a in accepted}

    ok = bool(given) and normalize_text(given) in allowed
    return (q.points if ok else 0), (given or '— нет ответа —'), ' / '.join(accepted)


def _check_number(q, post):
    given = post.get(f'q_{q.id}', '').strip()
    accepted = [a.value for a in q.accepted_answers.all()]

    given_num = parse_number(given)
    ok = False
    if given_num is not None:
        for a in accepted:
            a_num = parse_number(a)
            if a_num is not None and math.isclose(given_num, a_num, abs_tol=1e-9):
                ok = True
                break
    return (q.points if ok else 0), (given or '— нет ответа —'), ' / '.join(accepted)


def _check_match(q, post):
    pairs = list(q.pairs.all())
    right_by_id = {p.id: p.right for p in pairs}

    correct_count = 0
    given_lines = []
    correct_lines = []
    for p in pairs:
        chosen = post.get(f'q_{q.id}_{p.id}', '')
        chosen_right = right_by_id.get(int(chosen)) if chosen.isdigit() else None
        if chosen_right == p.right:
            correct_count += 1
        given_lines.append(f'{p.left} → {chosen_right or "—"}')
        correct_lines.append(f'{p.left} → {p.right}')

    earned = q.points * correct_count / len(pairs) if pairs else 0
    return round(earned, 2), '\n'.join(given_lines), '\n'.join(correct_lines)


def check_question(q, post):
    """Проверяет один вопрос. Возвращает (баллы, ответ ученика текстом, правильный ответ текстом)."""
    if q.qtype == 'single':
        return _check_choices(q, post, multiple=False)
    if q.qtype == 'multiple':
        return _check_choices(q, post, multiple=True)
    if q.qtype == 'text':
        return _check_text(q, post)
    if q.qtype == 'number':
        return _check_number(q, post)
    if q.qtype == 'match':
        return _check_match(q, post)
    return 0, '', ''

def validate_question(q):
    """
    Проверяет, что вопрос заполнен правильно.
    Возвращает текст проблемы или None, если всё в порядке.
    """
    if q.qtype in ('single', 'multiple'):
        choices = list(q.choices.all())
        correct = [c for c in choices if c.is_correct]
        if len(choices) < 2:
            return 'нужно минимум два варианта ответа.'
        if not correct:
            return 'не отмечен ни один правильный вариант.'
        if q.qtype == 'single' and len(correct) > 1:
            return 'для типа «Один ответ» правильным должен быть только один вариант.'

    elif q.qtype in ('text', 'number'):
        answers = list(q.accepted_answers.all())
        if not answers:
            return 'не заполнен блок «Допустимые ответы» (иначе любой ответ ученика будет неверным).'
        if q.qtype == 'number':
            bad = [a.value for a in answers if parse_number(a.value) is None]
            if bad:
                return 'в числовом вопросе допустимый ответ не является числом: ' + ', '.join(bad)

    elif q.qtype == 'match':
        if q.pairs.count() < 2:
            return 'для соотнесения нужно минимум две пары.'

    return None
