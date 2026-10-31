from django.urls import path
from . import views

app_name = 'quotations'

urlpatterns = [
    path('', views.quotation_list, name='quotation_list'),
    path('create/', views.quotation_create, name='quotation_create'),
    path('<int:pk>/', views.quotation_detail, name='quotation_detail'),
    path('<int:pk>/edit/', views.quotation_edit, name='quotation_edit'),
    path('<int:pk>/send/', views.quotation_send, name='quotation_send'),
    path('<int:pk>/accept/', views.quotation_accept, name='quotation_accept'),
    path('<int:pk>/reject/', views.quotation_reject, name='quotation_reject'),
]
