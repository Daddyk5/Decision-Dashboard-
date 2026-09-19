from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import send_mail
from django.db import connection
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import catalog
from .decorators import customer_required, current_entity_role, role_home_url_name, role_required, user_has_role
from .forms import CallbackRequestForm, CallLogForm, CustomerForm, CustomerOrderForm, CustomerPurchaseForm, InventoryBatchForm, OrderBookingForm, QuickCallForm, RegistrationForm, StockAdjustmentForm, TaskForm
from .models import CallLog, Customer, Delivery, InventoryBatch, Order, Payment, RegistrationRequest, StockAdjustment, Task
from .profiles import PLACEHOLDER_ADDRESS, ensure_customer_profile


class CustomLoginRedirectView(LoginView):
	template_name = 'registration/login.html'
	redirect_authenticated_user = True

	def dispatch(self, request, *args, **kwargs):
		# A session for an account with no usable workspace would bounce back to /login/ forever.
		ensure_customer_profile(request.user)
		if request.user.is_authenticated and not role_home_url_name(request.user):
			logout(request)
		return super().dispatch(request, *args, **kwargs)

	def form_valid(self, form):
		user = form.get_user()
		ensure_customer_profile(user)
		if not role_home_url_name(user):
			# Refuse the sign-in instead of landing the user on a page that answers 403.
			return redirect(f'{settings.LOGIN_URL}?error=unassigned')
		response = super().form_valid(form)
		self.request.session.set_expiry(1209600 if self.request.POST.get('remember_me') else 0)
		return response

	def get_success_url(self):
		home_name = role_home_url_name(self.request.user)
		return reverse(home_name) if home_name else settings.LOGIN_URL


class CustomLogoutView(LogoutView):
	next_page = '/login/'

	def post(self, request, *args, **kwargs):
		was_authenticated = request.user.is_authenticated
		response = super().post(request, *args, **kwargs)
		if was_authenticated:
			messages.success(request, 'You have been signed out successfully.')
		return response


def register(request):
	form = RegistrationForm(request.POST or None)
	if form.is_valid():
		full_name = form.cleaned_data['full_name'].split(' ', 1)
		user = get_user_model().objects.create_user(
			username=form.cleaned_data['email'],
			email=form.cleaned_data['email'],
			first_name=full_name[0],
			last_name=full_name[1],
			password=form.cleaned_data['password'],
			is_active=False,
		)
		RegistrationRequest.objects.create(
			user=user,
			company_name=form.cleaned_data['company_name'],
			phone=form.cleaned_data['phone'],
			role_requested=form.cleaned_data['role_requested'],
			agreed_to_terms=True,
		)
		uid = urlsafe_base64_encode(force_bytes(user.pk))
		token = default_token_generator.make_token(user)
		confirmation_url = request.build_absolute_uri(reverse('confirm-email', args=[uid, token]))
		send_mail(
			'Confirm your Rice Enterprise account',
			f'Confirm your account by opening: {confirmation_url}',
			None,
			[user.email],
			fail_silently=True,
		)
		return render(request, 'registration/register_sent.html', {'email': user.email, 'confirmation_url': confirmation_url})
	return render(request, 'registration/register.html', {'form': form})


def confirm_email(request, uidb64, token):
	try:
		user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
	except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
		user = None
	if user and default_token_generator.check_token(user, token):
		user.is_active = True
		user.save(update_fields=('is_active',))
		registration = getattr(user, 'registration_request', None)
		if registration and registration.role_requested == RegistrationRequest.Role.CUSTOMER:
			user.groups.add(Group.objects.get_or_create(name='Customer')[0])
			ensure_customer_profile(user)
		return redirect('confirm-success')
	return render(request, 'registration/confirm_invalid.html', status=400)


def confirm_success(request):
	return render(request, 'registration/confirm_success.html')


def terms(request):
	return render(request, 'registration/terms.html')


def privacy(request):
	return render(request, 'registration/privacy.html')


@login_required
def settings_panel(request):
	password_form = PasswordChangeForm(request.user, request.POST or None)
	if request.method == 'POST' and password_form.is_valid():
		password_form.save()
		login(request, request.user)
		return redirect('settings')
	try:
		with connection.cursor() as cursor:
			started = timezone.now()
			cursor.execute('SELECT 1')
			latency_ms = round((timezone.now() - started).total_seconds() * 1000, 1)
		database_status = 'Healthy'
	except Exception:
		latency_ms = None
		database_status = 'Unavailable'
	return render(request, 'inventory/settings.html', {
		'password_form': password_form,
		'database_status': database_status,
		'latency_ms': latency_ms,
		'powerbi_status': 'DirectQuery configured' if getattr(settings, 'POWERBI_WORKSPACE_ID', '') else 'Awaiting workspace configuration',
		'entity_role': request.entity_role,
	})


