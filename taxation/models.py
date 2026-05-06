from django.db import models
from core.models import BaseModel


class TaxType(models.TextChoices):
    SGST = 'sgst', 'SGST (State GST)'
    CGST = 'cgst', 'CGST (Central GST)'
    IGST = 'igst', 'IGST (Integrated GST)'
    EXEMPT = 'exempt', 'Exempt'


class TaxCategory(models.TextChoices):
    STANDARD = 'standard', 'Standard'
    ESSENTIAL = 'essential', 'Essential'
    EXEMPT = 'exempt', 'Exempt'


class TaxRule(BaseModel):
    name = models.CharField(max_length=200, help_text='E.g., Maharashtra SGST 9%')
    state = models.CharField(max_length=100, help_text='State this rule applies to.')
    tax_type = models.CharField(max_length=10, choices=TaxType.choices)
    rate_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Tax rate as a percentage, e.g. 9.00 for 9%.'
    )
    tax_category = models.CharField(
        max_length=20,
        choices=TaxCategory.choices,
        default=TaxCategory.STANDARD,
    )
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['state', 'tax_type']

    def __str__(self):
        return f'{self.name} — {self.rate_percentage}% ({self.get_tax_type_display()})'


class ProductTaxCategory(BaseModel):
    product = models.OneToOneField(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='tax_category_info'
    )
    tax_category = models.CharField(
        max_length=20,
        choices=TaxCategory.choices,
        default=TaxCategory.STANDARD,
    )
    hsn_code = models.CharField(
        max_length=8,
        blank=True,
    )

    def __str__(self):
        return f'{self.product.name} — {self.get_tax_category_display()}'
