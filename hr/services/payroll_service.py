import logging
from decimal import Decimal
from django.utils import timezone
from django.db import models
from hr.models import (
    Employee,
    MonthlyPayroll,
    MonthlyPayrollStatus,
    EmployeeSalary,
    DeliveryIncentiveRule,
)

logger = logging.getLogger(__name__)


def calculate_delivery_incentives(employee, month, year):
    # This logic would query TrackingEvents for the current schema
    return Decimal("500.00")


def generate_monthly_payroll(month, year):
    """
    Generates payroll records for all active employees for a given month/year.
    Scoped to the current tenant schema.
    """
    employees = Employee.objects.filter(is_active=True)

    count = 0
    for employee in employees:
        # Get active salary structure
        salary_info = (
            EmployeeSalary.objects.filter(
                employee=employee, effective_from__lte=timezone.now().date()
            )
            .filter(
                models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=timezone.now().date())
            )
            .select_related("salary_structure")
            .first()
        )

        if not salary_info:
            logger.warning(
                f"No active salary structure for employee {employee.employee_id}"
            )
            continue

        struct = salary_info.salary_structure

        basic = struct.basic_amount
        hra = round(basic * (struct.hra_percentage / Decimal("100")), 2)
        da = round(basic * (struct.da_percentage / Decimal("100")), 2)

        incentive = Decimal("0.00")
        if hasattr(employee.user, "driver_profile"):
            incentive = calculate_delivery_incentives(employee, month, year)

        gross = basic + hra + da + struct.other_allowances + incentive
        deductions = Decimal("0.00")
        net = gross - deductions

        payroll, created = MonthlyPayroll.objects.update_or_create(
            employee=employee,
            month=month,
            year=year,
            defaults={
                "basic": basic,
                "hra": hra,
                "da": da,
                "incentive": incentive,
                "deductions": deductions,
                "gross_salary": gross,
                "net_salary": net,
                "status": MonthlyPayrollStatus.DRAFT,
                "processed_at": timezone.now(),
            },
        )
        count += 1

    return count
