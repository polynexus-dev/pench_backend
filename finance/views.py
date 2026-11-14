from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from core.permissions import IsERPUser, HasGroupPermission
from .models import MonthlyBill, Transaction, BillStatus, OnlinePayment, OnlinePaymentStatus
from .serializers import (
    MonthlyBillSerializer,
    MonthlyBillListSerializer,
    TransactionSerializer,
    OnlinePaymentSerializer,
)
from .services import bulk_generate_monthly_bills


class MonthlyBillViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyBillSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Accountants", "ERP_Admins"]
    filterset_fields = ["status", "customer"]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "download_pdf"]:
            return [IsAuthenticated()]
        return [IsERPUser(), HasGroupPermission()]

    def get_serializer_class(self):
        if self.action == "list":
            return MonthlyBillListSerializer
        return MonthlyBillSerializer

    def _scope_to_user(self, qs):
        user = self.request.user
        if IsERPUser().has_permission(self.request, self):
            return qs
        if hasattr(user, "customer_profile") and user.customer_profile is not None:
            return qs.filter(customer=user.customer_profile)
        return qs.none()

    def get_queryset(self):
        if self.action == "list":
            return self._scope_to_user(
                MonthlyBill.objects.select_related("customer")
                .annotate(transaction_count=Count("transactions"))
            )
        return self._scope_to_user(
            MonthlyBill.objects.all()
            .select_related("customer")
            .prefetch_related("transactions")
        )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        Returns global finance dashboard KPI metrics:
        - total_outstanding: Sum of all unpaid/partial remaining amounts
        - collected_today: Sum of transactions recorded today
        - total_bills: Count of all bills
        - paid_count / unpaid_count / partial_count: Status distributions
        - collection_rate: Percentage of total billed that has been collected
        """
        today = timezone.localdate()

        bills = MonthlyBill.objects.all()

        total_billed = bills.aggregate(total=Sum("total_amount"))["total"] or 0
        total_collected = bills.aggregate(total=Sum("amount_paid"))["total"] or 0
        total_outstanding = float(total_billed) - float(total_collected)

        collected_today = (
            Transaction.objects.filter(payment_date__date=today).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        status_counts = bills.values("status").annotate(count=Count("id"))
        status_map = {item["status"]: item["count"] for item in status_counts}

        collection_rate = (
            (float(total_collected) / float(total_billed) * 100) if total_billed else 0
        )

        return Response(
            {
                "total_outstanding": round(float(total_outstanding), 2),
                "total_billed": round(float(total_billed), 2),
                "total_collected": round(float(total_collected), 2),
                "collected_today": round(float(collected_today), 2),
                "collection_rate": round(collection_rate, 1),
                "total_bills": bills.count(),
                "paid_count": status_map.get(BillStatus.PAID, 0),
                "unpaid_count": status_map.get(BillStatus.UNPAID, 0),
                "partial_count": status_map.get(BillStatus.PARTIAL, 0),
            }
        )

    @action(detail=False, methods=["post"], url_path="trigger-generation")
    def trigger_generation(self, request):
        """
        Manually trigger billing for a specific month/year.
        Example: {"year": 2024, "month": 4}
        """
        year = request.data.get("year")
        month = request.data.get("month")

        if not all([year, month]):
            return Response({"detail": "year and month are required."}, status=400)

        count = bulk_generate_monthly_bills(int(year), int(month))
        return Response(
            {"detail": f"Generated {count} bills for period {month}/{year}."}
        )

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request, pk=None):
        """
        Generates a premium PDF invoice for the specified bill.
        """
        bill = self.get_object()

        from django.http import HttpResponse
        from fpdf import FPDF
        import datetime
        from orders.models import Order, OrderStatus

        class InvoicePDF(FPDF):
            def __init__(self, bill, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.bill = bill

            def header(self):
                # Top bar background
                self.set_fill_color(30, 41, 59)  # Slate-800
                self.rect(0, 0, 210, 42, "F")

                # Title
                self.set_xy(15, 12)
                self.set_text_color(255, 255, 255)
                self.set_font("helvetica", "B", 22)
                self.cell(w=0, h=8, text="PENCH FOODS", new_x="LMARGIN", new_y="NEXT")

                self.set_font("helvetica", "I", 9)
                self.set_text_color(203, 213, 225)  # Slate-300
                self.cell(
                    w=0,
                    h=5,
                    text="Premium Dairy & Farm Fresh Deliveries",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

                # Invoice Title (Right aligned)
                self.set_xy(130, 12)
                self.set_text_color(255, 255, 255)
                self.set_font("helvetica", "B", 20)
                self.cell(
                    w=65, h=8, text="INVOICE", align="R", new_x="LMARGIN", new_y="NEXT"
                )

                # Reset position for body
                self.set_y(48)
                self.set_text_color(0, 0, 0)

            def footer(self):
                self.set_y(-25)
                self.set_font("helvetica", "I", 8)
                self.set_text_color(100, 116, 139)  # Slate-500
                self.cell(
                    w=0,
                    h=4,
                    text="Thank you for your business! For any billing queries, contact billing@penchfoods.com",
                    align="C",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
                self.cell(w=0, h=4, text=f"Page {self.page_no()}/{{nb}}", align="C")

        # Create PDF object
        pdf = InvoicePDF(bill)
        pdf.alias_nb_pages()
        pdf.add_page()

        # 1. Invoice details block
        pdf.set_y(48)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(71, 85, 105)  # Slate-600
        pdf.cell(w=100, h=5, text="BILLED TO:")
        pdf.cell(
            w=90, h=5, text="INVOICE DETAILS:", align="R", new_x="LMARGIN", new_y="NEXT"
        )

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(15, 23, 42)  # Slate-900

        customer = bill.customer
        client_name = customer.name
        client_company = customer.company
        client_phone = customer.phone
        client_email = customer.email
        client_address = customer.address or "No address provided"

        # Invoice metadata
        inv_num = bill.invoice_number
        inv_month = bill.billing_month.strftime("%B %Y")
        inv_due = bill.due_date.strftime("%d %b %Y")
        inv_status = bill.status.upper()

        # side-by-side lines
        lines_left = [
            client_name,
            f"Company: {client_company}" if client_company else None,
            f"Phone: {client_phone}" if client_phone else None,
            f"Email: {client_email}",
            f"Address: {client_address}",
        ]
        lines_left = [l for l in lines_left if l]

        lines_right = [
            f"Invoice No: {inv_num}",
            f"Billing Period: {inv_month}",
            f"Due Date: {inv_due}",
            f"Status: {inv_status}",
        ]

        max_lines = max(len(lines_left), len(lines_right))
        for i in range(max_lines):
            left_text = lines_left[i] if i < len(lines_left) else ""
            right_text = lines_right[i] if i < len(lines_right) else ""

            # Print left column
            if len(left_text) > 45:
                left_text = left_text[:42] + "..."

            pdf.set_font("helvetica", "B" if i == 0 else "", 10)
            pdf.cell(w=100, h=5, text=left_text)

            # Print right column
            pdf.set_font(
                "helvetica", "B" if i == 0 or "Status" in right_text else "", 10
            )
            if "Status: PAID" in right_text:
                pdf.set_text_color(22, 163, 74)  # Green-600
            elif "Status: PARTIAL" in right_text:
                pdf.set_text_color(217, 119, 6)  # Amber-600
            elif "Status: UNPAID" in right_text:
                pdf.set_text_color(220, 38, 38)  # Red-600
            else:
                pdf.set_text_color(15, 23, 42)

            pdf.cell(
                w=90, h=5, text=right_text, align="R", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.set_text_color(15, 23, 42)  # reset

        pdf.ln(8)

        # Horizontal separator
        pdf.set_draw_color(226, 232, 240)  # Slate-200
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

        # 2. Financial Overview summary
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(w=0, h=6, text="Financial Summary", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Table of Summary
        pdf.set_font("helvetica", "B", 10)
        pdf.set_fill_color(248, 250, 252)  # Slate-50
        pdf.set_text_color(71, 85, 105)

        pdf.cell(w=50, h=8, text="Total Billed Amount", border=1, align="C", fill=True)
        pdf.cell(w=50, h=8, text="Amount Paid", border=1, align="C", fill=True)
        pdf.cell(w=50, h=8, text="Outstanding Balance", border=1, align="C", fill=True)
        pdf.cell(
            w=40,
            h=8,
            text="Status",
            border=1,
            align="C",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(w=50, h=8, text=f"INR {bill.total_amount:,.2f}", border=1, align="C")
        pdf.cell(w=50, h=8, text=f"INR {bill.amount_paid:,.2f}", border=1, align="C")
        pdf.cell(
            w=50, h=8, text=f"INR {bill.remaining_amount:,.2f}", border=1, align="C"
        )

        if bill.status == "paid":
            pdf.set_text_color(22, 163, 74)
        elif bill.status == "partial":
            pdf.set_text_color(217, 119, 6)
        else:
            pdf.set_text_color(220, 38, 38)
        pdf.cell(
            w=40,
            h=8,
            text=inv_status,
            border=1,
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(15, 23, 42)  # reset

        pdf.ln(8)

        # 3. Comprehensive Breakdown using build_monthly_bill_breakdown
        from .services import build_monthly_bill_breakdown

        bd = build_monthly_bill_breakdown(bill)
        sub_summary = bd["subscription_summary"]
        extra_summary = bd["extra_orders_summary"]
        ded_summary = bd["deductions_and_credits"]
        calc = bd["final_calculation"]

        # Section A: Weekly Subscription Deliveries Breakdown (Scheduled vs Skipped vs Delivered)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(
            w=0,
            h=6,
            text="1. Subscription Weekly Delivery Breakdown (Charged Only for Delivered Days)",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)

        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(w=22, h=6, text="Week", border=1, align="C", fill=True)
        pdf.cell(w=42, h=6, text="Billing Period", border=1, align="C", fill=True)
        pdf.cell(w=28, h=6, text="Scheduled Days", border=1, align="C", fill=True)
        pdf.cell(w=28, h=6, text="Skipped / Missed", border=1, align="C", fill=True)
        pdf.cell(w=28, h=6, text="Delivered Days", border=1, align="C", fill=True)
        pdf.cell(w=18, h=6, text="Rate/Day", border=1, align="R", fill=True)
        pdf.cell(
            w=24,
            h=6,
            text="Charged (INR)",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(15, 23, 42)
        for w in sub_summary["weeks"]:
            pdf.cell(w=22, h=6, text=f"Week {w['week_number']}", border=1, align="C")
            pdf.cell(w=42, h=6, text=w["period"], border=1, align="C")
            pdf.cell(w=28, h=6, text=f"{w['scheduled_days']} days", border=1, align="C")
            pdf.cell(
                w=28,
                h=6,
                text=f"{w['skipped_or_missed_days']} days",
                border=1,
                align="C",
            )
            pdf.cell(w=28, h=6, text=f"{w['delivered_days']} days", border=1, align="C")
            pdf.cell(w=18, h=6, text=f"{w['rate_per_day']:.2f}", border=1, align="R")
            pdf.cell(
                w=24,
                h=6,
                text=f"{w['charged_amount']:.2f}",
                border=1,
                align="R",
                new_x="LMARGIN",
                new_y="NEXT",
            )

        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(248, 250, 252)
        pdf.cell(w=64, h=6, text="Subscription Monthly Subtotal", border=1, fill=True)
        pdf.cell(
            w=28,
            h=6,
            text=f"{sub_summary['total_scheduled_days']} days",
            border=1,
            align="C",
            fill=True,
        )
        pdf.cell(
            w=28,
            h=6,
            text=f"{sub_summary['total_skipped_or_missed_days']} days",
            border=1,
            align="C",
            fill=True,
        )
        pdf.cell(
            w=28,
            h=6,
            text=f"{sub_summary['total_delivered_days']} days",
            border=1,
            align="C",
            fill=True,
        )
        pdf.cell(w=18, h=6, text="-", border=1, align="C", fill=True)
        pdf.cell(
            w=24,
            h=6,
            text=f"{sub_summary['subscription_gross_total']:.2f}",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(5)

        # Section B: Mid-Month Extra / Additional Orders
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(
            w=0,
            h=6,
            text="2. Mid-Month Additional / Extra Orders",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)

        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(w=24, h=6, text="Order Date", border=1, fill=True)
        pdf.cell(w=26, h=6, text="Order Ref", border=1, fill=True)
        pdf.cell(w=56, h=6, text="Items Ordered", border=1, fill=True)
        pdf.cell(w=40, h=6, text="Payment Choice", border=1, fill=True)
        pdf.cell(w=22, h=6, text="Order Amt", border=1, align="R", fill=True)
        pdf.cell(
            w=22,
            h=6,
            text="Paid at Order",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(15, 23, 42)
        if not extra_summary["orders"]:
            pdf.cell(
                w=190,
                h=6,
                text="No mid-month additional orders placed in this billing period.",
                border=1,
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        else:
            for eo in extra_summary["orders"]:
                items_txt = (
                    eo["items_summary"][:32] + "..."
                    if len(eo["items_summary"]) > 35
                    else eo["items_summary"]
                )
                pdf.cell(w=24, h=6, text=eo["date"], border=1)
                pdf.cell(w=26, h=6, text=eo["order_ref"], border=1)
                pdf.cell(w=56, h=6, text=items_txt, border=1)
                pdf.cell(w=40, h=6, text=eo["payment_tag"], border=1)
                pdf.cell(w=22, h=6, text=f"{eo['total']:.2f}", border=1, align="R")
                pdf.cell(
                    w=22,
                    h=6,
                    text=f"{eo['paid_at_order']:.2f}",
                    border=1,
                    align="R",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
        pdf.ln(5)

        # Section C: Deductions / Prepaid Credits & Payments
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(
            w=0,
            h=6,
            text="3. Less: Deductions & Payments Already Received",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)

        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(w=32, h=6, text="Date", border=1, fill=True)
        pdf.cell(w=64, h=6, text="Deduction / Credit Type", border=1, fill=True)
        pdf.cell(w=60, h=6, text="Reference / Transaction ID", border=1, fill=True)
        pdf.cell(
            w=34,
            h=6,
            text="Deducted (INR)",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(15, 23, 42)
        if not ded_summary["items"]:
            pdf.cell(
                w=190,
                h=6,
                text="No upfront order payments or bill credits recorded yet.",
                border=1,
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        else:
            for d_item in ded_summary["items"]:
                pdf.cell(w=32, h=6, text=d_item["date"], border=1)
                pdf.cell(w=64, h=6, text=d_item["type"], border=1)
                pdf.cell(w=60, h=6, text=d_item["reference"], border=1)
                pdf.set_text_color(22, 163, 74)
                pdf.cell(
                    w=34,
                    h=6,
                    text=f"- {d_item['amount']:.2f}",
                    border=1,
                    align="R",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
                pdf.set_text_color(15, 23, 42)
        pdf.ln(5)

        # Section D: Final Bill Calculation Box
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(
            w=0,
            h=6,
            text="4. Final Monthly Bill Calculation",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)

        orders_value = calc["subscription_charges"] + calc["mid_month_extra_orders"]
        unpaid_subtotal = max(0.0, orders_value - calc["less_deductions_and_payments"])
        calc_rows = [
            (
                f"(+) Subscription Charges ({sub_summary['total_delivered_days']}/{sub_summary['total_scheduled_days']} Delivered Days)",
                f"INR {calc['subscription_charges']:,.2f}",
                False,
            ),
            (
                f"(+) Mid-Month Additional Orders ({extra_summary['count']} Extra Orders)",
                f"INR {calc['mid_month_extra_orders']:,.2f}",
                False,
            ),
            (
                "(=) Total Monthly Orders Value",
                f"INR {orders_value:,.2f}",
                True,
            ),
            (
                "(-) Less: Already Paid (Prepaid Extra Orders / Subscription Credits)",
                f"- INR {calc['less_deductions_and_payments']:,.2f}",
                False,
            ),
            (
                "(=) Unpaid Bill Subtotal",
                f"INR {unpaid_subtotal:,.2f}",
                True,
            ),
            (
                "(+) Packing & Handling Charges",
                f"INR {calc['packing_and_handling_charges']:,.2f}",
                False,
            ),
            (
                "(=) NET PAYABLE BALANCE (Remaining Amount)",
                f"INR {calc['net_payable_balance']:,.2f}",
                True,
            ),
        ]
        for label_txt, val_txt, is_bold in calc_rows:
            pdf.set_font("helvetica", "B" if is_bold else "", 9)
            if "NET PAYABLE" in label_txt:
                pdf.set_fill_color(239, 246, 255)
                fill = True
            elif is_bold:
                pdf.set_fill_color(248, 250, 252)
                fill = True
            else:
                fill = False
            pdf.cell(w=145, h=7, text=label_txt, border=1, fill=fill)
            pdf.cell(
                w=45,
                h=7,
                text=val_txt,
                border=1,
                align="R",
                fill=fill,
                new_x="LMARGIN",
                new_y="NEXT",
            )

        pdf_content = pdf.output()
        response = HttpResponse(bytes(pdf_content), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="Invoice_{bill.invoice_number}.pdf"'
        )
        return response


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = (
        Transaction.objects.all()
        .select_related("bill__customer")
        .order_by("-payment_date")
    )
    serializer_class = TransactionSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Accountants", "ERP_Admins"]
    filterset_fields = ["bill", "payment_method"]

    def get_queryset(self):
        qs = super().get_queryset()
        customer_id = self.request.query_params.get("customer")
        if customer_id:
            qs = qs.filter(bill__customer_id=customer_id)
        return qs


class OnlinePaymentViewSet(viewsets.ModelViewSet):
    """
    Online payments submitted by customers with a screenshot.
    Customers submit and view their own payments; admins verify or reject them.
    """

    serializer_class = OnlinePaymentSerializer
    required_groups = ["Accountants", "ERP_Admins"]
    filterset_fields = ["status", "purpose", "customer", "subscription", "order", "bill"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "create"]:
            return [IsAuthenticated()]
        return [IsERPUser(), HasGroupPermission()]

    def _customer_profile(self):
        user = self.request.user
        if hasattr(user, "customer_profile") and user.customer_profile is not None:
            return user.customer_profile
        return None

    def _is_admin(self):
        return IsERPUser().has_permission(self.request, self)

    def get_queryset(self):
        qs = OnlinePayment.objects.select_related(
            "customer", "bill", "verified_by"
        )
        if self._is_admin():
            return qs
        customer = self._customer_profile()
        if customer:
            return qs.filter(customer=customer)
        return qs.none()

    def create(self, request, *args, **kwargs):
        if not self._is_admin():
            customer = self._customer_profile()
            if not customer:
                from rest_framework.exceptions import PermissionDenied

                raise PermissionDenied("Only customers or admins can submit payments.")
            # Customers can only submit payments for themselves.
            data = request.data.copy()
            data["customer"] = str(customer.id)
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        from django.db import transaction as db_transaction
        from orders.models import PaymentStatus

        with db_transaction.atomic():
            payment = serializer.save(submitted_by=self.request.user)
            # Flag the order as awaiting verification until an admin reviews it.
            order = payment.order
            if order and order.payment_status != PaymentStatus.PAID:
                order.payment_status = PaymentStatus.VERIFICATION_PENDING
                order.save(update_fields=["payment_status"])

    def perform_destroy(self, instance):
        from django.db import transaction as db_transaction
        from orders.models import PaymentStatus

        with db_transaction.atomic():
            order = instance.order
            was_pending = instance.status == OnlinePaymentStatus.PENDING
            instance.delete()
            # Drop the flag if no other submitted payment is still awaiting review.
            if (
                order
                and was_pending
                and order.payment_status == PaymentStatus.VERIFICATION_PENDING
                and not order.online_payments.filter(
                    status=OnlinePaymentStatus.PENDING
                ).exists()
            ):
                order.payment_status = PaymentStatus.PENDING
                order.save(update_fields=["payment_status"])

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        payment = self.get_object()
        if payment.status != OnlinePaymentStatus.PENDING:
            return Response(
                {"detail": f"Payment is already {payment.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment.verify(request.user)
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        payment = self.get_object()
        if payment.status != OnlinePaymentStatus.PENDING:
            return Response(
                {"detail": f"Payment is already {payment.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"reason": "A rejection reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment.reject(request.user, reason)
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["get"], url_path="screenshot")
    def screenshot(self, request, pk=None):
        payment = self.get_object()
        if not payment.screenshot:
            return Response(
                {"detail": "No screenshot uploaded for this payment."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            from django.http import FileResponse
            return FileResponse(payment.screenshot.open("rb"))
        except (FileNotFoundError, ValueError):
            return Response(
                {"detail": "Screenshot file could not be found on storage."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        Dashboard counts for online payments.
        Optional query params: year, month (filters by submission date).
        """
        qs = OnlinePayment.objects.all()
        year = request.query_params.get("year")
        month = request.query_params.get("month")
        try:
            if year:
                qs = qs.filter(created_at__year=int(year))
            if month:
                qs = qs.filter(created_at__month=int(month))
        except ValueError:
            return Response(
                {"detail": "Invalid year or month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def bucket(status_value):
            sub = qs.filter(status=status_value)
            agg = sub.aggregate(
                count=Count("id"),
                customers=Count("customer", distinct=True),
                amount=Sum("amount"),
            )
            return {
                "count": agg["count"],
                "customers": agg["customers"],
                "amount": float(agg["amount"] or 0),
            }

        by_purpose = {
            row["purpose"]: row["count"]
            for row in qs.filter(status=OnlinePaymentStatus.PENDING)
            .values("purpose")
            .annotate(count=Count("id"))
        }

        return Response(
            {
                "total_customers_paid_online": qs.values("customer").distinct().count(),
                "pending": bucket(OnlinePaymentStatus.PENDING),
                "verified": bucket(OnlinePaymentStatus.VERIFIED),
                "rejected": bucket(OnlinePaymentStatus.REJECTED),
                "pending_by_purpose": by_purpose,
            }
        )


# ──────────────────────────────────────────────────────────────────────────────
# PayU Payment Gateway Views (Orders, Monthly Bills & Subscriptions)
# ──────────────────────────────────────────────────────────────────────────────

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from django.db import connection, transaction as db_transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import OnlinePaymentPurpose
from .payu import (
    build_user_credentials,
    calculate_command_hash,
    calculate_request_hash,
    estimate_subscription_amount,
    fetch_payu_verify_payment,
    format_payu_amount,
    generate_mobile_sdk_hash,
    generate_seamless_sdk_hashes,
    generate_txnid,
    get_payu_config,
    reconcile_payu_callback,
    verify_response_hash,
)


def _append_query_params(url: str, params: dict) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.update({k: str(v) for k, v in params.items() if v is not None})
    return urlunparse(parsed._replace(query=urlencode(query)))


class PayUInitiateView(APIView):
    """
    POST /api/erp/finance/payu/initiate/
    Initiates a PayU checkout session for:
      - Special / Extra Order: {"order": "<order_uuid>"}
      - Monthly Bill:          {"bill": "<bill_uuid>", "amount": "<optional_partial_amount>"}
      - Subscription:          {"subscription": "<subscription_uuid>", "amount": "<optional_amount>"}
    Computes the authoritative amount on the server, creates a PENDING OnlinePayment record
    tagged with `payment_gateway="payu"`, and returns the signed PayU parameters and hash.
    """

    permission_classes = [IsAuthenticated]

    def _is_admin(self, request):
        return IsERPUser().has_permission(request, self)

    def _customer_profile(self, request):
        user = request.user
        if hasattr(user, "customer_profile") and user.customer_profile is not None:
            return user.customer_profile
        return None

    def post(self, request):
        cfg = get_payu_config()
        if not cfg["key"] or not cfg["salt"]:
            return Response(
                {"detail": "PayU gateway credentials are not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        order_id = request.data.get("order") or request.data.get("order_id")
        bill_id = request.data.get("bill") or request.data.get("bill_id")
        subscription_id = (
            request.data.get("subscription") or request.data.get("subscription_id")
        )
        raw_amount = request.data.get("amount")

        targets = [bool(order_id), bool(bill_id), bool(subscription_id)]
        if sum(targets) != 1:
            return Response(
                {
                    "detail": "Specify exactly one payment target: 'order', 'bill', or 'subscription'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_admin = self._is_admin(request)
        customer_profile = self._customer_profile(request)
        if not is_admin and not customer_profile:
            return Response(
                {"detail": "Only customers or admins can initiate payments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        order = None
        bill = None
        subscription = None
        customer = None
        amount = None
        purpose = OnlinePaymentPurpose.GENERAL
        productinfo = "Pench Foods Payment"
        target_uuid = ""

        # 1. Special / Extra Order (or any Order)
        if order_id:
            from orders.models import Order, PaymentStatus

            try:
                order = Order.objects.select_related("customer").get(id=order_id)
            except (Order.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
                )

            if not is_admin and order.customer_id != customer_profile.id:
                return Response(
                    {"detail": "Order does not belong to you."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            remaining = Decimal(str(order.remaining_amount))
            if order.payment_status == PaymentStatus.PAID or remaining <= 0:
                return Response(
                    {"detail": "This order has already been fully paid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if raw_amount is not None and str(raw_amount).strip() != "":
                try:
                    amount = Decimal(str(raw_amount))
                except (InvalidOperation, ValueError):
                    return Response(
                        {"amount": "Invalid payment amount."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if amount <= 0 or amount > remaining:
                    return Response(
                        {
                            "amount": f"Amount must be between 0.01 and {remaining:.2f}."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                amount = remaining

            customer = order.customer
            purpose = OnlinePaymentPurpose.ORDER
            productinfo = f"Order {str(order.id)[:8].upper()}"
            target_uuid = str(order.id)

        # 2. Monthly Bill
        elif bill_id:
            try:
                bill = MonthlyBill.objects.select_related("customer").get(id=bill_id)
            except (MonthlyBill.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Monthly bill not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not is_admin and bill.customer_id != customer_profile.id:
                return Response(
                    {"detail": "Monthly bill does not belong to you."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            remaining = Decimal(str(bill.remaining_amount))
            if bill.status == BillStatus.PAID or remaining <= 0:
                return Response(
                    {"detail": "This monthly bill is already fully paid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if raw_amount is not None and str(raw_amount).strip() != "":
                try:
                    amount = Decimal(str(raw_amount))
                except (InvalidOperation, ValueError):
                    return Response(
                        {"amount": "Invalid payment amount."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if amount <= 0 or amount > remaining:
                    return Response(
                        {
                            "amount": f"Amount must be between 0.01 and {remaining:.2f}."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                amount = remaining

            customer = bill.customer
            purpose = OnlinePaymentPurpose.BILL
            productinfo = f"Monthly Bill {bill.invoice_number}"
            target_uuid = str(bill.id)

        # 3. Subscription
        elif subscription_id:
            from subscriptions.models import Subscription

            try:
                subscription = (
                    Subscription.objects.select_related("customer")
                    .prefetch_related("items__product")
                    .get(id=subscription_id)
                )
            except (Subscription.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Subscription not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not is_admin and subscription.customer_id != customer_profile.id:
                return Response(
                    {"detail": "Subscription does not belong to you."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if raw_amount is not None and str(raw_amount).strip() != "":
                try:
                    amount = Decimal(str(raw_amount))
                except (InvalidOperation, ValueError):
                    return Response(
                        {"amount": "Invalid payment amount."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                amount = estimate_subscription_amount(subscription)

            if amount <= 0:
                return Response(
                    {"amount": "Subscription payment amount must be greater than zero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            customer = subscription.customer
            purpose = OnlinePaymentPurpose.SUBSCRIPTION
            productinfo = f"Subscription {str(subscription.id)[:8].upper()}"
            target_uuid = str(subscription.id)

        amount_str = format_payu_amount(amount)
        txnid = generate_txnid()

        with db_transaction.atomic():
            payment = OnlinePayment.objects.create(
                customer=customer,
                amount=Decimal(amount_str),
                purpose=purpose,
                order=order,
                bill=bill,
                subscription=subscription,
                payment_gateway="payu",
                gateway_txnid=txnid,
                status=OnlinePaymentStatus.PENDING,
                submitted_by=request.user,
            )

        callback_url = request.build_absolute_uri("/api/erp/finance/payu/callback/")
        if request.is_secure() or request.META.get("HTTP_X_FORWARDED_PROTO") == "https":
            if callback_url.startswith("http://"):
                callback_url = "https://" + callback_url[7:]

        surl = request.data.get("surl") or callback_url
        furl = request.data.get("furl") or callback_url
        frontend_redirect = str(request.data.get("frontend_redirect_url") or "")

        raw_firstname = (customer.name or "Customer").strip().split(" ")[0]
        firstname = "".join(ch for ch in raw_firstname if ch.isalnum())[:60] or "Customer"
        email = (customer.email or getattr(request.user, "email", "") or "customer@penchfoods.com").strip()
        raw_phone = (customer.phone or getattr(request.user, "phone", "") or "").strip()
        digits_phone = "".join(ch for ch in raw_phone if ch.isdigit())
        phone = digits_phone[-10:] if len(digits_phone) >= 10 else (digits_phone or "9999999999")
        schema_name = getattr(connection, "schema_name", "") or ""
        user_identifier = phone or email or str(customer.id)
        user_credentials = (
            str(request.data.get("user_credentials") or "").strip()
            or build_user_credentials(cfg["key"], user_identifier)
        )
        sdk_environment = "1" if cfg["mode"] == "TEST" else "0"

        form_fields = {
            "key": cfg["key"],
            "txnid": txnid,
            "amount": amount_str,
            "productinfo": productinfo,
            "firstname": firstname,
            "email": email,
            "phone": phone,
            "surl": surl,
            "furl": furl,
            "udf1": schema_name,
            "udf2": str(payment.id),
            "udf3": frontend_redirect,
            "udf4": purpose,
            "udf5": target_uuid,
        }
        hashes = generate_seamless_sdk_hashes(
            params=form_fields,
            user_credentials=user_credentials,
            key=cfg["key"],
            salt=cfg["salt"],
        )
        form_fields["hash"] = hashes["payment_hash"]

        params = {
            **form_fields,
            "user_credentials": user_credentials,
            "environment": sdk_environment,
        }

        return Response(
            {
                "payment_id": str(payment.id),
                "online_payment_id": str(payment.id),
                "txnid": txnid,
                "amount": amount_str,
                "purpose": purpose,
                "mode": cfg["mode"],
                "payu_env": cfg["mode"],
                "environment": sdk_environment,
                "is_production": cfg["mode"] == "LIVE",
                "action_url": cfg["action_url"],
                "payu_action_url": cfg["action_url"],
                "user_credentials": user_credentials,
                "params": params,
                "form_fields": form_fields,
                "hashes": hashes,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class PayUCallbackView(APIView):
    """
    POST /api/erp/finance/payu/callback/  (and /api/payu/callback/)
    Handles browser redirects (surl / furl) from PayU after checkout completion.
    Verifies the reverse SHA-512 hash, reconciles the OnlinePayment (and linked Order,
    MonthlyBill, or Subscription), and either redirects to the frontend/mobile deep-link
    or returns JSON.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = {k: request.data.get(k) for k in request.data.keys()}
        if not verify_response_hash(payload):
            return Response(
                {"detail": "Invalid PayU signature hash."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment, outcome = reconcile_payu_callback(payload)
        if outcome == "not_found" or payment is None:
            return Response(
                {"detail": "Payment transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cfg = get_payu_config()
        payu_status = str(payload.get("status", "") or "").strip().lower()
        is_success = payu_status == "success"

        redirect_base = (
            str(payload.get("udf3", "") or "").strip()
            or (cfg["success_redirect_url"] if is_success else cfg["failure_redirect_url"])
        )

        result_params = {
            "status": "success" if is_success else "failure",
            "outcome": outcome,
            "txnid": payment.gateway_txnid,
            "mihpayid": payment.gateway_mihpayid,
            "payment_id": str(payment.id),
            "payment_status": payment.status,
            "purpose": payment.purpose,
        }

        if redirect_base:
            target_url = _append_query_params(redirect_base, result_params)
            res = HttpResponse(status=status.HTTP_302_FOUND)
            res["Location"] = target_url
            return res

        return Response(result_params, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class PayUWebhookView(APIView):
    """
    POST /api/erp/finance/payu/webhook/  (and /api/payu/webhook/)
    Server-to-server webhook endpoint for PayU asynchronous notifications.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = {k: request.data.get(k) for k in request.data.keys()}
        if not verify_response_hash(payload):
            return Response(
                {"detail": "Invalid PayU signature hash."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment, outcome = reconcile_payu_callback(payload)
        if outcome == "not_found" or payment is None:
            return Response(
                {"detail": "Payment transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "status": "success" if payment.status == OnlinePaymentStatus.VERIFIED else "failure",
                "outcome": outcome,
                "txnid": payment.gateway_txnid,
                "mihpayid": payment.gateway_mihpayid,
                "payment_id": str(payment.id),
                "payment_status": payment.status,
                "purpose": payment.purpose,
            },
            status=status.HTTP_200_OK,
        )


class PayUMobileHashView(APIView):
    """
    POST /api/erp/finance/payu/mobile-hash/
    Supports both:
      1. PayU CoreSDK Seamless Integration command hashes (`sha512(key|command|var1|salt)`):
         {"command": "validateVPA" | "vas_for_mobile_sdk" | "payment_related_details_for_mobile_sdk" | "check_is_domestic" | ..., "var1": "...", "hashName": "..."}
      2. PayU CheckoutPro / CoreSDK dynamic hashString callback (`sha512(hashString + salt)`):
         {"hashName": "...", "hashString": "...", "postSalt": "..."}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        cfg = get_payu_config()
        if not cfg["key"] or not cfg["salt"]:
            return Response(
                {"detail": "PayU gateway credentials are not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        command = request.data.get("command")
        var1 = request.data.get("var1", "default")
        hash_string = request.data.get("hashString") or request.data.get("hash_string")
        hash_name = request.data.get("hashName") or request.data.get("hash_name") or command or "hash"
        post_salt = request.data.get("postSalt") or request.data.get("post_salt")
        hash_type = request.data.get("hashType") or request.data.get("hash_type")

        if command:
            computed = calculate_command_hash(
                command=str(command).strip(),
                var1=str(var1) if var1 is not None else "default",
                key=cfg["key"],
                salt=cfg["salt"],
            )
        elif hash_string:
            computed = generate_mobile_sdk_hash(
                hash_string=str(hash_string),
                post_salt=str(post_salt) if post_salt else None,
                salt=cfg["salt"],
                hash_type=str(hash_type) if hash_type else None,
            )
        else:
            return Response(
                {"detail": "Provide either 'command' (and optional 'var1') or 'hashString'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "hashName": hash_name,
                hash_name: computed,
                "hash": computed,
            },
            status=status.HTTP_200_OK,
        )


class PayUPaymentStatusView(APIView):
    """
    GET /api/erp/finance/payu/status/<txnid>/?verify=1
    POST /api/erp/finance/payu/status/<txnid>/
    Allows Web and Mobile (CoreSDK Seamless) clients to check the status of a PayU
    transaction by `txnid` or `OnlinePayment.id`.
    If `?verify=1` (or POST) is used while the payment is still PENDING, queries
    PayU's `verify_payment` WebService API directly to reconcile on demand.
    """

    permission_classes = [IsAuthenticated]

    def _get_payment(self, request, txnid):
        qs = OnlinePayment.objects.select_related("customer", "bill", "order", "subscription")
        if not IsERPUser().has_permission(request, self):
            customer = getattr(request.user, "customer_profile", None)
            if not customer:
                return None, Response(status=status.HTTP_403_FORBIDDEN)
            qs = qs.filter(customer=customer)

        payment = qs.filter(gateway_txnid=txnid).first()
        if not payment:
            try:
                payment = qs.filter(id=txnid).first()
            except ValueError:
                payment = None

        if not payment:
            return None, Response(
                {"detail": "Payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return payment, None

    def _sync_with_payu_if_pending(self, payment):
        if payment.status != OnlinePaymentStatus.PENDING or not payment.gateway_txnid:
            return payment
        try:
            res = fetch_payu_verify_payment(payment.gateway_txnid)
            txn_details = (res.get("transaction_details") or {}).get(
                payment.gateway_txnid
            )
            if isinstance(txn_details, dict):
                payu_st = str(txn_details.get("status") or "").strip().lower()
                if payu_st in ("success", "failure", "failed"):
                    txn_details.setdefault("txnid", payment.gateway_txnid)
                    reconciled, _ = reconcile_payu_callback(txn_details)
                    if reconciled:
                        return reconciled
        except Exception:
            pass
        payment.refresh_from_db()
        return payment

    def get(self, request, txnid):
        payment, err_response = self._get_payment(request, txnid)
        if err_response:
            return err_response

        if str(request.query_params.get("verify", "")).lower() in ("1", "true", "yes"):
            payment = self._sync_with_payu_if_pending(payment)

        return Response(
            OnlinePaymentSerializer(payment, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, txnid):
        payment, err_response = self._get_payment(request, txnid)
        if err_response:
            return err_response

        payment = self._sync_with_payu_if_pending(payment)
        return Response(
            OnlinePaymentSerializer(payment, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class PayUSandboxTestPageView(APIView):
    """
    GET /api/erp/finance/payu/sandbox-test/
    Renders a self-contained HTML test harness for testing PayU Sandbox payments
    (Orders, Monthly Bills, and Subscriptions) end-to-end in the browser.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.shortcuts import render

        cfg = get_payu_config()
        return render(
            request,
            "finance/payu_sandbox_test.html",
            {"payu_mode": cfg["mode"], "payu_key": cfg["key"]},
        )


class HandlingFeeSlabsView(APIView):
    """
    GET /api/erp/finance/handling-fee-slabs/?amount=200&payment_method=payu
    Returns the configured Packing & Handling fee slabs and calculates the exact
    fee for a given cart/order/bill amount so the frontend/mobile app can preview it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from decimal import Decimal, InvalidOperation
        from .services import PACKING_AND_HANDLING_SLABS, get_packing_and_handling_slab

        slabs_out = [
            {
                "min_amount": float(s["min_amount"]),
                "max_amount": float(s["max_amount"]) if s["max_amount"] is not None else None,
                "handling_fee": float(s["fee"]),
                "label": s["label"],
            }
            for s in PACKING_AND_HANDLING_SLABS
        ]

        raw_amount = request.query_params.get("amount")
        payment_method = (request.query_params.get("payment_method") or "payu").lower()
        calculation = None

        if raw_amount is not None:
            try:
                base_amt = Decimal(str(raw_amount))
            except (InvalidOperation, ValueError):
                return Response(
                    {"amount": "Must be a valid number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if payment_method == "on_account":
                calculation = {
                    "items_subtotal": float(base_amt),
                    "payment_method": "on_account",
                    "handling_fee": 0.0,
                    "slab_label": "Added to Monthly Bill (Handling fee applied once on Monthly Bill)",
                    "total_payable_now": 0.0,
                    "added_to_monthly_bill": float(base_amt),
                }
            else:
                slab = get_packing_and_handling_slab(base_amt)
                fee = slab["fee"]
                calculation = {
                    "items_subtotal": float(base_amt),
                    "payment_method": payment_method,
                    "handling_fee": float(fee),
                    "slab_label": slab["label"],
                    "total_payable_now": float(base_amt + fee),
                }

        return Response(
            {
                "slabs": slabs_out,
                "calculation": calculation,
            },
            status=status.HTTP_200_OK,
        )



