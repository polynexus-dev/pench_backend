from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsERPUser, HasGroupPermission
from .models import MonthlyBill
from .serializers import MonthlyBillSerializer
from .services import bulk_generate_monthly_bills


class MonthlyBillViewSet(viewsets.ModelViewSet):
    queryset = MonthlyBill.objects.all().select_related('customer').prefetch_related('transactions')
    serializer_class = MonthlyBillSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ['Accountants', 'ERP_Admins']
    filterset_fields = ['status', 'customer']

    @action(detail=False, methods=['post'], url_path='trigger-generation')
    def trigger_generation(self, request):
        """
        Manually trigger billing for a specific month/year.
        Example: {"year": 2024, "month": 4}
        """
        year = request.data.get('year')
        month = request.data.get('month')
        
        if not all([year, month]):
            return Response({'detail': 'year and month are required.'}, status=400)
            
        count = bulk_generate_monthly_bills(int(year), int(month))
        return Response({'detail': f'Generated {count} bills for period {month}/{year}.'})
