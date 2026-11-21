from django.urls import path
from . import views

app_name = 'quiz'

urlpatterns = [
    path('', views.home, name='home'),

    # ученик
    path('cabinet/', views.cabinet, name='cabinet'),
    path('assignment/<int:assignment_id>/', views.take_assignment, name='take'),
    path('result/<int:attempt_id>/', views.attempt_result, name='attempt_result'),

    # преподаватель
    path('teacher/results/', views.results, name='results'),
    path('teacher/results/export/', views.export_results, name='export_results'),
]