@customer_required
def customer_portal(request):
	customer = request.user.customer_profile
	orders = customer.orders.prefetch_related('deliveries', 'payments').order_by('-order_date')
	context = {
		'customer': customer,
		'active_orders': orders.exclude(deliveries__delivery_status=Delivery.Status.DELIVERED).distinct().count(),
		'pending_deliveries': Delivery.objects.filter(order__customer=customer).exclude(delivery_status=Delivery.Status.DELIVERED).count(),
		'unpaid_balance': Payment.objects.filter(order__customer=customer, payment_status=Payment.Status.UNPAID).aggregate(total=Sum('amount_due'))['total'] or 0,
		'orders': orders[:20],
		'purchase_form': CustomerPurchaseForm(),
		'callback_form': CallbackRequestForm(),
		'entity_role': request.entity_role,
	}
	return render(request, 'inventory/customer_portal.html', context)


@customer_required
def customer_orders(request):
	customer = request.user.customer_profile
	return render(request, 'inventory/customer_orders.html', {
		'customer': customer,
		'orders': customer.orders.prefetch_related('deliveries', 'payments').order_by('-order_date'),
		'entity_role': request.entity_role,
	})


@customer_required
def customer_purchase(request):
	customer = request.user.customer_profile
	form = CustomerPurchaseForm(request.POST or None)
	if form.is_valid():
		with transaction.atomic():
			order = Order.objects.create(
				customer=customer,
				customer_name=customer.company_name,
				order_date=timezone.localdate(),
				qty_ordered=form.cleaned_data['quantity_kg'],
				total_amount=form.cleaned_data['total_amount'],
			)
			Delivery.objects.create(order=order, scheduled_date=form.cleaned_data['target_delivery_date'])
			Payment.objects.create(order=order, amount_due=form.cleaned_data['total_amount'])
		return redirect('customer-portal')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Quick rice purchase', 'back_url': 'customer-portal'})


@role_required('customer')
def customer_create_order(request):
	# Super Admins may open the page (role_required lets them through) but have no customer profile to order for.
	customer = ensure_customer_profile(request.user)
	address = customer.delivery_address if customer and customer.delivery_address != PLACEHOLDER_ADDRESS else ''
	form = CustomerOrderForm(request.POST if request.method == 'POST' else None, initial={'delivery_address': address})
	if request.method == 'POST':
		if customer is None:
			messages.error(request, 'Orders can only be placed from a customer account.')
		elif form.is_valid():
			data = form.cleaned_data
			quote = data['quote']
			with transaction.atomic():
				order = Order(
					customer=customer,
					customer_name=customer.company_name,
					order_date=timezone.localdate(),
					qty_ordered=quote.kilograms,
					total_amount=quote.total,
					status=Order.Status.PENDING_APPROVAL,
					rice_type=dict(catalog.grade_choices())[data['rice_grade']],
					requested_delivery_date=data['target_delivery_date'],
					delivery_address=data['delivery_address'],
					notes=data['notes'],
				)
				order._change_reason = 'Placed through the customer portal'
				order.save()
			messages.success(request, f'Order #{order.pk} submitted successfully for Team Lead review!')
			return redirect('customer-portal')
	return render(request, 'inventory/customer_create_order.html', {
		'form': form,
		'catalog': catalog.browser_catalog(),
		'is_preview': customer is None,
		'portal_url': reverse('customer-portal') if customer else reverse(role_home_url_name(request.user)),
		'min_lead_days': CustomerOrderForm.MIN_LEAD_DAYS,
		'entity_role': request.entity_role,
	})


@customer_required
def customer_callback(request):
	customer = request.user.customer_profile
	form = CallbackRequestForm(request.POST or None)
	if form.is_valid():
		csr = customer.default_csr_agent
		if csr is None:
			csr = get_user_model().objects.filter(groups__name='CSR Agent', is_active=True).first()
		if csr is None:
			form.add_error(None, 'No CSR agent is available yet. Please contact support.')
		else:
			CallLog.objects.create(
				customer=customer,
				csr_agent=csr,
				call_type=CallLog.CallType.INBOUND,
				purpose='Order Inquiry',
				summary=form.cleaned_data['summary'],
				follow_up_needed=True,
				escalated_to_tl=False,
			)
			return redirect('customer-portal')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Request a callback', 'back_url': 'customer-portal'})


