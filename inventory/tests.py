import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Customer, InventoryBatch, Order, RegistrationRequest, StockAdjustment, Task


@override_settings(
	DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AuthenticationWorkflowTests(TestCase):
	def setUp(self):
		self.client = Client()

	def test_anonymous_internal_routes_redirect_to_login(self):
		response = self.client.get('/')
		self.assertRedirects(response, '/login/?next=/')

	def test_public_compliance_routes_remain_open(self):
		self.assertEqual(self.client.get('/login/').status_code, 200)
		self.assertEqual(self.client.get('/register/').status_code, 200)
		self.assertEqual(self.client.get('/terms/').status_code, 200)
		self.assertEqual(self.client.get('/privacy/').status_code, 200)

	def test_logout_post_returns_to_login(self):
		user = get_user_model().objects.create_user(username='operator', password='safe-password')
		self.client.force_login(user)
		response = self.client.post('/logout/')
		self.assertRedirects(response, '/login/')

	def test_logout_shows_signed_out_notification_on_login_page(self):
		user = get_user_model().objects.create_user(username='operator', password='safe-password')
		self.client.force_login(user)
		response = self.client.post('/logout/', follow=True)
		self.assertContains(response, 'You have been signed out successfully.')
		self.assertNotIn('_auth_user_id', self.client.session)
		# Notification is one-shot: it must not reappear on the next visit.
		self.assertNotContains(self.client.get('/login/'), 'You have been signed out successfully.')

	def test_anonymous_logout_does_not_show_notification(self):
		response = self.client.post('/logout/', follow=True)
		self.assertNotContains(response, 'You have been signed out successfully.')

	def test_logout_buttons_post_from_every_workspace(self):
		for username, group, path in (
			('admin1', 'Super Admin / Client', '/'),
			('csr1', 'CSR Agent', '/workstation/'),
		):
			user = get_user_model().objects.create_user(username=username, password='safe-password')
			user.groups.add(Group.objects.get_or_create(name=group)[0])
			self.client.force_login(user)
			html = self.client.get(path).content.decode()
			self.assertNotIn('href="/logout/"', html)
			self.assertIn('action="/logout/"', html)

	def test_registration_creates_inactive_user_and_confirmation_activates_customer(self):
		response = self.client.post('/register/', {
			'full_name': 'Asha Patel',
			'company_name': 'Harvest Foods',
			'email': 'asha@example.com',
			'phone': '+91 555 0100',
			'password': 'a-strong-test-password',
			'role_requested': 'Customer',
			'agreed_to_terms': 'on',
		})
		self.assertEqual(response.status_code, 200)
		user = get_user_model().objects.get(username='asha@example.com')
		self.assertFalse(user.is_active)
		message = response.context['confirmation_url']
		match = re.search(r'/confirm-email/([^/]+)/([^/]+)/$', message)
		self.assertIsNotNone(match)
		confirmation = self.client.get(f'/confirm-email/{match.group(1)}/{match.group(2)}/')
		self.assertRedirects(confirmation, '/confirm-success/')
		user.refresh_from_db()
		self.assertTrue(user.is_active)
		self.assertTrue(user.groups.filter(name='Customer').exists())

	def test_role_login_redirect_supports_customer_b2b_group(self):
		user = get_user_model().objects.create_user(username='client', password='safe-password')
		user.groups.add(Group.objects.create(name='Customer B2B'))
		Customer.objects.create(user=user, company_name='Client Co', contact_person='Client', delivery_address='1 Main St', credit_limit=0)
		self.client.force_login(user)
		response = self.client.get('/login/')
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], '/portal/')


