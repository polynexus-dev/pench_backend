from django.db import models
from core.models import BaseModel


class Warehouse(BaseModel):
    name = models.CharField(max_length=200)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(BaseModel):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, default='pcs')
    is_active = models.BooleanField(default=True)

    # Dairy-specific: bottle tracking
    bottle_type = models.ForeignKey(
        'BottleType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text='If set, this product comes in a returnable bottle.'
    )
    is_returnable = models.BooleanField(
        default=False,
        help_text='Whether the container/bottle for this product is returnable.'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'


class Stock(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_levels')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_levels')
    quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=10)

    class Meta:
        unique_together = [('product', 'warehouse')]
        verbose_name_plural = 'Stock'

    def __str__(self):
        return f'{self.product.name} @ {self.warehouse.name}: {self.quantity}'


class BottleType(BaseModel):
    name = models.CharField(max_length=200)
    deposit_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    volume_ml = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CustomerBottleBalance(BaseModel):
    """
    Tracks how many bottles of a specific type a customer currently has.
    Balance = (Total Issued - Total Returned)
    """
    customer = models.ForeignKey(
        'crm.Customer',
        on_delete=models.CASCADE,
        related_name='bottle_balances'
    )
    bottle_type = models.ForeignKey(
        BottleType,
        on_delete=models.CASCADE
    )
    balance = models.IntegerField(default=0)

    class Meta:
        unique_together = ('customer', 'bottle_type')

    def __str__(self):
        return f"{self.customer.name} - {self.bottle_type.name}: {self.balance}"


class BottleTransactionType(models.TextChoices):
    ISSUED = 'issued', 'Issued to Customer'
    RETURNED = 'returned', 'Returned by Customer'
    BROKEN = 'broken', 'Broken/Damaged'
    REFILLED = 'refilled', 'Refilled at Warehouse'


class BottleTransaction(BaseModel):
    bottle_type = models.ForeignKey(BottleType, on_delete=models.PROTECT, related_name='transactions')
    customer = models.ForeignKey(
        'crm.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bottle_transactions',
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bottle_transactions',
    )
    transaction_type = models.CharField(max_length=20, choices=BottleTransactionType.choices)
    quantity = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} of {self.quantity} for {self.bottle_type.name}"


class CustomerProductPrice(BaseModel):
    """
    Defines a custom/discounted price for a product for a specific customer.
    If a record exists, this price overrides the default Product.unit_price.
    """
    customer = models.ForeignKey(
        'crm.Customer',
        on_delete=models.CASCADE,
        related_name='custom_prices'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='custom_prices'
    )
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    custom_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('customer', 'product')
        verbose_name = 'Customer Product Price'
        verbose_name_plural = 'Customer Product Prices'

    def __str__(self):
        return f"{self.customer.name} - {self.product.name}: Rs. {self.custom_price}"