@role_required('super_admin')
def dashboard(request):
	today = timezone.localdate()
	start_date = parse_date(request.GET.get('from_date', ''))
	end_date = parse_date(request.GET.get('to_date', ''))
	batches = InventoryBatch.objects.all()
	deliveries = Delivery.objects.all()
	payments = Payment.objects.select_related('order').order_by('-id')

	if start_date:
		batches = batches.filter(arrival_date__gte=start_date)
		deliveries = deliveries.filter(scheduled_date__gte=start_date)
		payments = payments.filter(order__order_date__gte=start_date)
	if end_date:
		batches = batches.filter(arrival_date__lte=end_date)
		deliveries = deliveries.filter(scheduled_date__lte=end_date)
		payments = payments.filter(order__order_date__lte=end_date)

	stock_summary = batches.aggregate(
		total_stock=Sum('qty_kg'),
		expired_stock=Sum('qty_kg', filter=Q(expiry_date__lte=today)),
	)
	pending_deliveries = deliveries.exclude(
		delivery_status=Delivery.Status.DELIVERED,
	).count()
	unpaid_balance = payments.filter(
		payment_status=Payment.Status.UNPAID,
	).aggregate(total=Sum('amount_due'))['total']
	stock_by_variety = list(
		batches.values('rice_type').annotate(total=Sum('qty_kg')).order_by('-total')
	)
	logistics = list(
		deliveries.values('delivery_status').annotate(total=Count('id'))
	)

	context = {
		'entity_role': request.entity_role,
		'today': today,
		'from_date': request.GET.get('from_date', ''),
		'to_date': request.GET.get('to_date', ''),
		'total_stock': stock_summary['total_stock'] or 0,
		'expired_stock': stock_summary['expired_stock'] or 0,
		'pending_deliveries': pending_deliveries,
		'unpaid_balance': unpaid_balance or 0,
		'batches': batches,
		'payments': payments,
		'stock_by_variety': stock_by_variety,
		'logistics': logistics,
	}
	return render(request, 'inventory/dashboard.html', context)


@role_required('super_admin')
def operations_report(request):
	from reportlab.lib.pagesizes import letter
	from reportlab.lib.styles import getSampleStyleSheet
	from reportlab.lib.units import inch
	from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
	from reportlab.lib import colors

	today = timezone.localdate()
	stock = InventoryBatch.objects.aggregate(
		total=Sum('qty_kg'),
		expired=Sum('qty_kg', filter=Q(expiry_date__lte=today)),
	)
	pending = Delivery.objects.exclude(delivery_status=Delivery.Status.DELIVERED).count()
	unpaid = Payment.objects.filter(payment_status=Payment.Status.UNPAID).aggregate(total=Sum('amount_due'))['total'] or 0

	response = HttpResponse(content_type='application/pdf')
	response['Content-Disposition'] = 'attachment; filename="rice-operations-report.pdf"'
	document = SimpleDocTemplate(response, pagesize=letter, rightMargin=0.6 * inch, leftMargin=0.6 * inch)
	styles = getSampleStyleSheet()
	story = [
		Paragraph('Rice Enterprise Operations Report', styles['Title']),
		Paragraph(f'Generated {today.isoformat()}', styles['Normal']),
		Spacer(1, 0.25 * inch),
	]
	table = Table([
		['Metric', 'Value'],
		['Total stock', f"{stock['total'] or 0} kg"],
		['Expired stock', f"{stock['expired'] or 0} kg"],
		['Pending deliveries', str(pending)],
		['Unpaid receivables', f'${unpaid}'],
	], colWidths=[3 * inch, 2.5 * inch])
	table.setStyle(TableStyle([
		('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B2545')),
		('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
		('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#8DA9C4')),
		('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EEF4F8')),
		('PADDING', (0, 0), (-1, -1), 8),
	]))
	story.append(table)
	document.build(story)
	return response


@role_required('csr_agent')
def workstation(request):
	my_tasks = Task.objects.filter(assigned_to=request.user)
	return render(request, 'inventory/workstation.html', {
		'batches': InventoryBatch.objects.all()[:20],
		'customers': Customer.objects.all()[:20],
		'orders': Order.objects.select_related('customer').prefetch_related('deliveries', 'payments')[:20],
		'tasks': my_tasks.select_related('assigned_by')[:20],
		'follow_up_calls': CallLog.objects.filter(csr_agent=request.user, follow_up_needed=True).select_related('customer')[:20],
		'entity_role': request.entity_role,
	})


@role_required('team_lead', 'csr_agent')
def customer_list(request):
	return render(request, 'inventory/customers.html', {'customers': Customer.objects.prefetch_related('orders')})


@role_required('team_lead', 'csr_agent')
@permission_required('inventory.add_customer', raise_exception=True)
def customer_create(request):
	form = CustomerForm(request.POST or None)
	if form.is_valid():
		form.save()
		return redirect('customer-directory')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Add customer', 'back_url': 'customer-directory'})


@role_required('team_lead', 'csr_agent')
@permission_required('inventory.change_customer', raise_exception=True)
def customer_update(request, pk):
	customer = get_object_or_404(Customer, pk=pk)
	form = CustomerForm(request.POST or None, instance=customer)
	if form.is_valid():
		form.save()
		return redirect('customer-directory')
	return render(request, 'inventory/form.html', {'form': form, 'title': f'Edit {customer.company_name}', 'back_url': 'customer-directory'})


