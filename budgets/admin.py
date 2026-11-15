from django.contrib import admin

from .models import Budget, Cost


class CostInline(admin.TabularInline):
    model = Cost
    extra = 0


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'parent', 'setup', 'owner', 'amount', 'active']
    list_filter = ['active', 'setup']
    search_fields = ['number', 'name']
    inlines = [CostInline]
