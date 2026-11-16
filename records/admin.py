from django.contrib import admin

from .models import Record, RecordEvent


class EventInline(admin.TabularInline):
    model = RecordEvent
    extra = 0


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ['pk', 'tag', 'definition', 'harness', 'device', 'quantity', 'location', 'status', 'holder', 'keeper']
    list_filter = ['status']
    search_fields = ['tag', 'serial', 'definition__number']
    inlines = [EventInline]