@role_required('team_lead')
@permission_required('inventory.add_inventorybatch', raise_exception=True)
def batch_create(request):
	form = InventoryBatchForm(request.POST or None)
	if form.is_valid():
		form.save()
		return redirect(role_home_url_name(request.user))
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Add rice batch', 'back_url': role_home_url_name(request.user)})


@role_required('team_lead')
@permission_required('inventory.add_stockadjustment', raise_exception=True)
def stock_adjustment_create(request):
	form = StockAdjustmentForm(request.POST or None)
	if form.is_valid():
		adjustment = form.save(commit=False)
		adjustment.requested_by = request.user
		adjustment.is_approved = False
		adjustment.save()
		return redirect(role_home_url_name(request.user))
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Adjust stock', 'back_url': role_home_url_name(request.user)})


@role_required('csr_agent')
@permission_required('inventory.add_order', raise_exception=True)
def order_booking(request):
	form = OrderBookingForm(request.POST or None)
	if form.is_valid():
		form.save(user=request.user)
		return redirect('workstation')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'New customer order', 'back_url': 'workstation'})


@role_required('team_lead')
@permission_required('inventory.add_task', raise_exception=True)
def task_create(request):
	form = TaskForm(request.POST or None, assigning_user=request.user)
	if form.is_valid():
		task = form.save(commit=False)
		task.assigned_by = request.user
		task.save()
		return redirect(role_home_url_name(request.user))
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Assign staff task', 'back_url': role_home_url_name(request.user)})


@role_required('team_lead', 'csr_agent')
def task_update(request, pk):
	task = get_object_or_404(Task, pk=pk)
	if not request.user.has_perm('inventory.change_task') and task.assigned_to_id != request.user.id:
		raise PermissionDenied
	form = TaskForm(request.POST or None, instance=task, assigning_user=request.user)
	if form.is_valid():
		form.save()
		return redirect(role_home_url_name(request.user))
	return render(request, 'inventory/form.html', {'form': form, 'title': f'Update {task.title}', 'back_url': role_home_url_name(request.user)})


@role_required('team_lead')
def tl_dashboard(request):
	return render(request, 'inventory/tl_dashboard.html', {
		'entity_role': request.entity_role,
		'csr_agents': Task.objects.filter(assigned_to__groups__name='CSR Agent').values('assigned_to__username').annotate(total=Count('id'), completed=Count('id', filter=Q(status=Task.Status.COMPLETED))).order_by('assigned_to__username'),
		'escalated_calls': CallLog.objects.filter(escalated_to_tl=True).select_related('customer', 'csr_agent')[:30],
		'pending_adjustments': StockAdjustment.objects.filter(is_approved=False).select_related('batch', 'requested_by')[:30],
		'pending_orders': Order.objects.filter(status=Order.Status.PENDING_APPROVAL).select_related('customer').order_by('requested_delivery_date', 'id')[:30],
	})


@role_required('csr_agent')
def call_log_create(request):
	form = CallLogForm(request.POST or None)
	if form.is_valid():
		call = form.save(commit=False)
		call.csr_agent = request.user
		call.save()
		return redirect('workstation')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Log customer call', 'back_url': 'workstation'})


@role_required('csr_agent')
def quick_call_log(request):
	form = QuickCallForm(request.POST or None)
	if form.is_valid():
		CallLog.objects.create(
			customer=form.cleaned_data['customer'],
			csr_agent=request.user,
			call_type=form.cleaned_data['call_type'],
			purpose='Active call',
			summary=form.cleaned_data['summary'],
			call_duration_seconds=form.cleaned_data['call_duration_seconds'] or 0,
			terms_accepted=True,
		)
		return redirect('workstation')
	return render(request, 'inventory/form.html', {'form': form, 'title': 'Quick call log', 'back_url': 'workstation'})


@role_required('team_lead')
@permission_required('inventory.change_stockadjustment', raise_exception=True)
def approve_stock_adjustment(request, pk):
	adjustment = get_object_or_404(StockAdjustment, pk=pk, is_approved=False)
	with transaction.atomic():
		batch = InventoryBatch.objects.select_for_update().get(pk=adjustment.batch_id)
		if batch.qty_kg + adjustment.qty_kg < 0:
			return render(request, 'inventory/form.html', {'title': 'Approval blocked', 'message': 'Approval would reduce stock below zero.', 'back_url': 'tl-dashboard'})
		batch.qty_kg += adjustment.qty_kg
		batch.save(update_fields=('qty_kg',))
		adjustment.approved_by_tl = request.user
		adjustment.is_approved = True
		adjustment.save(update_fields=('approved_by_tl', 'is_approved'))
	return redirect('tl-dashboard')
