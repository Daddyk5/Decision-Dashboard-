from datetime import timedelta

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CallLog, Customer, Delivery, InventoryBatch, Order, Payment, StockAdjustment, Task


class StockFlagFilter(admin.SimpleListFilter):
	title = 'stock flag'
	parameter_name = 'stock_flag'

	def lookups(self, request, model_admin):
		return (('expired', 'Expired'), ('critical', 'Critical'), ('optimal', 'Optimal'))

	def queryset(self, request, queryset):
		today = timezone.localdate()
		if self.value() == 'expired':
			return queryset.filter(expiry_date__lte=today)
		if self.value() == 'critical':
			return queryset.filter(expiry_date__gt=today, expiry_date__lte=today + timedelta(days=30))
		if self.value() == 'optimal':
			return queryset.filter(expiry_date__gt=today + timedelta(days=30))
		return queryset


@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
	list_display = ('rice_type', 'qty_kg', 'arrival_date', 'expiry_date', 'days_until_expiry', 'stock_flag')
	list_filter = (StockFlagFilter, 'rice_type')
	search_fields = ('rice_type',)
	date_hierarchy = 'expiry_date'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	list_display = ('customer', 'customer_name', 'order_date', 'qty_ordered', 'total_amount')
	list_filter = ('order_date',)
	search_fields = ('customer_name',)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
	list_display = ('order', 'scheduled_date', 'delivery_status')
	list_filter = ('delivery_status', 'scheduled_date')
	search_fields = ('order__customer_name',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
	list_display = ('order', 'amount_due', 'payment_status')
	list_filter = ('payment_status',)
	search_fields = ('order__customer_name',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
	list_display = ('company_name', 'user', 'default_csr_agent', 'contact_person', 'email', 'phone', 'credit_limit')
	search_fields = ('company_name', 'contact_person', 'email')
	list_filter = ('default_csr_agent',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
	list_display = ('title', 'assigned_by', 'assigned_to', 'priority', 'status', 'due_date')
	list_filter = ('priority', 'status', 'due_date')
	search_fields = ('title', 'assigned_to__username')


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
	list_display = ('batch', 'qty_kg', 'reason', 'requested_by', 'approved_by_tl', 'is_approved')
	list_filter = ('timestamp',)
	search_fields = ('batch__rice_type', 'reason', 'requested_by__username')
	readonly_fields = ('timestamp', 'requested_by', 'approved_by_tl')

	def save_model(self, request, obj, form, change):
		if not obj.requested_by_id:
			obj.requested_by = request.user
		if not obj.is_approved or change:
			super().save_model(request, obj, form, change)
			return
		with transaction.atomic():
			batch = obj.batch.__class__.objects.select_for_update().get(pk=obj.batch_id)
			if batch.qty_kg + obj.qty_kg < 0:
				raise ValidationError('Adjustment cannot reduce stock below zero.')
			batch.qty_kg += obj.qty_kg
			batch.save(update_fields=('qty_kg',))
			obj.approved_by_tl = request.user
			super().save_model(request, obj, form, change)


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
	list_display = ('customer', 'csr_agent', 'call_type', 'call_duration_seconds', 'terms_accepted', 'follow_up_needed', 'escalated_to_tl', 'created_at')
	list_filter = ('call_type', 'follow_up_needed', 'escalated_to_tl')
	search_fields = ('customer__company_name', 'csr_agent__username', 'purpose', 'summary')
	readonly_fields = ('csr_agent', 'created_at')


admin.site.site_header = 'Rice Enterprise Operations'
admin.site.site_title = 'Rice Enterprise Operations'
admin.site.index_title = 'Operations Dashboard'
