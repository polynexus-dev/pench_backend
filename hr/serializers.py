from rest_framework import serializers
from .models import (
    Employee, Department, SalaryStructure, EmployeeSalary, 
    MonthlyPayroll, EmployeeDocument, DeliveryIncentiveRule, Attendance
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'description']


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)

    class Meta:
        model = EmployeeDocument
        fields = [
            'id', 'employee', 'document_type', 'document_type_display',
            'document_number', 'document_file', 'is_verified', 'verified_by', 'verified_at'
        ]
        read_only_fields = ['id', 'verified_by', 'verified_at']


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'full_name', 'email', 'department', 'department_name',
            'job_title', 'employee_id', 'date_joined', 
            'is_active', 'aadhaar_number', 'pan_number', 'licence_number',
            'emergency_contact_name', 'emergency_contact_phone', 
            'bank_account_number', 'bank_ifsc'
        ]


class SalaryStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryStructure
        fields = [
            'id', 'name', 'basic_amount', 'hra_percentage', 
            'da_percentage', 'other_allowances', 'is_active'
        ]


class MonthlyPayrollSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = MonthlyPayroll
        fields = [
            'id', 'employee', 'employee_name', 'month', 'year',
            'basic', 'hra', 'da', 'incentive', 'deductions',
            'gross_salary', 'net_salary', 'status', 'status_display',
            'processed_at', 'paid_at'
        ]
        read_only_fields = ['id', 'processed_at']


class DeliveryIncentiveRuleSerializer(serializers.ModelSerializer):
    metric_display = serializers.CharField(source='get_metric_display', read_only=True)

    class Meta:
        model = DeliveryIncentiveRule
        fields = ['id', 'name', 'metric', 'metric_display', 'threshold', 'incentive_amount', 'is_active']

class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.get_full_name', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'employee_name', 'date', 'check_in', 'check_out', 'is_driver_ready', 'notes']
        read_only_fields = ['id', 'date', 'check_in']
