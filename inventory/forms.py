from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import catalog
from .models import CallLog, Customer, Delivery, InventoryBatch, Order, Payment, RegistrationRequest, StockAdjustment, Task


class RegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=200)
    company_name = forms.CharField(max_length=200, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=40, required=False)
    password = forms.CharField(widget=forms.PasswordInput, min_length=10)
    role_requested = forms.ChoiceField(choices=RegistrationRequest.Role.choices, label='Role requested')
    agreed_to_terms = forms.BooleanField(label='I have read and agree to the Terms & Conditions and Privacy Policy')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if get_user_model().objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_full_name(self):
        full_name = ' '.join(self.cleaned_data['full_name'].split())
        if len(full_name.split()) < 2:
            raise forms.ValidationError('Enter your first and last name.')
        return full_name


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ('company_name', 'contact_person', 'email', 'phone', 'delivery_address', 'credit_limit')
        widgets = {'delivery_address': forms.Textarea(attrs={'rows': 3})}


class InventoryBatchForm(forms.ModelForm):
    class Meta:
        model = InventoryBatch
        fields = ('rice_type', 'qty_kg', 'arrival_date', 'expiry_date')
        widgets = {'arrival_date': forms.DateInput(attrs={'type': 'date'}), 'expiry_date': forms.DateInput(attrs={'type': 'date'})}


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ('batch', 'qty_kg', 'reason')

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get('batch')
        qty_kg = cleaned.get('qty_kg')
        if batch and qty_kg and batch.qty_kg + qty_kg < 0:
            raise ValidationError('Adjustment cannot reduce stock below zero.')
        return cleaned


class OrderBookingForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.all())
    rice_type = forms.CharField(max_length=100)
    quantity_kg = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    total_amount = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2)
    scheduled_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        cleaned = super().clean()
        rice_type = cleaned.get('rice_type')
        quantity = cleaned.get('quantity_kg')
        if rice_type and quantity:
            available = InventoryBatch.objects.filter(rice_type__iexact=rice_type).aggregate(total=Sum('qty_kg'))['total'] or 0
            if available < quantity:
                raise ValidationError(f'Only {available} kg of {rice_type} is available.')
        return cleaned

    @transaction.atomic
    def save(self, *, user=None):
        customer = self.cleaned_data['customer']
        order = Order.objects.create(
            customer=customer,
            customer_name=customer.company_name,
            order_date=timezone.localdate(),
            qty_ordered=self.cleaned_data['quantity_kg'],
            total_amount=self.cleaned_data['total_amount'],
        )
        Delivery.objects.create(order=order, scheduled_date=self.cleaned_data['scheduled_date'])
        Payment.objects.create(order=order, amount_due=self.cleaned_data['total_amount'])
        return order


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('title', 'description', 'assigned_to', 'priority', 'status', 'due_date')
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'}), 'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, assigning_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if assigning_user and not assigning_user.is_superuser:
            self.fields['assigned_to'].queryset = self.fields['assigned_to'].queryset.filter(groups__name='CSR Agent').distinct()


class CallLogForm(forms.ModelForm):
    terms_accepted = forms.BooleanField(required=True, label='I confirm call-recording consent was obtained')

    class Meta:
        model = CallLog
        fields = ('customer', 'call_type', 'purpose', 'summary', 'call_duration_seconds', 'follow_up_needed', 'follow_up_date', 'escalated_to_tl', 'tl_notes', 'terms_accepted')
        widgets = {
            'follow_up_date': forms.DateInput(attrs={'type': 'date'}),
            'summary': forms.Textarea(attrs={'rows': 4}),
            'tl_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('follow_up_needed') and not cleaned.get('follow_up_date'):
            raise ValidationError('A follow-up date is required when follow-up is needed.')
        return cleaned


class QuickCallForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.all())
    call_type = forms.ChoiceField(choices=CallLog.CallType.choices)
    summary = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))
    call_duration_seconds = forms.IntegerField(min_value=0, required=False, initial=0)
    terms_accepted = forms.BooleanField(required=True, label='I confirm call-recording consent was obtained')


class CustomerPurchaseForm(forms.Form):
    rice_type = forms.CharField(max_length=100)
    quantity_kg = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    target_delivery_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    total_amount = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2)

    def clean(self):
        cleaned = super().clean()
        rice_type = cleaned.get('rice_type')
        quantity = cleaned.get('quantity_kg')
        if rice_type and quantity:
            available = InventoryBatch.objects.filter(rice_type__iexact=rice_type).aggregate(total=Sum('qty_kg'))['total'] or 0
            if available < quantity:
                raise ValidationError(f'Only {available} kg of {rice_type} is currently available.')
        return cleaned


FIELD_CLASSES = 'w-full rounded-lg border border-slate-300 bg-white/80 px-3 py-2.5 text-navy shadow-sm focus:border-slateblue focus:outline-none focus:ring-2 focus:ring-softblue/50'


class CustomerOrderForm(forms.Form):
    """B2B order request. The total is always priced here, never taken from the browser."""

    MIN_LEAD_DAYS = 3

    rice_grade = forms.ChoiceField(choices=catalog.grade_choices(), label='Rice grain type & grade')
    quantity = forms.DecimalField(min_value=Decimal('0.01'), max_digits=10, decimal_places=2, label='Quantity')
    unit = forms.ChoiceField(choices=catalog.unit_choices(), initial='tons', label='Unit')
    target_delivery_date = forms.DateField(label='Target delivery date', widget=forms.DateInput(attrs={'type': 'date'}))
    delivery_address = forms.CharField(max_length=500, label='Shipping / delivery address', widget=forms.Textarea(attrs={'rows': 3}))
    notes = forms.CharField(max_length=1000, required=False, label='Payment terms & notes', widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Purchase order number, payment terms, loading / unloading instructions...'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.earliest_delivery = timezone.localdate() + timedelta(days=self.MIN_LEAD_DAYS)
        self.fields['target_delivery_date'].widget.attrs['min'] = self.earliest_delivery.isoformat()
        for field in self.fields.values():
            field.widget.attrs['class'] = FIELD_CLASSES

    def clean_target_delivery_date(self):
        target = self.cleaned_data['target_delivery_date']
        if target < self.earliest_delivery:
            raise ValidationError(f'Delivery must be at least {self.MIN_LEAD_DAYS} days away (earliest {self.earliest_delivery:%b %d, %Y}).')
        return target

    def clean(self):
        cleaned = super().clean()
        grade, unit, quantity = cleaned.get('rice_grade'), cleaned.get('unit'), cleaned.get('quantity')
        if grade and unit and quantity is not None:
            if unit == 'bags' and quantity != quantity.to_integral_value():
                self.add_error('quantity', 'Bags must be a whole number.')
            else:
                quote = catalog.quote(grade, unit, quantity)
                if quote.metric_tons > catalog.MAX_ORDER_TONS:
                    self.add_error('quantity', f'Orders are limited to {catalog.MAX_ORDER_TONS:,} metric tons. Contact your account manager for larger volumes.')
                else:
                    cleaned['quote'] = quote
        return cleaned


class CallbackRequestForm(forms.Form):
    summary = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), label='How can we help?')
