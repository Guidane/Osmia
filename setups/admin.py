from django.contrib import admin

from .models import Placement, Setup


class PlacementInline(admin.TabularInline):
    model = Placement
    extra = 0


@admin.register(Setup)
class SetupAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'in_project']
    list_filter = ['in_project']
    inlines = [PlacementInline]
