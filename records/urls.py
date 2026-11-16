"""Included at the top: a record's own pages under /records/, the assets (the records with an asset tag) under /assets/."""
from django.urls import path

from . import views

app_name = 'records'

urlpatterns = [
    path('records/<int:pk>/', views.record, name='record'),
    path('records/<int:pk>/edit/', views.record_form, name='edit'),
    path('records/<int:pk>/brief/', views.record_brief, name='brief'),
    path('records/<int:pk>/act/', views.act, name='act'),
    path('records/<int:pk>/checklist/', views.checklist, name='checklist'),
    path('assets/', views.asset_list, name='assets'),
    path('assets/new/', views.record_form, name='new'),
    path('assets/fields/', views.fields, name='fields'),
    path('assets/fields/<int:pk>/', views.fields, name='field_edit'),
    path('assets/fields/<int:pk>/delete/', views.field_delete, name='field_delete'),
    path('assets/fields/<int:pk>/move/', views.field_move, name='field_move'),
]
