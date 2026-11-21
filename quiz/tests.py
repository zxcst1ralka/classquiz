from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .checking import normalize_text, parse_number, validate_question
from .models import (
    AcceptedAnswer, Assignment, Attempt, Choice, MatchPair,
    Question, StudentGroup, Test,
)
from .services import build_results

User = get_user_model()
PASSWORD = 'pass12345'


class QuizFixture(TestCase):
    """Общие данные для проверок: тест из пяти вопросов, группа, два ученика, преподаватель."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user('teacher', password=PASSWORD, is_staff=True)
        cls.anna = User.objects.create_user(
            'anna', password=PASSWORD, first_name='Анна', last_name='Иванова')
        cls.boris = User.objects.create_user('boris', password=PASSWORD)

        cls.test = Test.objects.create(title='Проверочный', description='Тест для проверки')

        # 1 балл: один ответ
        cls.q_single = Question.objects.create(
            test=cls.test, text='Столица Франции?', qtype='single', points=1, order=1,
            comment='Париж, конечно.')
        cls.c_paris = Choice.objects.create(question=cls.q_single, text='Париж', is_correct=True)
        cls.c_rome = Choice.objects.create(question=cls.q_single, text='Рим')

        # 2 балла: несколько ответов
        cls.q_multi = Question.objects.create(
            test=cls.test, text='Какие числа чётные?', qtype='multiple', points=2, order=2)
        cls.c_2 = Choice.objects.create(question=cls.q_multi, text='2', is_correct=True)
        cls.c_4 = Choice.objects.create(question=cls.q_multi, text='4', is_correct=True)
        cls.c_3 = Choice.objects.create(question=cls.q_multi, text='3')

        # 1 балл: ввод слова
        cls.q_text = Question.objects.create(
            test=cls.test, text='Домашнее животное, которое мяукает?', qtype='text', points=1, order=3)
        AcceptedAnswer.objects.create(question=cls.q_text, value='кошка')
        AcceptedAnswer.objects.create(question=cls.q_text, value='кот')

        # 1 балл: ввод числа
        cls.q_num = Question.objects.create(
            test=cls.test, text='Чему равно 7 / 2?', qtype='number', points=1, order=4)
        AcceptedAnswer.objects.create(question=cls.q_num, value='3.5')

        # 3 балла: соотнесение
        cls.q_match = Question.objects.create(
            test=cls.test, text='Соотнесите страны и столицы', qtype='match', points=3, order=5)
        cls.pairs = [
            MatchPair.objects.create(question=cls.q_match, left='Франция', right='Париж'),
            MatchPair.objects.create(question=cls.q_match, left='Япония', right='Токио'),
            MatchPair.objects.create(question=cls.q_match, left='Египет', right='Каир'),
        ]
        cls.max_score = 8

        cls.group = StudentGroup.objects.create(name='8А')
        cls.group.students.add(cls.anna)
        cls.assignment = Assignment.objects.create(
            test=cls.test, group=cls.group, due_date=timezone.now() + timedelta(days=3))

    # --- помощники ---
    def login(self, username):
        self.assertTrue(self.client.login(username=username, password=PASSWORD))

    def perfect_post(self):
        data = {
            f'q_{self.q_single.id}': str(self.c_paris.id),
            f'q_{self.q_multi.id}': [str(self.c_2.id), str(self.c_4.id)],
            f'q_{self.q_text.id}': '  КОШКА ',
            f'q_{self.q_num.id}': '3,5',
        }
        for p in self.pairs:
            data[f'q_{self.q_match.id}_{p.id}'] = str(p.id)
        return data

    def take_url(self):
        return reverse('quiz:take', args=[self.assignment.id])

    def anna_cell(self):
        """Ячейка таблицы результатов для Анны и единственного назначенного теста."""
        row = next(r for r in build_results()['rows'] if r['student'] == self.anna)
        return row['cells'][0]


class AccessTests(QuizFixture):
    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(self.client.get('/'), reverse('login'))

    def test_login_form_works_and_leads_to_cabinet(self):
        resp = self.client.post(reverse('login'), {'username': 'anna', 'password': PASSWORD})
        self.assertRedirects(resp, '/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/'), reverse('quiz:cabinet'))

    def test_wrong_password_shows_error(self):
        resp = self.client.post(reverse('login'), {'username': 'anna', 'password': 'wrong'})
        self.assertContains(resp, 'Неверный логин или пароль')

    def test_teacher_home_is_results(self):
        self.login('teacher')
        self.assertRedirects(self.client.get('/'), reverse('quiz:results'))

    def test_student_cannot_open_teacher_pages(self):
        self.login('anna')
        self.assertEqual(self.client.get(reverse('quiz:results')).status_code, 403)
        self.assertEqual(self.client.get(reverse('quiz:export_results')).status_code, 403)

    def test_anonymous_cannot_open_teacher_pages(self):
        url = reverse('quiz:results')
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_logout_by_post(self):
        self.login('anna')
        resp = self.client.post(reverse('logout'))
        self.assertRedirects(resp, reverse('login'))


class TakeTestTests(QuizFixture):
    def test_cabinet_lists_assignment(self):
        self.login('anna')
        resp = self.client.get(reverse('quiz:cabinet'))
        self.assertContains(resp, 'Проверочный')
        self.assertContains(resp, 'Пройти тест')
        self.assertEqual(resp.context['waiting'], 1)
        self.assertEqual(resp.context['debts'], 0)

    def test_test_page_shows_all_question_types(self):
        self.login('anna')
        resp = self.client.get(self.take_url())
        self.assertEqual(resp.status_code, 200)
        for text in ('Столица Франции?', 'Какие числа чётные?', 'Чему равно 7 / 2?',
                     'Соотнесите страны и столицы', 'Сдать тест'):
            self.assertContains(resp, text)

    def test_perfect_answers_give_full_score(self):
        self.login('anna')
        resp = self.client.post(self.take_url(), self.perfect_post())
        attempt = Attempt.objects.get()
        self.assertRedirects(resp, reverse('quiz:attempt_result', args=[attempt.id]))
        self.assertEqual(attempt.score, self.max_score)
        self.assertEqual(attempt.max_score, self.max_score)
        self.assertEqual(attempt.user, self.anna)
        self.assertEqual(attempt.assignment, self.assignment)
        self.assertFalse(attempt.is_late)
        self.assertEqual(attempt.answers.count(), 5)

    def test_result_page_shows_correct_answers_and_comment(self):
        self.login('anna')
        self.client.post(self.take_url(), {})
        attempt = Attempt.objects.get()
        resp = self.client.get(reverse('quiz:attempt_result', args=[attempt.id]))
        self.assertContains(resp, 'Париж')                       # правильный ответ
        self.assertContains(resp, 'Комментарий преподавателя')
        self.assertContains(resp, 'Париж, конечно.')

    def test_empty_answers_give_zero(self):
        self.login('anna')
        self.client.post(self.take_url(), {})
        attempt = Attempt.objects.get()
        self.assertEqual(attempt.score, 0)

    def test_wrong_answers_give_zero(self):
        self.login('anna')
        data = self.perfect_post()
        data[f'q_{self.q_single.id}'] = str(self.c_rome.id)
        data[f'q_{self.q_multi.id}'] = [str(self.c_2.id)]                 # не весь набор
        data[f'q_{self.q_text.id}'] = 'собака'
        data[f'q_{self.q_num.id}'] = '4'
        for p in self.pairs:
            data[f'q_{self.q_match.id}_{p.id}'] = ''
        self.client.post(self.take_url(), data)
        self.assertEqual(Attempt.objects.get().score, 0)

    def test_multiple_requires_exact_set(self):
        self.login('anna')
        data = self.perfect_post()
        data[f'q_{self.q_multi.id}'] = [str(self.c_2.id), str(self.c_4.id), str(self.c_3.id)]
        self.client.post(self.take_url(), data)
        self.assertEqual(Attempt.objects.get().score, self.max_score - 2)

    def test_match_gives_partial_score(self):
        self.login('anna')
        data = self.perfect_post()
        # третью пару путаем: Египет → Токио
        data[f'q_{self.q_match.id}_{self.pairs[2].id}'] = str(self.pairs[1].id)
        self.client.post(self.take_url(), data)
        self.assertEqual(Attempt.objects.get().score, self.max_score - 1)

    def test_text_answer_accepts_any_variant_ignoring_case_and_yo(self):
        self.login('anna')
        data = self.perfect_post()
        data[f'q_{self.q_text.id}'] = 'КоТ'
        self.client.post(self.take_url(), data)
        self.assertEqual(Attempt.objects.get().score, self.max_score)

    def test_number_accepts_dot_and_comma(self):
        for value in ('3.5', '3,5', ' 3,50 '):
            Attempt.objects.all().delete()
            self.client.logout()
            self.login('anna')
            data = self.perfect_post()
            data[f'q_{self.q_num.id}'] = value
            self.client.post(self.take_url(), data)
            self.assertEqual(Attempt.objects.get().score, self.max_score, value)

    def test_assignment_can_be_submitted_only_once(self):
        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        resp = self.client.post(self.take_url(), self.perfect_post())
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(self.take_url())
        self.assertRedirects(resp, reverse('quiz:attempt_result', args=[Attempt.objects.get().id]))

    def test_student_outside_group_cannot_open_assignment(self):
        self.login('boris')
        self.assertEqual(self.client.get(self.take_url()).status_code, 404)
        self.assertEqual(self.client.post(self.take_url(), self.perfect_post()).status_code, 404)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_result_is_private(self):
        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        url = reverse('quiz:attempt_result', args=[Attempt.objects.get().id])
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.logout()
        self.login('boris')
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.logout()
        self.login('teacher')
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)   # на страницу входа


class DeadlineTests(QuizFixture):
    def make_overdue(self):
        self.assignment.due_date = timezone.now() - timedelta(days=1)
        self.assignment.save()

    def test_not_submitted_after_deadline_is_debt(self):
        self.make_overdue()
        self.login('anna')
        resp = self.client.get(reverse('quiz:cabinet'))
        self.assertEqual(resp.context['debts'], 1)
        self.assertContains(resp, 'Долг')
        cell = self.anna_cell()
        self.assertEqual(cell['status'], 'debt')

    def test_late_submission_is_accepted_and_marked(self):
        self.make_overdue()
        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        attempt = Attempt.objects.get()
        self.assertTrue(attempt.is_late)
        resp = self.client.get(reverse('quiz:cabinet'))
        self.assertEqual(resp.context['debts'], 0)
        self.assertContains(resp, 'Сдано с опозданием')
        self.assertEqual(self.anna_cell()['status'], 'late')

    def test_on_time_submission_status_done(self):
        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        cell = self.anna_cell()
        self.assertEqual(cell['status'], 'done')

    def test_waiting_status_before_deadline(self):
        cell = self.anna_cell()
        self.assertEqual(cell['status'], 'waiting')


class ResultsAndExportTests(QuizFixture):
    def test_results_page_for_teacher(self):
        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        self.client.logout()

        self.login('teacher')
        resp = self.client.get(reverse('quiz:results'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Анна Иванова')
        self.assertContains(resp, 'Проверочный')
        self.assertContains(resp, '8/8')

    def test_results_filter_by_group(self):
        other = StudentGroup.objects.create(name='9Б')
        other.students.add(self.boris)
        self.login('teacher')
        resp = self.client.get(reverse('quiz:results'), {'group': self.group.id})
        names = [r['name'] for r in resp.context['rows']]
        self.assertEqual(names, ['Анна Иванова'])
        resp = self.client.get(reverse('quiz:results'), {'group': 'абракадабра'})
        self.assertEqual(resp.status_code, 200)

    def test_results_without_assignments_shows_hint(self):
        Assignment.objects.all().delete()
        self.login('teacher')
        resp = self.client.get(reverse('quiz:results'))
        self.assertContains(resp, 'ни один тест не назначен')

    def test_excel_export(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest('openpyxl не установлен')

        self.login('anna')
        self.client.post(self.take_url(), self.perfect_post())
        self.client.logout()

        self.login('teacher')
        resp = self.client.get(reverse('quiz:export_results'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('.xlsx', resp['Content-Disposition'])

        wb = openpyxl.load_workbook(BytesIO(resp.content))
        self.assertEqual(wb.sheetnames, ['Результаты', 'Попытки'])
        ws = wb['Результаты']
        self.assertEqual(ws['A1'].value, 'Ученик')
        self.assertEqual(ws['C1'].value, 'Проверочный')
        rows = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
        self.assertEqual(rows['Анна Иванова'][2], 8)          # баллы за тест
        self.assertEqual(rows['Анна Иванова'][3], 8)          # всего баллов
        self.assertIsNone(rows['boris'][2])                   # тест ему не назначен
        attempts = list(wb['Попытки'].iter_rows(min_row=2, values_only=True))
        self.assertEqual(attempts[0][0], 'Анна Иванова')


class CheckingUnitTests(TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text('  ЁЖ   Ик '), 'еж ик')
        self.assertEqual(normalize_text(None), '')

    def test_parse_number(self):
        self.assertEqual(parse_number('3,5'), 3.5)
        self.assertEqual(parse_number(' 1 000 '), 1000)
        self.assertIsNone(parse_number('abc'))
        self.assertIsNone(parse_number('nan'))
        self.assertIsNone(parse_number(''))


class ValidateQuestionTests(QuizFixture):
    def test_good_questions_have_no_problems(self):
        for q in (self.q_single, self.q_multi, self.q_text, self.q_num, self.q_match):
            self.assertIsNone(validate_question(q), q.text)

    def test_detects_problems(self):
        t = self.test
        no_correct = Question.objects.create(test=t, text='a', qtype='single')
        Choice.objects.create(question=no_correct, text='x')
        Choice.objects.create(question=no_correct, text='y')
        self.assertIn('правильный', validate_question(no_correct))

        two_correct = Question.objects.create(test=t, text='b', qtype='single')
        Choice.objects.create(question=two_correct, text='x', is_correct=True)
        Choice.objects.create(question=two_correct, text='y', is_correct=True)
        self.assertIn('только один', validate_question(two_correct))

        empty_text = Question.objects.create(test=t, text='c', qtype='text')
        self.assertIn('Допустимые ответы', validate_question(empty_text))

        bad_number = Question.objects.create(test=t, text='d', qtype='number')
        AcceptedAnswer.objects.create(question=bad_number, value='много')
        self.assertIn('не является числом', validate_question(bad_number))

        one_pair = Question.objects.create(test=t, text='e', qtype='match')
        MatchPair.objects.create(question=one_pair, left='a', right='b')
        self.assertIn('две пары', validate_question(one_pair))


class AdminPagesTests(QuizFixture):
    """Открываем страницы админки: так ловятся ошибки в настройках admin.py."""

    def test_admin_pages_open(self):
        admin_user = User.objects.create_superuser('boss', password=PASSWORD)
        self.client.force_login(admin_user)
        pages = [
            reverse('admin:index'),
            reverse('admin:quiz_test_changelist'),
            reverse('admin:quiz_question_changelist'),
            reverse('admin:quiz_question_add'),
            reverse('admin:quiz_question_change', args=[self.q_single.id]),
            reverse('admin:quiz_studentgroup_changelist'),
            reverse('admin:quiz_studentgroup_change', args=[self.group.id]),
            reverse('admin:quiz_assignment_changelist'),
            reverse('admin:quiz_assignment_add'),
            reverse('admin:quiz_attempt_changelist'),
        ]
        for url in pages:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_warns_about_bad_question(self):
        """Сохраняем вопрос без правильного ответа: админка должна предупредить."""
        admin_user = User.objects.create_superuser('boss', password=PASSWORD)
        self.client.force_login(admin_user)
        data = {
            'test': self.test.id, 'text': 'Без ответа', 'qtype': 'single',
            'points': 1, 'order': 9, 'comment': '',
            'choices-TOTAL_FORMS': 0, 'choices-INITIAL_FORMS': 0,
            'choices-MIN_NUM_FORMS': 0, 'choices-MAX_NUM_FORMS': 1000,
            'accepted_answers-TOTAL_FORMS': 0, 'accepted_answers-INITIAL_FORMS': 0,
            'accepted_answers-MIN_NUM_FORMS': 0, 'accepted_answers-MAX_NUM_FORMS': 1000,
            'pairs-TOTAL_FORMS': 0, 'pairs-INITIAL_FORMS': 0,
            'pairs-MIN_NUM_FORMS': 0, 'pairs-MAX_NUM_FORMS': 1000,
        }
        resp = self.client.post(reverse('admin:quiz_question_add'), data, follow=True)
        self.assertContains(resp, 'есть проблема')
