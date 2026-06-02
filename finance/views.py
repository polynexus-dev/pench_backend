from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from core.permissions import IsERPUser, HasGroupPermission
from .models import MonthlyBill, Transaction, BillStatus
from .serializers import MonthlyBillSerializer, TransactionSerializer
from .services import bulk_generate_monthly_bills


class MonthlyBillViewSet(viewsets.ModelViewSet):
    queryset = (
        MonthlyBill.objects.all()
        .select_related("customer")
        .prefetch_related("transactions")
    )
    serializer_class = MonthlyBillSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Accountants", "ERP_Admins"]
    filterset_fields = ["status", "customer"]

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

        # 3. Delivered Orders breakdown
        year = bill.billing_month.year
        month = bill.billing_month.month
        start_date = datetime.date(year, month, 1)
        if month == 12:
            end_date = datetime.date(year + 1, 1, 1)
        else:
            end_date = datetime.date(year, month + 1, 1)

        orders = Order.objects.filter(
            customer=customer,
            status=OrderStatus.DELIVERED,
            scheduled_delivery_date__gte=start_date,
            scheduled_delivery_date__lt=end_date,
        ).order_by("scheduled_delivery_date")

        pdf.set_font("helvetica", "B", 12)
        pdf.cell(
            w=0, h=6, text="Delivered Orders Breakdown", new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(2)

        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_text_color(71, 85, 105)

        pdf.cell(w=40, h=6, text="Order Date", border=1, fill=True)
        pdf.cell(w=60, h=6, text="Order ID / Reference", border=1, fill=True)
        pdf.cell(w=50, h=6, text="Status", border=1, fill=True)
        pdf.cell(
            w=40,
            h=6,
            text="Amount (INR)",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)

        if not orders.exists():
            pdf.cell(
                w=190,
                h=6,
                text="No delivered orders logged for this billing period.",
                border=1,
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        else:
            for order in orders:
                if pdf.get_y() > 250:
                    pdf.add_page()
                    pdf.set_font("helvetica", "B", 9)
                    pdf.set_fill_color(248, 250, 252)
                    pdf.set_text_color(71, 85, 105)
                    pdf.cell(w=40, h=6, text="Order Date", border=1, fill=True)
                    pdf.cell(
                        w=60, h=6, text="Order ID / Reference", border=1, fill=True
                    )
                    pdf.cell(w=50, h=6, text="Status", border=1, fill=True)
                    pdf.cell(
                        w=40,
                        h=6,
                        text="Amount (INR)",
                        border=1,
                        align="R",
                        fill=True,
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                    pdf.set_font("helvetica", "", 9)
                    pdf.set_text_color(15, 23, 42)

                order_date = order.scheduled_delivery_date.strftime("%d %b %Y")
                order_id = str(order.id)[:8].upper()
                pdf.cell(w=40, h=6, text=order_date, border=1)
                pdf.cell(w=60, h=6, text=f"ORD-{order_id}", border=1)
                pdf.cell(w=50, h=6, text=order.status.capitalize(), border=1)
                pdf.cell(
                    w=40,
                    h=6,
                    text=f"{order.total:.2f}",
                    border=1,
                    align="R",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

        pdf.ln(8)

        # 4. Payment Register
        transactions = bill.transactions.all().order_by("payment_date")

        pdf.set_font("helvetica", "B", 12)
        pdf.cell(
            w=0, h=6, text="Received Payments History", new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(2)

        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_text_color(71, 85, 105)

        pdf.cell(w=45, h=6, text="Payment Date", border=1, fill=True)
        pdf.cell(w=45, h=6, text="Method", border=1, fill=True)
        pdf.cell(w=60, h=6, text="Transaction ID", border=1, fill=True)
        pdf.cell(
            w=40,
            h=6,
            text="Amount (INR)",
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)

        if not transactions.exists():
            pdf.cell(
                w=190,
                h=6,
                text="No payments recorded against this invoice.",
                border=1,
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        else:
            for tx in transactions:
                if pdf.get_y() > 250:
                    pdf.add_page()
                    pdf.set_font("helvetica", "B", 9)
                    pdf.set_fill_color(248, 250, 252)
                    pdf.set_text_color(71, 85, 105)
                    pdf.cell(w=45, h=6, text="Payment Date", border=1, fill=True)
                    pdf.cell(w=45, h=6, text="Method", border=1, fill=True)
                    pdf.cell(w=60, h=6, text="Transaction ID", border=1, fill=True)
                    pdf.cell(
                        w=40,
                        h=6,
                        text="Amount (INR)",
                        border=1,
                        align="R",
                        fill=True,
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                    pdf.set_font("helvetica", "", 9)
                    pdf.set_text_color(15, 23, 42)

                tx_date = tx.payment_date.strftime("%d %b %Y %H:%M")
                pdf.cell(w=45, h=6, text=tx_date, border=1)
                pdf.cell(w=45, h=6, text=tx.payment_method.capitalize(), border=1)
                pdf.cell(w=60, h=6, text=tx.transaction_id or "N/A", border=1)
                pdf.cell(
                    w=40,
                    h=6,
                    text=f"{tx.amount:.2f}",
                    border=1,
                    align="R",
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
