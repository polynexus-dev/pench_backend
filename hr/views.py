from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsERPUser
from .models import (
    Employee, Department, SalaryStructure, 
    MonthlyPayroll, EmployeeDocument, DeliveryIncentiveRule
)
from .serializers import (
    EmployeeSerializer, DepartmentSerializer, SalaryStructureSerializer,
    MonthlyPayrollSerializer, EmployeeDocumentSerializer, DeliveryIncentiveRuleSerializer
)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('user', 'department').filter(is_active=True)
    serializer_class = EmployeeSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['department']
    search_fields = ['user__first_name', 'user__last_name', 'employee_id']


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsERPUser]


class SalaryStructureViewSet(viewsets.ModelViewSet):
    queryset = SalaryStructure.objects.all()
    serializer_class = SalaryStructureSerializer
    permission_classes = [IsERPUser]


class MonthlyPayrollViewSet(viewsets.ModelViewSet):
    queryset = MonthlyPayroll.objects.select_related('employee__user')
    serializer_class = MonthlyPayrollSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['employee', 'month', 'year', 'status']

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        month = request.data.get('month')
        year = request.data.get('year')
        
        if not month or not year:
            return Response({'detail': 'Month and year are required.'}, status=400)
            
        from .services.payroll_service import generate_monthly_payroll
        count = generate_monthly_payroll(int(month), int(year))
        
        return Response({'detail': f'Successfully generated {count} payroll records.'})


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.select_related('employee', 'verified_by')
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['employee', 'document_type', 'is_verified']

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        doc = self.get_object()
        doc.is_verified = True
        doc.verified_by = request.user
        from django.utils import timezone
        doc.verified_at = timezone.now()
        doc.save()
        return Response(EmployeeDocumentSerializer(doc).data)


class DeliveryIncentiveRuleViewSet(viewsets.ModelViewSet):
    queryset = DeliveryIncentiveRule.objects.all()
    serializer_class = DeliveryIncentiveRuleSerializer
    permission_classes = [IsERPUser]
