import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings


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
		self.client.force_login(user)
		response = self.client.get('/login/')
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], '/portal/')

# Create your tests here.
