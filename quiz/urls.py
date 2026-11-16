from django.urls import path
from . import views

app_name = 'quiz'

urlpatterns = [
    path('', views.test_list, name='test_list'),
    path('test/<int:test_id>/', views.test_detail, name='test_detail'),
    path('result/<int:attempt_id>/', views.attempt_result, name='attempt_result'),
]