from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('admin/', admin.site.urls),   # administrators: users, and bulk changes to anything
    path('', include('web.urls')),
    path('', include('inventory.urls')),
    path('orders/', include('orders.urls')),
    path('devices/', include('devices.urls')),
    path('harnesses/', include('harnesses.urls')),
    path('setups/', include('setups.urls')),
    re_path(r'^wire-diagrams/(?P<rest>.*)$', RedirectView.as_view(url='/setups/%(rest)s', query_string=True)),   # the old address
    re_path(r'^parts/(?P<rest>.*)$', RedirectView.as_view(url='/item-definitions/%(rest)s', query_string=True)),   # the old address
    path('projects/', include('work.urls')),
    path('budgets/', include('budgets.urls')),
    path('', include('records.urls')),   # /records/Åc and /assets/Åc
    re_path(r'^assets/(?P<pk>[0-9]+)/(?P<rest>.*)$', RedirectView.as_view(url='/records/%(pk)s/%(rest)s', query_string=True)),   # an asset's old address
]
