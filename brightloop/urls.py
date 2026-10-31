from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

urlpatterns = [
    path('', lambda request: redirect('dashboard:index'), name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('products/', include('products.urls')),
    path('quotations/', include('quotations.urls')),
    path('subscriptions/', include('subscriptions.urls')),
    path('billing/', include('billing.urls')),
]
