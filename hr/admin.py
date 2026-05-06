from django.contrib import admin
from .models import (
    Employee, Department, SalaryStructure, EmployeeSalary, 
    MonthlyPayroll, EmployeeDocument, DeliveryIncentiveRule
)

class EmployeeSalaryInline(admin.TabularInline):
    model = EmployeeSalary
    extra = 1

class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 1

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['user', 'job_title', 'department', 'employee_id', 'is_active']
    list_filter = ['department', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'employee_id']
    inlines = [EmployeeSalaryInline, EmployeeDocumentInline]

@admin.register(MonthlyPayroll)
class MonthlyPayrollAdmin(admin.ModelAdmin):
    list_display = ['employee', 'month', 'year', 'net_salary', 'status', 'processed_at']
    list_filter = ['month', 'year', 'status']
    search_fields = ['employee__user__first_name', 'employee__employee_id']

@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'basic_amount', 'is_active']

admin.site.register(Department)
admin.site.register(DeliveryIncentiveRule)
admin.site.register(EmployeeDocument)
