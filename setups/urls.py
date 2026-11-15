from django.urls import path

from . import views

app_name = 'setups'

urlpatterns = [
    path('', views.setup_list, name='list'),
    path('new/', views.setup_form, name='new'),
    path('<int:pk>/', views.setup, name='setup'),
    path('<int:pk>/edit/', views.setup_form, name='edit'),
    path('<int:pk>/copy/', views.copy, name='copy'),
    path('<int:pk>/change/', views.change, name='change'),
    path('<int:pk>/needs/', views.needs, name='needs'),
]
