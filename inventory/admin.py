from django.contrib import admin

from .models import Category, Location, Movement, ItemDefinition, Vendor


@admin.register(ItemDefinition)
class DefinitionAdmin(admin.ModelAdmin):
    list_display = ['number', 'description', 'category', 'manufacturer', 'vendor', 'minimum', 'active']
    list_filter = ['active', 'category', 'vendor']
    search_fields = ['number', 'description', 'manufacturer', 'mpn', 'vendor_number']


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'email', 'phone', 'active']
    search_fields = ['name', 'code']


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ['at', 'definition', 'kind', 'quantity', 'source', 'target', 'user', 'reference']
    list_filter = ['kind']
    search_fields = ['definition__number', 'reference', 'note']

    def has_change_permission(self, request, obj=None):   # the history of stock is kept as it happened
        return False


admin.site.register([Category, Location])
