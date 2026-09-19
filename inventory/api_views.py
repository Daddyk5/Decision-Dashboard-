from rest_framework import permissions, viewsets

from .models import CallLog, Customer, Delivery, InventoryBatch, Order, Payment, StockAdjustment, Task
from .serializers import (
    CustomerSerializer,
    CallLogSerializer,
    DeliverySerializer,
    InventoryBatchSerializer,
    OrderSerializer,
    PaymentSerializer,
    StockAdjustmentSerializer,
    TaskSerializer,
)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class InventoryBatchViewSet(viewsets.ModelViewSet):
    queryset = InventoryBatch.objects.all()
    serializer_class = InventoryBatchSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filterset_fields = ('rice_type', 'expiry_date')


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.select_related('order')
    serializer_class = DeliverySerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filterset_fields = ('delivery_status', 'scheduled_date')


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('order')
    serializer_class = PaymentSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filterset_fields = ('payment_status',)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related('assigned_to')
    serializer_class = TaskSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filterset_fields = ('priority', 'status', 'assigned_to')


class StockAdjustmentViewSet(viewsets.ModelViewSet):
    queryset = StockAdjustment.objects.select_related('batch', 'adjusted_by')
    serializer_class = StockAdjustmentSerializer
    permission_classes = (permissions.DjangoModelPermissions,)

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)


class CallLogViewSet(viewsets.ModelViewSet):
    queryset = CallLog.objects.select_related('customer', 'csr_agent')
    serializer_class = CallLogSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filterset_fields = ('call_type', 'follow_up_needed', 'escalated_to_tl')

    def perform_create(self, serializer):
        serializer.save(csr_agent=self.request.user)
