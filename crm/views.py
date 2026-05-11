from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.permissions import HasGroupPermission
from .models import Customer, Lead
from .serializers import CustomerSerializer, LeadSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().filter(is_active=True)
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasGroupPermission]
    required_groups = ['CRM_Managers', 'ERP_Admins']
    search_fields = ['name', 'company', 'email', 'phone']
    ordering_fields = ['name', 'created_at']

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple customers in a single POST request.
        Just send a JSON list instead of a single object.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates multiple customers at once. 
        Each object in the list MUST have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list of objects."}, status=status.HTTP_400_BAD_REQUEST)

        updated_customers = []
        for item in data:
            customer_id = item.get('id')
            if not customer_id:
                continue
            
            try:
                instance = Customer.objects.get(id=customer_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated_customers.append(serializer.data)
            except Customer.DoesNotExist:
                continue

        return Response(updated_customers, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='qr-resolve/(?P<qr_id>[^/.]+)', permission_classes=[AllowAny])
    def qr_resolve(self, request, qr_id=None):
        """
        Resolves a Smart QR scan based on user role.
        """
        customer = Customer.objects.filter(qr_code_id=qr_id).first()
        if not customer:
            return Response({'detail': 'Invalid QR Code.'}, status=404)

        user = request.user
        
        # Scenario 1: Delivery Person (Driver)
        if not user.is_anonymous and getattr(user, 'is_driver', False):
            # Return full customer profile + current active order if exists
            from orders.models import Order, OrderStatus
            import datetime
            today = datetime.date.today()
            order = Order.objects.filter(customer=customer, scheduled_delivery_date=today).first()
            
            return Response({
                'role': 'driver',
                'customer': CustomerSerializer(customer).data,
                'active_order_id': order.id if order else None,
                'message': f'Ready to deliver to {customer.name}'
            })

        # Scenario 2: The Customer themselves
        if not user.is_anonymous and user == customer.user:
            return Response({
                'role': 'customer',
                'customer': CustomerSerializer(customer).data,
                'message': 'Welcome to your dashboard'
            })

        # Scenario 3: Guest / Stranger
        return Response({
            'role': 'guest',
            'company_info': {
                'name': 'Smart Dairy ERP',
                'description': 'Premium milk delivery services.',
                'referred_by_customer_id': customer.id,
                'referred_by_customer_name': customer.name
            },
            'message': 'Scan this QR to join our milk delivery network!'
        })


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [HasGroupPermission]
    required_groups = ['CRM_Managers', 'ERP_Admins']
    
    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]
