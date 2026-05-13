from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeViewSet, DepartmentViewSet, SalaryStructureViewSet,
    MonthlyPayrollViewSet, EmployeeDocumentViewSet, DeliveryIncentiveRuleViewSet,
    AttendanceViewSet
)

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'salary-structures', SalaryStructureViewSet, basename='salary-structure')
router.register(r'payrolls', MonthlyPayrollViewSet, basename='payroll')
router.register(r'documents', EmployeeDocumentViewSet, basename='document')
router.register(r'incentive-rules', DeliveryIncentiveRuleViewSet, basename='incentive-rule')
router.register(r'attendance', AttendanceViewSet, basename='attendance')

urlpatterns = [path('', include(router.urls))]
