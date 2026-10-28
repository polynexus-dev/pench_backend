import math
from decimal import Decimal

from django.core.validators import MinValueValidator

# Item quantities may be fractional (e.g. 0.5 or 1.5 litres of a 1L product).
QUANTITY_MAX_DIGITS = 8
QUANTITY_DECIMAL_PLACES = 2
MIN_QUANTITY = Decimal("0.01")
quantity_validators = [MinValueValidator(MIN_QUANTITY)]


def bottles_for(quantity):
    """Containers needed for a quantity: a part-filled bottle still counts as one (1.5 -> 2)."""
    return math.ceil(quantity or 0)


def format_quantity(quantity):
    """Human-friendly quantity: 1.00 -> "1", 1.50 -> "1.5"."""
    return f"{Decimal(quantity).normalize():f}"
