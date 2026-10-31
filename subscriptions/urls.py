from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.subscription_list, name='subscription_list'),
    path('<int:pk>/', views.subscription_detail, name='subscription_detail'),
    path('<int:pk>/pause/', views.subscription_pause, name='subscription_pause'),
    path('<int:pk>/resume/', views.subscription_resume, name='subscription_resume'),
    path('<int:pk>/cancel/', views.subscription_cancel, name='subscription_cancel'),
]
