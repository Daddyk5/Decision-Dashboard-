from rest_framework import serializers

from .models import CallLog, Customer, Delivery, InventoryBatch, Order, Payment, StockAdjustment, Task


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ('id', 'company_name', 'contact_person', 'email', 'phone', 'delivery_address', 'credit_limit')


class InventoryBatchSerializer(serializers.ModelSerializer):
    days_until_expiry = serializers.ReadOnlyField()
    stock_flag = serializers.ReadOnlyField()

    class Meta:
        model = InventoryBatch
        fields = ('id', 'rice_type', 'qty_kg', 'arrival_date', 'expiry_date', 'days_until_expiry', 'stock_flag')


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ('id', 'customer', 'customer_name', 'order_date', 'qty_ordered', 'total_amount')


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = ('id', 'order', 'scheduled_date', 'delivery_status')


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('id', 'order', 'amount_due', 'payment_status')


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('id', 'title', 'description', 'assigned_by', 'assigned_to', 'priority', 'status', 'due_date')


class StockAdjustmentSerializer(serializers.ModelSerializer):
    requested_by = serializers.PrimaryKeyRelatedField(read_only=True)
    approved_by_tl = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = StockAdjustment
        fields = ('id', 'batch', 'qty_kg', 'reason', 'timestamp', 'requested_by', 'approved_by_tl', 'is_approved')


class CallLogSerializer(serializers.ModelSerializer):
    csr_agent = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CallLog
        fields = ('id', 'customer', 'csr_agent', 'call_type', 'purpose', 'summary', 'call_duration_seconds', 'follow_up_needed', 'follow_up_date', 'escalated_to_tl', 'tl_notes', 'terms_accepted', 'created_at')
