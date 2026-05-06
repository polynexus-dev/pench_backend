import logging
from decimal import Decimal
from django.utils import timezone
from .models import TaxRule, TaxType, InvoiceTaxBreakdown, ProductTaxCategory, TaxCategory

logger = logging.getLogger(__name__)


def determine_tax_type(seller_state, buyer_state):
    """
    Determines if the transaction is intra-state (SGST + CGST)
    or inter-state (IGST) based on seller and buyer locations.

    Returns:
        str: 'intra_state' or 'inter_state'
    """
    if not seller_state or not buyer_state:
        return 'intra_state'  # default to intra-state
    return 'intra_state' if seller_state.lower() == buyer_state.lower() else 'inter_state'


def get_applicable_tax_rules(state, tax_category=TaxCategory.STANDARD, date=None):
    """
    Fetches active tax rules for a given state and tax category.

    Returns:
        QuerySet of TaxRule objects applicable today.
    """
    if date is None:
        date = timezone.now().date()

    rules = TaxRule.objects.filter(
        state__iexact=state,
        tax_category=tax_category,
        is_active=True,
        effective_from__lte=date,
    ).filter(
        models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=date)
    )
    return rules


def calculate_order_tax(order, seller_state=None, buyer_state=None):
    """
    Calculates GST breakdown for an order based on product tax categories
    and the seller/buyer state combination.

    Args:
        order: Order instance with items
        seller_state: City state (seller)
        buyer_state: Customer state (buyer)

    Returns:
        dict: {
            'is_inter_state': bool,
            'total_tax': Decimal,
            'breakdowns': [
                {'tax_type': str, 'rate': Decimal, 'taxable': Decimal, 'tax': Decimal, 'rule': TaxRule}
            ]
        }
    """
    from django.db import models as django_models

    transaction_type = determine_tax_type(seller_state, buyer_state)
    is_inter_state = transaction_type == 'inter_state'

    breakdowns = []
    total_tax = Decimal('0.00')

    for item in order.items.select_related('product').all():
        taxable_amount = item.quantity * item.unit_price

        # Determine product tax category
        try:
            ptc = item.product.tax_category_info
            tax_cat = ptc.tax_category
        except ProductTaxCategory.DoesNotExist:
            tax_cat = TaxCategory.STANDARD

        if tax_cat == TaxCategory.EXEMPT:
            continue

        # Determine state for rule lookup
        state = buyer_state or seller_state or ''
        date = timezone.now().date()

        if is_inter_state:
            # IGST
            rules = TaxRule.objects.filter(
                state__iexact=state,
                tax_category=tax_cat,
                tax_type=TaxType.IGST,
                is_active=True,
                effective_from__lte=date,
            ).filter(
                django_models.Q(effective_to__isnull=True) | django_models.Q(effective_to__gte=date)
            )
        else:
            # SGST + CGST
            rules = TaxRule.objects.filter(
                state__iexact=state,
                tax_category=tax_cat,
                tax_type__in=[TaxType.SGST, TaxType.CGST],
                is_active=True,
                effective_from__lte=date,
            ).filter(
                django_models.Q(effective_to__isnull=True) | django_models.Q(effective_to__gte=date)
            )

        if not rules.exists():
            # Fallback: apply default 18% split
            logger.warning(
                'No tax rules found for state=%s, category=%s. Using defaults.',
                state, tax_cat,
            )
            if is_inter_state:
                tax = round(taxable_amount * Decimal('0.18'), 2)
                breakdowns.append({
                    'tax_type': TaxType.IGST,
                    'rate': Decimal('18.00'),
                    'taxable': taxable_amount,
                    'tax': tax,
                    'rule': None,
                })
                total_tax += tax
            else:
                for tt, rate in [(TaxType.SGST, Decimal('9.00')), (TaxType.CGST, Decimal('9.00'))]:
                    tax = round(taxable_amount * (rate / Decimal('100')), 2)
                    breakdowns.append({
                        'tax_type': tt,
                        'rate': rate,
                        'taxable': taxable_amount,
                        'tax': tax,
                        'rule': None,
                    })
                    total_tax += tax
        else:
            for rule in rules:
                tax = round(taxable_amount * (rule.rate_percentage / Decimal('100')), 2)
                breakdowns.append({
                    'tax_type': rule.tax_type,
                    'rate': rule.rate_percentage,
                    'taxable': taxable_amount,
                    'tax': tax,
                    'rule': rule,
                })
                total_tax += tax

    return {
        'is_inter_state': is_inter_state,
        'total_tax': total_tax,
        'breakdowns': breakdowns,
    }


def create_invoice_tax_breakdowns(invoice, tax_data):
    """
    Creates InvoiceTaxBreakdown records from the tax calculation result.

    Args:
        invoice: Invoice instance
        tax_data: dict from calculate_order_tax()
    """
    for bd in tax_data['breakdowns']:
        InvoiceTaxBreakdown.objects.create(
            invoice=invoice,
            tax_rule=bd['rule'],
            taxable_amount=bd['taxable'],
            tax_amount=bd['tax'],
            tax_type=bd['tax_type'],
        )
