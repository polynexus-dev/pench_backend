from rest_framework import serializers
from .models import (
    Employee,
    Department,
    SalaryStructure,
    EmployeeSalary,
    MonthlyPayroll,
    EmployeeDocument,
    DeliveryIncentiveRule,
    Attendance,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description"]


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )

    class Meta:
        model = EmployeeDocument
        fields = [
            "id",
            "employee",
            "document_type",
            "document_type_display",
            "document_number",
            "document_file",
            "is_verified",
            "verified_by",
            "verified_at",
        ]
        read_only_fields = ["id", "verified_by", "verified_at"]


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)

    # Writable user profile fields — so admins can fix incomplete profiles inline
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    warehouse_id = serializers.SerializerMethodField(read_only=True)
    warehouse_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "user",
            "full_name",
            "first_name",
            "last_name",
            "phone",
            "email",
            "department",
            "department_name",
            "job_title",
            "employee_id",
            "date_joined",
            "is_active",
            "aadhaar_number",
            "pan_number",
            "licence_number",
            "emergency_contact_name",
            "emergency_contact_phone",
            "bank_account_number",
            "bank_ifsc",
            "warehouse_id",
            "warehouse_name",
        ]

    def get_warehouse_id(self, obj):
        try:
            from routing.models import Driver

            driver_profile = Driver.objects.filter(user=obj.user).first()
            if driver_profile and driver_profile.warehouse:
                return str(driver_profile.warehouse.id)
        except Exception:
            pass
        return None

    def get_warehouse_name(self, obj):
        try:
            from routing.models import Driver

            driver_profile = Driver.objects.filter(user=obj.user).first()
            if driver_profile and driver_profile.warehouse:
                return driver_profile.warehouse.name
        except Exception:
            pass
        return None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Manually inject the user fields into the serialized representation
        if instance.user:
            ret["first_name"] = instance.user.first_name
            ret["last_name"] = instance.user.last_name
            ret["phone"] = instance.user.phone
        else:
            ret["first_name"] = ""
            ret["last_name"] = ""
            ret["phone"] = ""
        return ret

    def update(self, instance, validated_data):
        first_name = validated_data.pop("first_name", None)
        last_name = validated_data.pop("last_name", None)
        phone = validated_data.pop("phone", None)

        user = instance.user
        if user:
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if phone is not None:
                user.phone = phone
            user.save()

        return super().update(instance, validated_data)

    def create(self, validated_data):
        first_name = validated_data.pop("first_name", None)
        last_name = validated_data.pop("last_name", None)
        phone = validated_data.pop("phone", None)

        instance = super().create(validated_data)

        user = instance.user
        if user:
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if phone is not None:
                user.phone = phone
            user.save()

        return instance


class SalaryStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryStructure
        fields = [
            "id",
            "name",
            "basic_amount",
            "hra_percentage",
            "da_percentage",
            "other_allowances",
            "is_active",
        ]


class MonthlyPayrollSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.user.get_full_name", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MonthlyPayroll
        fields = [
            "id",
            "employee",
            "employee_name",
            "month",
            "year",
            "basic",
            "hra",
            "da",
            "incentive",
            "deductions",
            "gross_salary",
            "net_salary",
            "status",
            "status_display",
            "processed_at",
            "paid_at",
        ]
        read_only_fields = ["id", "processed_at"]


class DeliveryIncentiveRuleSerializer(serializers.ModelSerializer):
    metric_display = serializers.CharField(source="get_metric_display", read_only=True)

    class Meta:
        model = DeliveryIncentiveRule
        fields = [
            "id",
            "name",
            "metric",
            "metric_display",
            "threshold",
            "incentive_amount",
            "is_active",
        ]


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.user.get_full_name", read_only=True
    )

    class Meta:
        model = Attendance
        fields = [
            "id",
            "employee",
            "employee_name",
            "date",
            "check_in",
            "check_out",
            "is_driver_ready",
            "notes",
        ]
        read_only_fields = ["id", "date", "check_in"]
