from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('item-definitions/', views.definitions, name='definitions'),
    path('item-definitions/new/', views.definition_form, name='definition_new'),
    path('item-definitions/import/', views.definitions_import, name='definitions_import'),
    path('item-definitions/find/', views.find, name='find'),
    path('item-definitions/<int:pk>/', views.definition, name='definition'),
    path('item-definitions/<int:pk>/brief/', views.definition_brief, name='definition_brief'),
    path('item-definitions/<int:pk>/edit/', views.definition_form, name='definition_edit'),
    path('item-definitions/<int:pk>/stock/', views.definition_stock, name='definition_stock'),
    path('item-definitions/<int:pk>/reorder/', views.definition_reorder, name='definition_reorder'),
    path('categories/', views.categories, name='categories'),
    path('categories/standard/', views.standard_categories, name='categories_standard'),
    path('categories/<int:pk>/', views.category, name='category'),
    path('categories/<int:pk>/attributes/', views.attribute_form, name='attribute_new'),
    path('categories/<int:pk>/attributes/<int:attribute>/', views.attribute_form, name='attribute_edit'),
    path('categories/<int:pk>/attributes/<int:attribute>/delete/', views.attribute_delete, name='attribute_delete'),
    path('categories/<int:pk>/attributes/<int:attribute>/move/', views.attribute_move, name='attribute_move'),
    path('locations/', views.locations, name='locations'),
    path('locations/new/', views.location_form, name='location_new'),
    path('locations/<int:pk>/', views.location, name='location'),
    path('locations/<int:pk>/edit/', views.location_form, name='location_edit'),
    path('families/', views.families, name='families'),
    path('families/standard/', views.standard_families, name='families_standard'),
    path('families/export/', views.families_export, name='families_export'),
    path('families/import/', views.families_import, name='families_import'),
    path('families/<int:pk>/brief/', views.family_brief, name='family_brief'),
    path('families/<int:pk>/', views.family, name='family'),
    path('families/<int:pk>/connector/', views.connector, name='connector'),
    path('vendors/', views.vendors, name='vendors'),
    path('vendors/new/', views.vendor_form, name='vendor_new'),
    path('vendors/<int:pk>/', views.vendor, name='vendor'),
    path('vendors/<int:pk>/edit/', views.vendor_form, name='vendor_edit'),
]
