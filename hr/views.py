from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsERPUser, HasGroupPermission
from .models import (
    Employee,
    Department,
    SalaryStructure,
    MonthlyPayroll,
    EmployeeDocument,
    DeliveryIncentiveRule,
    Attendance,
)
from .serializers import (
    EmployeeSerializer,
    DepartmentSerializer,
    SalaryStructureSerializer,
    MonthlyPayrollSerializer,
    EmployeeDocumentSerializer,
    DeliveryIncentiveRuleSerializer,
    AttendanceSerializer,
)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("user", "department").filter(
        is_active=True
    )
    serializer_class = EmployeeSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]
    filterset_fields = ["department"]
    search_fields = ["user__first_name", "user__last_name", "employee_id"]

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple employee profiles in one request.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)

        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["patch", "put"])
    def bulk_update(self, request):
        """
        Updates multiple employee profiles at once.
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST
            )

        updated = []
        for item in data:
            emp_id = item.get("id")
            if not emp_id:
                continue
            try:
                instance = Employee.objects.get(id=emp_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated.append(serializer.data)
            except Employee.DoesNotExist:
                continue
        return Response(updated, status=status.HTTP_200_OK)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]


class SalaryStructureViewSet(viewsets.ModelViewSet):
    queryset = SalaryStructure.objects.all()
    serializer_class = SalaryStructureSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]


class MonthlyPayrollViewSet(viewsets.ModelViewSet):
    queryset = MonthlyPayroll.objects.select_related("employee__user")
    serializer_class = MonthlyPayrollSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]
    filterset_fields = ["employee", "month", "year", "status"]

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        month = request.data.get("month")
        year = request.data.get("year")

        if not month or not year:
            return Response({"detail": "Month and year are required."}, status=400)

        from .services.payroll_service import generate_monthly_payroll

        count = generate_monthly_payroll(int(month), int(year))

        return Response({"detail": f"Successfully generated {count} payroll records."})


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.select_related("employee", "verified_by")
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]
    filterset_fields = ["employee", "document_type", "is_verified"]

    @action(detail=True, methods=["post"], url_path="verify")
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
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["HR_Managers", "ERP_Admins"]


class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related("employee__user").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ["employee", "date", "is_driver_ready"]
