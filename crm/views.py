from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().filter(is_active=True)
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    # In django-tenants, filtering is handled by schema context
    search_fields = ['name', 'company', 'email', 'phone']
    ordering_fields = ['name', 'created_at']