@override_settings(
	DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class RoleWorkspaceTests(TestCase):
	"""Every role must be able to sign in and click through its whole workspace without an error page."""

	PASSWORD = 'safe-password'
	ROLES = (
		('admin1', 'Super Admin / Client', '/'),
		('lead1', 'Team Lead', '/tl/dashboard/'),
		('csr1', 'CSR Agent', '/workstation/'),
		('cust1', 'Customer', '/portal/'),
	)
	# Links that are not workspace pages: POST-only, static files, the admin, or GET actions that change data.
	# '/api/' is deliberately NOT skipped: no workspace page should ever send a user to a raw API endpoint.
	SKIPPED_LINK_PREFIXES = ('//', '/static/', '/logout/', '/admin/')

	@classmethod
	def setUpTestData(cls):
		call_command('setup_roles', verbosity=0)
		User = get_user_model()
		cls.users = {}
		for username, group, _home in cls.ROLES:
			user = User.objects.create_user(username=username, password=cls.PASSWORD)
			user.groups.add(Group.objects.get(name=group))
			cls.users[username] = user
		Customer.objects.create(user=cls.users['cust1'], company_name='Harvest Foods', contact_person='Asha', delivery_address='1 Main St', credit_limit=1000)
		Customer.objects.create(company_name='Walk-in Co', contact_person='Ravi', delivery_address='2 Side St', credit_limit=500)
		today = timezone.localdate()
		batch = InventoryBatch.objects.create(rice_type='Jasmine', qty_kg=500, arrival_date=today, expiry_date=today + timedelta(days=365))
		Task.objects.create(title='Count stock', assigned_by=cls.users['lead1'], assigned_to=cls.users['csr1'], due_date=today)
		StockAdjustment.objects.create(batch=batch, qty_kg=10, reason='Recount', requested_by=cls.users['lead1'])

	def sign_in(self, username):
		response = self.client.post('/login/', {'username': username, 'password': self.PASSWORD})
		self.assertEqual(response.status_code, 302, f'{username} could not sign in')
		return response

	def crawl(self, start):
		"""Follow every internal link reachable from `start`, asserting each page answers 200."""
		seen, queue = set(), [start]
		while queue:
			path = queue.pop()
			if path in seen:
				continue
			seen.add(path)
			response = self.client.get(path)
			self.assertEqual(response.status_code, 200, f'{path} answered {response.status_code}')
			for href in re.findall(r'href="([^"#]+)"', response.content.decode()):
				if href.startswith('/') and not href.startswith(self.SKIPPED_LINK_PREFIXES) and '/approve/' not in href:
					queue.append(href)
		return seen

	def test_every_role_signs_in_and_reaches_its_home_without_error(self):
		for username, _group, home in self.ROLES:
			with self.subTest(role=username):
				self.client = Client()
				response = self.sign_in(username)
				self.assertEqual(response['Location'], home)
				self.assertEqual(self.client.get(home).status_code, 200)

	def test_no_role_has_a_link_that_leads_to_an_error_page(self):
		expected_pages = {
			'admin1': {'/'},
			'lead1': {'/tl/dashboard/', '/batches/new/', '/tasks/new/'},
			'csr1': {'/workstation/', '/customers/', '/orders/new/', '/calls/new/', '/settings/'},
			'cust1': {'/portal/', '/portal/orders/', '/portal/purchase/', '/portal/callback/', '/portal/order/create/'},
		}
		for username, _group, home in self.ROLES:
			with self.subTest(role=username):
				self.client = Client()
				self.sign_in(username)
				visited = self.crawl(home)
				self.assertLessEqual(expected_pages[username], visited)

	def test_customer_directory_links_and_redirects_use_the_page_not_the_api(self):
		self.assertEqual(reverse('customer-directory'), '/customers/')
		self.sign_in('csr1')
		self.assertContains(self.client.get('/workstation/'), 'href="/customers/"')
		self.assertNotContains(self.client.get('/workstation/'), '/api/')
		response = self.client.post('/customers/new/', {'company_name': 'New Co', 'contact_person': 'Ravi', 'email': 'new@example.com', 'phone': '', 'delivery_address': '3 Lane', 'credit_limit': '100'})
		self.assertRedirects(response, '/customers/')

	def test_settings_page_links_back_to_each_roles_own_home(self):
		for username, _group, home in self.ROLES:
			with self.subTest(role=username):
				self.client = Client()
				self.sign_in(username)
				self.assertContains(self.client.get('/settings/'), f'href="{home}"')

	def test_team_lead_can_approve_pending_adjustment_from_dashboard(self):
		self.sign_in('lead1')
		adjustment = StockAdjustment.objects.get(is_approved=False)
		self.assertContains(self.client.get('/tl/dashboard/'), f'/stock-adjustments/{adjustment.pk}/approve/')
		self.assertRedirects(self.client.get(f'/stock-adjustments/{adjustment.pk}/approve/'), '/tl/dashboard/')

	def test_team_lead_batch_form_returns_to_team_lead_dashboard(self):
		self.sign_in('lead1')
		self.assertContains(self.client.get('/batches/new/'), 'href="/tl/dashboard/"')
		today = timezone.localdate()
		response = self.client.post('/batches/new/', {'rice_type': 'Basmati', 'qty_kg': '100', 'arrival_date': today, 'expiry_date': today + timedelta(days=30)})
		self.assertRedirects(response, '/tl/dashboard/')

	def test_links_are_hidden_for_pages_a_role_may_not_open(self):
		self.sign_in('csr1')
		html = self.client.get('/workstation/').content.decode()
		for forbidden in ('href="/"', '/batches/new/', '/tasks/new/', '/stock-adjustments/new/'):
			self.assertNotIn(forbidden, html)

	def test_direct_access_to_other_roles_pages_is_still_forbidden(self):
		checks = (
			('csr1', '/batches/new/'), ('csr1', '/tl/dashboard/'), ('csr1', '/'),
			('lead1', '/workstation/'), ('lead1', '/'),
			('cust1', '/workstation/'), ('cust1', '/tl/dashboard/'), ('cust1', '/customers/'),
			('csr1', '/portal/order/create/'), ('lead1', '/portal/order/create/'),
		)
		for username, path in checks:
			with self.subTest(user=username, path=path):
				self.client = Client()
				self.sign_in(username)
				self.assertEqual(self.client.get(path).status_code, 403)

	def test_group_names_match_regardless_of_case_or_stray_spaces(self):
		user = get_user_model().objects.create_user(username='messy', password=self.PASSWORD)
		user.groups.add(Group.objects.create(name='  csr   AGENT '))
		self.sign_in('messy')
		self.assertEqual(self.client.get('/workstation/').status_code, 200)

	def test_superuser_without_groups_lands_on_dashboard(self):
		get_user_model().objects.create_superuser(username='root', password=self.PASSWORD)
		self.assertEqual(self.sign_in('root')['Location'], '/')
		self.assertEqual(self.client.get('/').status_code, 200)

	def test_account_without_a_role_is_refused_with_a_message_not_a_loop_or_403(self):
		get_user_model().objects.create_user(username='norole', password=self.PASSWORD)
		response = self.client.post('/login/', {'username': 'norole', 'password': self.PASSWORD})
		self.assertRedirects(response, '/login/?error=unassigned')
		self.assertNotIn('_auth_user_id', self.client.session)
		self.assertContains(self.client.get('/login/?error=unassigned'), 'not been assigned to an enterprise role')

	def test_existing_session_without_a_role_is_signed_out_instead_of_redirect_looping(self):
		user = get_user_model().objects.create_user(username='norole', password=self.PASSWORD)
		self.client.force_login(user)
		response = self.client.get('/login/?error=unassigned')
		self.assertEqual(response.status_code, 200)
		self.assertNotIn('_auth_user_id', self.client.session)

	def test_customer_without_a_profile_gets_one_at_login_and_lands_on_the_portal(self):
		user = get_user_model().objects.create_user(username='noprofile', password=self.PASSWORD, first_name='Mira', last_name='Shah')
		user.groups.add(Group.objects.get(name='Customer'))
		response = self.client.post('/login/', {'username': 'noprofile', 'password': self.PASSWORD})
		self.assertRedirects(response, '/portal/', fetch_redirect_response=False)
		profile = Customer.objects.get(user=user)
		self.assertEqual(profile.contact_person, 'Mira Shah')
		self.assertEqual(profile.company_name, 'Mira Shah')
		self.assertEqual(self.client.get('/portal/').status_code, 200)

	def test_auto_created_profile_uses_registration_details_when_present(self):
		user = get_user_model().objects.create_user(username='reg@example.com', email='reg@example.com', password=self.PASSWORD)
		user.groups.add(Group.objects.get(name='Customer'))
		RegistrationRequest.objects.create(user=user, company_name='Harvest Foods Ltd', phone='+91 555 0100', role_requested='Customer', agreed_to_terms=True)
		self.sign_in('reg@example.com')
		profile = Customer.objects.get(user=user)
		self.assertEqual((profile.company_name, profile.phone, profile.email), ('Harvest Foods Ltd', '+91 555 0100', 'reg@example.com'))

	def test_existing_customer_session_without_a_profile_self_heals_on_the_portal(self):
		user = get_user_model().objects.create_user(username='oldsession', password=self.PASSWORD)
		user.groups.add(Group.objects.get(name='Customer'))
		self.client.force_login(user)
		self.assertEqual(self.client.get('/portal/').status_code, 200)
		self.assertTrue(Customer.objects.filter(user=user).exists())

	def test_staff_accounts_never_get_a_customer_profile(self):
		self.sign_in('csr1')
		self.client.get('/workstation/')
		self.assertFalse(Customer.objects.filter(user__username='csr1').exists())


@override_settings(
	DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class CustomerOrderPageTests(TestCase):
	PASSWORD = 'safe-password'
	URL = '/portal/order/create/'

	@classmethod
	def setUpTestData(cls):
		call_command('setup_roles', verbosity=0)
		User = get_user_model()
		cls.users = {}
		for username, group in (('cust1', 'Customer'), ('lead1', 'Team Lead'), ('csr1', 'CSR Agent'), ('admin1', 'Super Admin / Client')):
			user = User.objects.create_user(username=username, password=cls.PASSWORD)
			user.groups.add(Group.objects.get(name=group))
			cls.users[username] = user
		cls.customer = Customer.objects.create(user=cls.users['cust1'], company_name='Harvest Foods', contact_person='Asha', delivery_address='1 Main St, Chennai', credit_limit=1000)

	def sign_in(self, username):
		self.client.post('/login/', {'username': username, 'password': self.PASSWORD})

	def payload(self, **overrides):
		data = {
			'rice_grade': 'jasmine-premium-5',
			'quantity': '5',
			'unit': 'tons',
			'target_delivery_date': (timezone.localdate() + timedelta(days=5)).isoformat(),
			'delivery_address': '9 Dock Road, Chennai',
			'notes': 'PO-4471, net 30, forklift on site',
		}
		data.update(overrides)
		return data

	def test_page_renders_with_address_prefilled_and_minimum_delivery_date(self):
		self.sign_in('cust1')
		response = self.client.get(self.URL)
		self.assertContains(response, '1 Main St, Chennai')
		self.assertContains(response, f'min="{(timezone.localdate() + timedelta(days=3)).isoformat()}"')
		self.assertContains(response, 'Portal')
		self.assertContains(response, 'New Order')
		self.assertContains(response, 'Jasmine Premium 5%')

	def test_placeholder_address_is_not_prefilled(self):
		self.customer.delivery_address = 'To be completed'
		self.customer.save()
		self.sign_in('cust1')
		self.assertNotContains(self.client.get(self.URL), 'To be completed')

	def test_valid_order_is_saved_pending_approval_and_priced_on_the_server(self):
		self.sign_in('cust1')
		response = self.client.post(self.URL, self.payload(total_amount='1'))
		order = Order.objects.get()
		self.assertRedirects(response, '/portal/', fetch_redirect_response=False)
		self.assertEqual(order.status, Order.Status.PENDING_APPROVAL)
		self.assertEqual(order.customer, self.customer)
		self.assertEqual(order.customer_name, 'Harvest Foods')
		self.assertEqual(order.rice_type, 'Jasmine Premium 5%')
		self.assertEqual(order.qty_ordered, Decimal('5000.00'))
		self.assertEqual(order.total_amount, Decimal('4750.00'))
		self.assertEqual(order.requested_delivery_date, timezone.localdate() + timedelta(days=5))
		self.assertEqual(order.delivery_address, '9 Dock Road, Chennai')
		self.assertEqual(order.notes, 'PO-4471, net 30, forklift on site')

	def test_bags_are_converted_at_fifty_kilograms_each(self):
		self.sign_in('cust1')
		self.client.post(self.URL, self.payload(rice_grade='basmati-white-1121', quantity='40', unit='bags'))
		order = Order.objects.get()
		self.assertEqual(order.qty_ordered, Decimal('2000.00'))
		self.assertEqual(order.total_amount, Decimal('2360.00'))

	def test_success_toast_is_shown_on_the_portal_after_redirect(self):
		self.sign_in('cust1')
		response = self.client.post(self.URL, self.payload(), follow=True)
		order = Order.objects.get()
		self.assertEqual(response.redirect_chain[-1][0], '/portal/')
		self.assertContains(response, f'Order #{order.pk} submitted successfully for Team Lead review!')
		self.assertContains(response, 'Pending approval')

	def test_order_is_recorded_in_simple_history(self):
		self.sign_in('cust1')
		self.client.post(self.URL, self.payload())
		record = Order.objects.get().history.get()
		self.assertEqual(record.history_change_reason, 'Placed through the customer portal')
		self.assertEqual(record.history_user, self.users['cust1'])
		self.assertEqual(record.status, Order.Status.PENDING_APPROVAL)

	def test_delivery_date_needs_three_days_notice(self):
		self.sign_in('cust1')
		too_soon = self.client.post(self.URL, self.payload(target_delivery_date=(timezone.localdate() + timedelta(days=2)).isoformat()))
		self.assertContains(too_soon, 'Delivery must be at least 3 days away')
		self.assertEqual(Order.objects.count(), 0)
		earliest = self.client.post(self.URL, self.payload(target_delivery_date=(timezone.localdate() + timedelta(days=3)).isoformat()))
		self.assertEqual(earliest.status_code, 302)

	def test_invalid_input_is_rejected_without_creating_an_order(self):
		self.sign_in('cust1')
		for label, overrides, message in (
			('fractional bags', {'unit': 'bags', 'quantity': '2.5'}, 'Bags must be a whole number.'),
			('zero quantity', {'quantity': '0'}, 'greater than or equal to 0.01'),
			('over the cap', {'quantity': '10001'}, 'limited to 10,000 metric tons'),
			('unknown grade', {'rice_grade': 'golden-fantasy'}, 'Select a valid choice'),
			('missing address', {'delivery_address': ''}, 'This field is required'),
		):
			with self.subTest(case=label):
				response = self.client.post(self.URL, self.payload(**overrides))
				self.assertContains(response, message)
				self.assertEqual(Order.objects.count(), 0)

	def test_only_customers_and_super_admins_may_open_the_page(self):
		for username, expected in (('lead1', 403), ('csr1', 403), ('cust1', 200), ('admin1', 200)):
			with self.subTest(user=username):
				self.client = Client()
				self.sign_in(username)
				self.assertEqual(self.client.get(self.URL).status_code, expected)
		self.assertRedirects(Client().get(self.URL), f'/login/?next={self.URL}')

	def test_super_admin_can_preview_but_not_submit(self):
		self.sign_in('admin1')
		preview = self.client.get(self.URL)
		self.assertContains(preview, 'Preview only')
		self.assertContains(preview, 'href="/"')
		self.assertNotContains(preview, 'href="/portal/"')
		response = self.client.post(self.URL, self.payload())
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Orders can only be placed from a customer account.')
		self.assertEqual(Order.objects.count(), 0)

	def test_pending_order_appears_in_the_team_lead_queue(self):
		self.sign_in('cust1')
		self.client.post(self.URL, self.payload())
		order = Order.objects.get()
		self.client = Client()
		self.sign_in('lead1')
		response = self.client.get('/tl/dashboard/')
		self.assertContains(response, 'Pending order approvals')
		self.assertContains(response, f'>#{order.pk}</td>')
		self.assertContains(response, 'Harvest Foods')
		self.assertContains(response, 'Jasmine Premium 5%')

	def test_orders_created_elsewhere_stay_confirmed_and_out_of_the_queue(self):
		order = Order.objects.create(customer=self.customer, customer_name='Harvest Foods', qty_ordered=100, total_amount=50)
		self.assertEqual(order.status, Order.Status.CONFIRMED)
		self.sign_in('lead1')
		response = self.client.get('/tl/dashboard/')
		self.assertNotContains(response, f'>#{order.pk}</td>')
		self.assertContains(response, 'No orders waiting for review.')

# Create your tests here.
