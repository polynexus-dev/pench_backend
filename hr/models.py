from django.db import models
from core.models import BaseModel


class Department(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Employee(BaseModel):
    # User is in SHARED schema
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='employee_profile'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        related_name='employees'
    )
    job_title = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=50, unique=True)
    date_joined = models.DateField()
    is_active = models.BooleanField(default=True)

    # Onboarding & Compliance
    aadhaar_number = models.CharField(max_length=12, blank=True)
    pan_number = models.CharField(max_length=10, blank=True)
    licence_number = models.CharField(max_length=20, blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)

    class Meta:
        ordering = ['user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.job_title}'


class SalaryStructure(BaseModel):
    name = models.CharField(max_length=100)
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2)
    hra_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    da_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    other_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class EmployeeSalary(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_history')
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.PROTECT)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Employee Salaries'

    def __str__(self):
        return f'{self.employee.employee_id} — {self.salary_structure.name}'


class MonthlyPayrollStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PROCESSED = 'processed', 'Processed'
    PAID = 'paid', 'Paid'


class MonthlyPayroll(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hra = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    da = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    incentive = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=MonthlyPayrollStatus.choices, default=MonthlyPayrollStatus.DRAFT)
    processed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('employee', 'month', 'year')]

    def __str__(self):
        return f'{self.employee.employee_id} — {self.month}/{self.year}'


class DocumentType(models.TextChoices):
    AADHAAR = 'aadhaar', 'Aadhaar Card'
    PAN = 'pan', 'PAN Card'
    LICENCE = 'licence', 'Driving Licence'
    OTHER = 'other', 'Other'


class EmployeeDocument(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    document_number = models.CharField(max_length=50)
    document_file = models.FileField(upload_to='employee_docs/')
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_docs')
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.get_document_type_display()} — {self.employee.employee_id}'


class IncentiveMetric(models.TextChoices):
    ON_TIME_PCT = 'on_time_pct', 'On-Time Delivery %'
    COLLECTION_ACCURACY = 'collection_accuracy', 'Collection Accuracy'
    TOTAL_DELIVERIES = 'total_deliveries', 'Total Deliveries'


class DeliveryIncentiveRule(BaseModel):
    name = models.CharField(max_length=200)
    metric = models.CharField(max_length=50, choices=IncentiveMetric.choices)
    threshold = models.DecimalField(max_digits=10, decimal_places=2)
    incentive_amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name} — {self.metric} > {self.threshold}'


class Attendance(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(auto_now_add=True)
    check_in = models.DateTimeField(auto_now_add=True)
    check_out = models.DateTimeField(null=True, blank=True)
    
    # Tracking for logistics
    is_driver_ready = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date', '-check_in']

    def __str__(self):
        return f'{self.employee.employee_id} — {self.date}'
