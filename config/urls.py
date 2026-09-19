"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventory.api_views import (
    CustomerViewSet,
    CallLogViewSet,
    DeliveryViewSet,
    InventoryBatchViewSet,
    OrderViewSet,
    PaymentViewSet,
    StockAdjustmentViewSet,
    TaskViewSet,
)
from inventory.views import (
    batch_create,
    customer_create,
    customer_list,
    customer_update,
    customer_callback,
    customer_orders,
    customer_portal,
    customer_purchase,
    CustomLoginRedirectView,
    confirm_email,
    confirm_success,
    dashboard,
    privacy,
    register,
    settings_panel,
    terms,
    operations_report,
    order_booking,
    approve_stock_adjustment,
    call_log_create,
    quick_call_log,
    stock_adjustment_create,
    task_create,
    task_update,
    tl_dashboard,
    workstation,
)

router = DefaultRouter()
router.register('batches', InventoryBatchViewSet, basename='batch')
router.register('orders', OrderViewSet, basename='order')
router.register('deliveries', DeliveryViewSet, basename='delivery')
router.register('payments', PaymentViewSet, basename='payment')
router.register('customers', CustomerViewSet, basename='customer')
router.register('tasks', TaskViewSet, basename='task')
router.register('stock-adjustments', StockAdjustmentViewSet, basename='stock-adjustment')
router.register('calls', CallLogViewSet, basename='call')

urlpatterns = [
    path('login/', CustomLoginRedirectView.as_view(), name='login'),
    path('register/', register, name='register'),
    path('confirm-email/<uidb64>/<token>/', confirm_email, name='confirm-email'),
    path('confirm-success/', confirm_success, name='confirm-success'),
    path('terms/', terms, name='terms'),
    path('privacy/', privacy, name='privacy'),
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'),
    path('', dashboard, name='dashboard'),
    path('workstation/', workstation, name='workstation'),
    path('tl/dashboard/', tl_dashboard, name='tl-dashboard'),
    path('customers/', customer_list, name='customer-list'),
    path('customers/new/', customer_create, name='customer-create'),
    path('customers/<int:pk>/edit/', customer_update, name='customer-update'),
    path('batches/new/', batch_create, name='batch-create'),
    path('stock-adjustments/new/', stock_adjustment_create, name='stock-adjustment-create'),
    path('orders/new/', order_booking, name='order-booking'),
    path('tasks/new/', task_create, name='task-create'),
    path('tasks/<int:pk>/edit/', task_update, name='task-update'),
    path('calls/new/', call_log_create, name='call-log-create'),
    path('calls/quick/', quick_call_log, name='quick-call-log'),
    path('stock-adjustments/<int:pk>/approve/', approve_stock_adjustment, name='approve-stock-adjustment'),
    path('reports/operations.pdf', operations_report, name='operations-report'),
    path('portal/', customer_portal, name='customer-portal'),
    path('portal/orders/', customer_orders, name='customer-orders'),
    path('portal/purchase/', customer_purchase, name='customer-purchase'),
    path('portal/callback/', customer_callback, name='customer-callback'),
    path('settings/', settings_panel, name='settings'),
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
]
