from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from simple_history.models import HistoricalRecords


class InventoryBatch(models.Model):
	rice_type = models.CharField(max_length=100)
	qty_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
	arrival_date = models.DateField()
	expiry_date = models.DateField()
	history = HistoricalRecords()

	class Meta:
		ordering = ['expiry_date', 'rice_type']
		verbose_name = 'Inventory batch'
		verbose_name_plural = 'Inventory batches'

	def __str__(self):
		return f'{self.rice_type} - {self.qty_kg} kg'

	@property
	def days_until_expiry(self):
		return (self.expiry_date - timezone.localdate()).days

	@property
	def stock_flag(self):
		if self.days_until_expiry <= 0:
			return 'Expired'
		if self.days_until_expiry <= 30:
			return 'Critical'
		return 'Optimal'


class Customer(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_profile')
	default_csr_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='default_customer_accounts')
	company_name = models.CharField(max_length=200)
	contact_person = models.CharField(max_length=200)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=40, blank=True)
	delivery_address = models.TextField()
	credit_limit = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
	history = HistoricalRecords()

	class Meta:
		ordering = ['company_name']

	def __str__(self):
		return self.company_name


class Order(models.Model):
	class Status(models.TextChoices):
		PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending approval'
		CONFIRMED = 'CONFIRMED', 'Confirmed'

	customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders', null=True, blank=True)
	customer_name = models.CharField(max_length=200)
	order_date = models.DateField(default=timezone.localdate)
	qty_ordered = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
	total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
	# Orders created before the approval workflow existed (and staff-booked orders) are already confirmed.
	status = models.CharField(max_length=20, choices=Status, default=Status.CONFIRMED)
	rice_type = models.CharField(max_length=100, blank=True)
	requested_delivery_date = models.DateField(null=True, blank=True)
	delivery_address = models.TextField(blank=True)
	notes = models.TextField(blank=True)
	history = HistoricalRecords()

	class Meta:
		ordering = ['-order_date', '-id']

	def __str__(self):
		return f'Order #{self.pk} - {self.customer_name}'


class Delivery(models.Model):
	class Status(models.TextChoices):
		PENDING = 'Pending', 'Pending'
		IN_TRANSIT = 'In-Transit', 'In-Transit'
		DELIVERED = 'Delivered', 'Delivered'

	order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='deliveries')
	scheduled_date = models.DateField()
	delivery_status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
	history = HistoricalRecords()

	class Meta:
		ordering = ['scheduled_date']

	def __str__(self):
		return f'{self.order} - {self.delivery_status}'


class Payment(models.Model):
	class Status(models.TextChoices):
		PAID = 'Paid', 'Paid'
		UNPAID = 'Unpaid', 'Unpaid'

	order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
	amount_due = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
	payment_status = models.CharField(max_length=10, choices=Status, default=Status.UNPAID)
	history = HistoricalRecords()

	def __str__(self):
		return f'{self.order} - {self.payment_status}'


class Task(models.Model):
	class Priority(models.TextChoices):
		LOW = 'Low', 'Low'
		MEDIUM = 'Medium', 'Medium'
		HIGH = 'High', 'High'

	class Status(models.TextChoices):
		TO_DO = 'To Do', 'To Do'
		IN_PROGRESS = 'In Progress', 'In Progress'
		COMPLETED = 'Completed', 'Completed'

	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='delegated_inventory_tasks', null=True, blank=True)
	assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='inventory_tasks')
	priority = models.CharField(max_length=10, choices=Priority, default=Priority.MEDIUM)
	status = models.CharField(max_length=20, choices=Status, default=Status.TO_DO)
	due_date = models.DateField()
	history = HistoricalRecords()

	class Meta:
		ordering = ['status', 'due_date', '-id']

	def __str__(self):
		return self.title


class StockAdjustment(models.Model):
	batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name='adjustments')
	qty_kg = models.DecimalField(max_digits=12, decimal_places=2)
	reason = models.CharField(max_length=255)
	timestamp = models.DateTimeField(auto_now_add=True)
	requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_stock_adjustments', null=True, blank=True)
	approved_by_tl = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_stock_adjustments', null=True, blank=True)
	is_approved = models.BooleanField(default=False)
	history = HistoricalRecords()

	class Meta:
		ordering = ['-timestamp']

	def clean(self):
		if self.batch_id and self.qty_kg is not None:
			batch = self.batch if self.batch_id == getattr(self.batch, 'pk', None) else InventoryBatch.objects.get(pk=self.batch_id)
			if batch.qty_kg + self.qty_kg < 0:
				raise ValidationError({'qty_kg': 'Adjustment cannot reduce stock below zero.'})

	def __str__(self):
		return f'{self.batch} ({self.qty_kg:+g} kg)'


class CallLog(models.Model):
	class CallType(models.TextChoices):
		INBOUND = 'Inbound', 'Inbound'
		OUTBOUND = 'Outbound', 'Outbound'

	customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='call_logs')
	csr_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='call_logs')
	call_type = models.CharField(max_length=10, choices=CallType)
	purpose = models.CharField(max_length=200)
	summary = models.TextField()
	follow_up_needed = models.BooleanField(default=False)
	follow_up_date = models.DateField(null=True, blank=True)
	escalated_to_tl = models.BooleanField(default=False)
	call_duration_seconds = models.PositiveIntegerField(default=0)
	tl_notes = models.TextField(blank=True)
	terms_accepted = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	history = HistoricalRecords()

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.call_type} - {self.customer} - {self.created_at:%Y-%m-%d}'


class RegistrationRequest(models.Model):
	class Role(models.TextChoices):
		CUSTOMER = 'Customer', 'Customer B2B'
		CSR = 'CSR Agent', 'CSR Agent'
		TEAM_LEAD = 'Team Lead', 'Team Lead'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='registration_request')
	company_name = models.CharField(max_length=200, blank=True)
	phone = models.CharField(max_length=40, blank=True)
	role_requested = models.CharField(max_length=30, choices=Role.choices)
	agreed_to_terms = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	approved_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.user.email} - {self.role_requested}'
