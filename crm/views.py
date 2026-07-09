from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.permissions import HasGroupPermission
from .models import Customer, Lead, HAS_GIS, _parse_coordinates, _point_in_polygon
from .serializers import CustomerSerializer, CustomerListSerializer, LeadSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.filter(is_active=True).select_related("zone", "user").prefetch_related(
        "custom_prices", "subscriptions", "monthly_bills", "orders"
    )
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasGroupPermission]
    required_groups = ["CRM_Managers", "ERP_Admins"]
    search_fields = ["name", "company", "email", "phone"]
    ordering_fields = ["name", "created_at"]
    filterset_fields = ["is_active", "is_new", "trial_approved", "zone"]

    def get_queryset(self):
        if self.action == "list":
            # Optimized subqueries for listings to avoid N+1 queries and memory inflation
            from django.db.models import OuterRef, Subquery, IntegerField, DecimalField, Count, Sum, F, Value
            from django.db.models.functions import Coalesce
            from subscriptions.models import Subscription, SubscriptionStatus
            from finance.models import MonthlyBill, BillStatus
            from orders.models import Order

            active_subs_sub = Subscription.objects.filter(
                customer=OuterRef("pk"),
                status=SubscriptionStatus.ACTIVE
            ).values("customer").annotate(count=Count("id")).values("count")

            pending_balance_sub = MonthlyBill.objects.filter(
                customer=OuterRef("pk")
            ).exclude(status=BillStatus.CANCELLED).values("customer").annotate(
                pending=Sum(
                    F("total_amount") - F("amount_paid"),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )
            ).values("pending")

            total_orders_sub = Order.objects.filter(
                customer=OuterRef("pk")
            ).values("customer").annotate(count=Count("id")).values("count")

            return (
                Customer.objects.filter(is_active=True)
                .select_related("zone", "user")
                .annotate(
                    annotated_active_subs=Coalesce(Subquery(active_subs_sub, output_field=IntegerField()), 0),
                    annotated_pending_balance=Coalesce(
                        Subquery(pending_balance_sub, output_field=DecimalField(max_digits=10, decimal_places=2)),
                        Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
                        output_field=DecimalField(max_digits=10, decimal_places=2)
                    ),
                    annotated_total_orders=Coalesce(Subquery(total_orders_sub, output_field=IntegerField()), 0),
                )
            )

        return super().get_queryset()

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        return CustomerSerializer

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple customers in a single POST request.
        Just send a JSON list instead of a single object.
        """
        is_many = isinstance(request.data, list)
        
        from django.db import IntegrityError, transaction
        
        if not is_many:
            try:
                with transaction.atomic():
                    return super().create(request, *args, **kwargs)
            except IntegrityError as e:
                err_msg = str(e)
                if "crm_customer_email_key" in err_msg or "email" in err_msg.lower():
                    detail = "A customer with this email already exists."
                elif "crm_customer_phone_key" in err_msg or "phone" in err_msg.lower():
                    detail = "A customer with this phone number already exists."
                else:
                    detail = f"Database integrity error: {err_msg}"
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk creation payload validations - Skip duplicate phone/email by clearing them / using dummy values
        payload = request.data
        processed_payload = []
        skipped_records = []
        
        seen_emails = set()
        seen_phones = set()
        
        existing_phones = {p.strip() for p in Customer.objects.values_list("phone", flat=True) if p}
        existing_emails = {e.strip().lower() for e in Customer.objects.exclude(email__isnull=True).exclude(email="").values_list("email", flat=True) if e}
        
        import random
        import string
        import time

        for i, item in enumerate(payload):
            row_num = i + 1
            if not isinstance(item, dict):
                skipped_records.append({
                    "row": row_num,
                    "reason": "Invalid record format (expected JSON object)"
                })
                continue
                
            name = item.get("name", "")
            phone = item.get("phone")
            email = item.get("email")
            
            # Clean inputs
            email_clean = email.strip().lower() if email else None
            phone_clean = phone.strip() if phone else None
            
            # Check/Sanitize phone: if duplicate, generate unique dummy phone
            if not phone_clean:
                random_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
                timestamp = int(time.time() * 1000) % 1000000
                phone_clean = f"N/A-{random_str}-{timestamp}"
            elif (phone_clean in existing_phones) or (phone_clean in seen_phones):
                random_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
                timestamp = int(time.time() * 1000) % 1000000
                phone_clean = f"N/A-{random_str}-{timestamp}"
            else:
                seen_phones.add(phone_clean)
                
            # Check/Sanitize email: if duplicate, set email to None (skip adding)
            if email_clean:
                if (email_clean in existing_emails) or (email_clean in seen_emails):
                    email_clean = None
                else:
                    seen_emails.add(email_clean)
            
            # Update item with processed values
            item["phone"] = phone_clean
            item["email"] = email_clean
            processed_payload.append((row_num, item))

        valid_serializers = []
        for row_num, item in processed_payload:
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                valid_serializers.append((row_num, serializer, item))
            else:
                errors_str = "; ".join([f"{k}: {v[0] if isinstance(v, list) else v}" for k, v in serializer.errors.items()])
                skipped_records.append({
                    "row": row_num,
                    "name": item.get("name", ""),
                    "phone": item.get("phone", ""),
                    "email": item.get("email", ""),
                    "reason": f"Validation errors: {errors_str}"
                })

        imported_records = []
        if valid_serializers:
            from accounts.models import User
            from django_tenants.utils import schema_context
            from django.db import connection
            
            target_schema = connection.schema_name
            
            try:
                with transaction.atomic():
                    for row_num, s, item in valid_serializers:
                        # 1. Save Customer Profile
                        instance = s.save()
                        
                        # 2. Extract Names for user creation (strip MR/MS/MRS prefixes)
                        name_str = instance.name.strip()
                        title_prefixes = ["mr.", "ms.", "mrs.", "mr", "ms", "mrs", "dr.", "dr"]
                        parts = name_str.split()
                        if parts and parts[0].lower() in title_prefixes:
                            parts = parts[1:]
                        
                        if len(parts) >= 2:
                            first_name = parts[0]
                            last_name = parts[1]
                        elif len(parts) == 1:
                            first_name = parts[0]
                            last_name = ""
                        else:
                            first_name = "customer"
                            last_name = ""

                        # 3. Build Username: lowercase firstname.lastname
                        first_clean = "".join(c for c in first_name.lower() if c.isalnum())
                        last_clean = "".join(c for c in last_name.lower() if c.isalnum())
                        if last_clean:
                            username = f"{first_clean}.{last_clean}"
                        else:
                            username = first_clean
                            
                        if not username:
                            username = f"user_{str(instance.id)[:8]}"
                            
                        # Ensure username uniqueness in public schema
                        base_username = username
                        counter = 1
                        with schema_context("public"):
                            while User.objects.filter(username=username).exists():
                                username = f"{base_username}{counter}"
                                counter += 1
                                
                            # Create new user in public schema with Welcome@pench password
                            new_user = User.objects.create(
                                username=username,
                                phone=instance.phone if instance.phone and not instance.phone.startswith("N/A-") else None,
                                email=instance.email if instance.email else f"{username}@penchfoods.in",
                                first_name=first_name,
                                last_name=last_name,
                                is_customer=True,
                                tenant_schema=target_schema,
                                is_active=True
                            )
                            new_user.set_password("Welcome@pench")
                            new_user.save()
                            
                        # 4. Link User to Customer
                        instance.user = new_user
                        instance.save(update_fields=["user"])
                        
                        imported_records.append(self.get_serializer(instance).data)
            except IntegrityError as e:
                # Fallback database constraint check
                return Response(
                    {"detail": f"Database integrity error during bulk import save: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        return Response({
            "imported_count": len(imported_records),
            "skipped_count": len(skipped_records),
            "imported": imported_records,
            "skipped": skipped_records
        }, status=status.HTTP_201_CREATED if imported_records else status.HTTP_200_OK)

    def perform_destroy(self, instance):
        user = instance.user
        instance.delete()
        if user:
            from django_tenants.utils import schema_context
            with schema_context("public"):
                user.delete()

    @action(detail=False, methods=["patch", "put"])
    def bulk_update(self, request):
        """
        Updates multiple customers at once.
        Each object in the list MUST have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list of objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_customers = []
        for item in data:
            customer_id = item.get("id")
            if not customer_id:
                continue

            try:
                instance = Customer.objects.get(id=customer_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated_customers.append(serializer.data)
            except Customer.DoesNotExist:
                continue

        return Response(updated_customers, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """
        Deletes multiple customers and their dependencies.
        Accepts:
          - A list of customer UUIDs: `["uuid1", "uuid2"]`
          - A dict wrapper: `{"ids": ["uuid1", "uuid2"]}` or `{"customer_ids": ["uuid1", "uuid2"]}`
        """
        import uuid
        from django.db import transaction, models
        from accounts.models import User
        from orders.models import Order
        from finance.models import MonthlyBill

        data = request.data
        customer_ids = None

        if isinstance(data, list):
            customer_ids = data
        elif isinstance(data, dict):
            customer_ids = data.get("ids") or data.get("customer_ids")

        if not customer_ids or not isinstance(customer_ids, list):
            return Response(
                {
                    "detail": "Expected a list of customer IDs, either as a flat JSON array or wrapped in 'ids' or 'customer_ids'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse and validate UUIDs
        cleaned_ids = []
        for cid in customer_ids:
            try:
                cleaned_ids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                continue

        if not cleaned_ids:
            return Response(
                {"detail": "No valid UUIDs found in the provided list of customer IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Filter customers in the active schema context
        customers_qs = Customer.objects.filter(id__in=cleaned_ids)
        if not customers_qs.exists():
            return Response(
                {"detail": "No customers found matching the provided IDs."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build list of deleted customers metadata to return
        deleted_details = []
        for cust in customers_qs:
            deleted_details.append(
                {
                    "id": str(cust.id),
                    "name": cust.name,
                    "email": cust.email,
                }
            )

        # Extract user IDs linked to the selected customers before deletion
        user_ids = list(
            customers_qs.exclude(user__isnull=True).values_list(
                "user_id", flat=True
            )
        )

        try:
            with transaction.atomic():
                # 1. Delete protected Orders
                order_del_count, _ = Order.objects.filter(
                    customer__in=customers_qs
                ).delete()

                # 2. Delete protected MonthlyBills
                bill_del_count, _ = MonthlyBill.objects.filter(
                    customer__in=customers_qs
                ).delete()

                # 3. Delete Customer profiles (cascades: Subscription, CustomerBottleBalance, CustomerProductPrice)
                cust_del_count, _ = customers_qs.delete()

                # 4. Safely handle associated User accounts (shared app)
                user_del_count = 0
                if user_ids:
                    # Users to delete (no other role flags)
                    users_to_delete = User.objects.filter(id__in=user_ids).exclude(
                        models.Q(is_staff=True)
                        | models.Q(is_superuser=True)
                        | models.Q(is_erp_user=True)
                        | models.Q(is_driver=True)
                    )
                    user_del_count, _ = users_to_delete.delete()

                    # Users to keep (have other roles) -> clear is_customer flag
                    users_to_keep = User.objects.filter(id__in=user_ids).filter(
                        models.Q(is_staff=True)
                        | models.Q(is_superuser=True)
                        | models.Q(is_erp_user=True)
                        | models.Q(is_driver=True)
                    )
                    for user in users_to_keep:
                        user.is_customer = False
                        user.save(update_fields=["is_customer"])

            return Response(
                {
                    "message": f"Successfully deleted {len(deleted_details)} customers and their dependencies.",
                    "deleted_customers": deleted_details,
                    "summary": {
                        "orders_deleted": order_del_count,
                        "monthly_bills_deleted": bill_del_count,
                        "customer_profiles_deleted": cust_del_count,
                        "user_accounts_deleted": user_del_count,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"detail": f"An error occurred during deletion: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _generate_qr_label_image(self, request, customer):
        import qrcode
        import os
        from django.conf import settings
        from PIL import Image, ImageDraw, ImageFont

        # --- COLORS & CONFIG ---
        pench_green = (0, 150, 70)
        dark_bg = (20, 30, 40)
        text_color = (255, 255, 255)

        # 1. Generate QR Code
        from django.urls import reverse

        resolve_url = reverse(
            "customer-qr-resolve", kwargs={"qr_id": str(customer.qr_code_id)}
        )

        # Build a reachable QR code URL. If running locally and request is 'localhost' / '127.0.0.1',
        # try to use a registered non-localhost tenant domain (e.g. nip.io or public domain) so
        # that mobile devices scanning the QR can resolve and reach the server.
        current_host = request.get_host()
        base_url = None
        if ("localhost" in current_host or "127.0.0.1" in current_host) and getattr(
            request, "tenant", None
        ):
            from tenants.models import Domain

            tenant_domains = Domain.objects.filter(tenant=request.tenant)
            reachable_domains = [
                d.domain
                for d in tenant_domains
                if "localhost" not in d.domain and "127.0.0.1" not in d.domain
            ]
            if reachable_domains:
                # Prefer local wifi domains (e.g. nip.io or IP-based) for local testing on the same network,
                # fallback to public domains.
                local_wifi = [
                    d
                    for d in reachable_domains
                    if "nip.io" in d or any(c.isdigit() for c in d.split(".")[0])
                ]
                public_domains = [d for d in reachable_domains if d not in local_wifi]

                preferred_domain = local_wifi[0] if local_wifi else public_domains[0]

                # Use HTTP or HTTPS depending on domain type
                is_local = "nip.io" in preferred_domain or any(
                    c.isdigit() for c in preferred_domain.split(".")[0]
                )
                scheme = "https" if request.is_secure() or not is_local else "http"

                # Keep port for local IP/nip.io if present in request
                port = ""
                if ":" in current_host and is_local:
                    port = ":" + current_host.split(":")[1]

                base_url = f"{scheme}://{preferred_domain}{port}"

        if base_url:
            full_url = f"{base_url}{resolve_url}"
        else:
            full_url = request.build_absolute_uri(resolve_url)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=7,  # Shrunk to ensure it never overlaps text
            border=2,
        )
        qr.add_data(full_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color=pench_green, back_color="white").convert(
            "RGB"
        )

        # 2. Canvas Setup (Optimized for A4 aspect ratio to minimize margins)
        width, height = qr_img.size
        canvas_width = 600
        canvas_height = 850

        canvas = Image.new("RGB", (canvas_width, canvas_height), pench_green)
        draw = ImageDraw.Draw(canvas)

        # 3. Draw Stylized Background
        draw.polygon(
            [(0, 0), (canvas_width, 0), (canvas_width, 420), (0, 590)], fill=dark_bg
        )

        # 3.5. Draw Inclined Watermark
        logo_path = os.path.join(settings.BASE_DIR, "Untitled design-8 (2).png")
        wm_layer = Image.new(
            "RGBA", (canvas_width * 2, canvas_height * 2), (0, 0, 0, 0)
        )
        wm_draw = ImageDraw.Draw(wm_layer)

        wm_logo = None
        if os.path.exists(logo_path):
            wm_logo = Image.open(logo_path).convert("RGBA")
            wm_logo.thumbnail((50, 50), Image.Resampling.LANCZOS)
            # Make logo 15% opacity
            r, g, b, a = wm_logo.split()
            a = a.point(lambda p: p * 0.15)
            wm_logo.putalpha(a)

        try:
            wm_font = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 35)
        except Exception:
            wm_font = ImageFont.load_default()

        wm_text_color = (255, 255, 255, 30)  # Low opacity white text

        step_x = 280
        step_y = 120
        for y in range(0, canvas_height * 2, step_y):
            for x in range(0, canvas_width * 2, step_x):
                # Offset every other row for brick-like tiling
                offset_x = x if (y // step_y) % 2 == 0 else x - (step_x // 2)

                # Alternate between Logo and Text
                if (x // step_x + y // step_y) % 2 == 0:
                    if wm_logo:
                        wm_layer.paste(wm_logo, (offset_x, y), wm_logo)
                    else:
                        wm_draw.text(
                            (offset_x, y), "PENCH", fill=wm_text_color, font=wm_font
                        )
                else:
                    wm_draw.text(
                        (offset_x, y), "PENCH FOODS", fill=wm_text_color, font=wm_font
                    )

        # Rotate by 45 degrees to make it inclined
        wm_layer = wm_layer.rotate(45, resample=Image.Resampling.BICUBIC)

        # Center crop the oversized watermark layer to fit the canvas
        left = (wm_layer.width - canvas_width) // 2
        top = (wm_layer.height - canvas_height) // 2
        wm_layer = wm_layer.crop((left, top, left + canvas_width, top + canvas_height))

        # Paste watermark onto the main canvas background
        canvas.paste(wm_layer, (0, 0), wm_layer)

        # 4. Embed Logo in QR
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo_max_size = int(width * 0.25)
            logo.thumbnail((logo_max_size, logo_max_size), Image.Resampling.LANCZOS)

            qr_w, qr_h = qr_img.size
            logo_pos = ((qr_w - logo.size[0]) // 2, (qr_h - logo.size[1]) // 2)

            logo_bg = Image.new(
                "RGBA", (logo.size[0] + 12, logo.size[1] + 12), (255, 255, 255, 255)
            )
            qr_img.paste(logo_bg, (logo_pos[0] - 6, logo_pos[1] - 6), logo_bg)
            qr_img.paste(logo, logo_pos, logo)

        # 5. Paste QR onto Canvas (Centered vertically)
        qr_x = (canvas_width - width) // 2
        qr_y = 190
        canvas.paste(qr_img, (qr_x, qr_y))

        # 6. Load Professional Font
        try:
            # Using Segoe UI for a more modern, premium look instead of basic Arial
            font_bold = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 60)
            font_small = ImageFont.truetype(
                "C:\\Windows\\Fonts\\segoeuib.ttf", 26
            )  # Bold & Larger Footer
            font_title = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 60) # Larger Title
            font_customer = ImageFont.truetype(
                "C:\\Windows\\Fonts\\segoeuib.ttf", 40
            )  # Bold & Larger ID
        except Exception:
            font_bold = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_title = ImageFont.load_default()
            font_customer = ImageFont.load_default()

        # 7. Add Text with Impact
        # Title
        draw.text(
            (canvas_width / 2, 80),
            "PENCH FOODS",
            fill=text_color,
            anchor="mm",
            font=font_title,
        )

        # Privacy-Safe Identifier (NO NAME, NO ADDRESS)
        # We generate a readable 6-digit ID like "PENCH-482917" from the QR UUID.
        # This will be printed on the sticker AND can be exported to Excel later.
        unique_num = str(customer.qr_code_id.int)[:6]
        display_text = f"ID: PENCH-{unique_num}"

        # Draw the ID right beneath the QR code (centered in the green region)
        draw.text(
            (canvas_width / 2, 680),
            display_text,
            fill=dark_bg,
            anchor="mm",
            font=font_customer,
        )

        # Small Footer sitting neatly at the bottom edge
        footer_text = "Powered by Polynexus Technologies"
        draw.text(
            (canvas_width / 2, 810),
            footer_text,
            fill=(255, 255, 255, 200),
            anchor="mm",
            font=font_small,
        )

        return canvas

    @action(detail=True, methods=["get"], url_path="download-qr")
    def download_qr(self, request, pk=None):
        """
        Generates and returns a single page A4 PDF containing the QR label at row 0, col 0, with full cutting lines.
        """
        customer = self.get_object()
        from io import BytesIO
        from django.http import HttpResponse
        from PIL import Image, ImageDraw

        canvas = self._generate_qr_label_image(request, customer)

        # A4 page at 300 DPI
        page_width, page_height = 2480, 3508
        cols, rows = 3, 3
        # 600x850 aspect ratio stickers
        sticker_width, sticker_height = 750, 1060
        card_gap = 30  # Gap/gutter between stickers

        total_width = cols * sticker_width + (cols - 1) * card_gap
        total_height = rows * sticker_height + (rows - 1) * card_gap

        # Calculate margins for centering 3x3 grid with gutters
        margin_x = (page_width - total_width) // 2
        margin_y = (page_height - total_height) // 2

        def draw_dashed_line(
            draw, pt1, pt2, fill, width=1, dash_length=20, gap_length=15
        ):
            x1, y1 = pt1
            x2, y2 = pt2
            dx = x2 - x1
            dy = y2 - y1
            distance = (dx**2 + dy**2) ** 0.5
            if distance == 0:
                return

            ux = dx / distance
            uy = dy / distance

            current_dist = 0
            while current_dist < distance:
                sx = x1 + ux * current_dist
                sy = y1 + uy * current_dist

                current_dist += dash_length
                if current_dist > distance:
                    current_dist = distance
                ex = x1 + ux * current_dist
                ey = y1 + uy * current_dist

                draw.line([(sx, sy), (ex, ey)], fill=fill, width=width)
                current_dist += gap_length

        def finalize_page(page):
            draw_lines = ImageDraw.Draw(page)
            line_color = (80, 80, 80)  # Visible dark gray
            line_width = 4

            # Horizontal lines - drawn in the middle of gutters + outer borders
            for r in range(rows + 1):
                if r == 0:
                    ly = margin_y
                elif r == rows:
                    ly = margin_y + rows * sticker_height + (rows - 1) * card_gap
                else:
                    ly = (
                        margin_y
                        + r * sticker_height
                        + (r - 1) * card_gap
                        + card_gap // 2
                    )

                draw_dashed_line(
                    draw_lines,
                    (margin_x - 60, ly),
                    (margin_x + total_width + 60, ly),
                    fill=line_color,
                    width=line_width,
                )

            # Vertical lines - drawn in the middle of gutters + outer borders
            for c in range(cols + 1):
                if c == 0:
                    lx = margin_x
                elif c == cols:
                    lx = margin_x + cols * sticker_width + (cols - 1) * card_gap
                else:
                    lx = (
                        margin_x
                        + c * sticker_width
                        + (c - 1) * card_gap
                        + card_gap // 2
                    )

                draw_dashed_line(
                    draw_lines,
                    (lx, margin_y - 60),
                    (lx, margin_y + total_height + 60),
                    fill=line_color,
                    width=line_width,
                )

        # Draw the single page PDF
        page = Image.new("RGB", (page_width, page_height), "white")

        # Resize the 600x850 sticker to larger 750x1060 to fit 3x3 layout
        sticker_resized = canvas.resize(
            (sticker_width, sticker_height), Image.Resampling.LANCZOS
        )

        # Paste at row 0, col 0 (top-left)
        page.paste(sticker_resized, (margin_x, margin_y))

        # Finalize page by drawing the grid lines
        finalize_page(page)

        # Save as PDF
        buffer = BytesIO()
        page.save(buffer, format="PDF", resolution=300.0)
        buffer.seek(0)

        unique_num = str(customer.qr_code_id.int)[:6]
        filename = f"qr_sticker_customer_PENCH-{unique_num}.pdf"

        response = HttpResponse(buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["get"], url_path="view-qr")
    def view_qr(self, request, pk=None):
        """
        Generates and returns a single PNG image containing the styled QR sticker label.
        """
        customer = self.get_object()
        from io import BytesIO
        from django.http import HttpResponse

        canvas = self._generate_qr_label_image(request, customer)
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        buffer.seek(0)

        response = HttpResponse(buffer, content_type="image/png")
        return response

    @action(detail=False, methods=["get", "post"], url_path="bulk-download-qr")
    def bulk_download_qr(self, request):
        """
        Generates a ZIP archive containing:
        1. A multi-page A4 PDF with customer QR stickers in a 3x3 grid.
        2. A CSV mapping file (opens in Excel) matching the Sticker IDs to customer details.
        Supports filtering by customer IDs passed via GET query params or POST request body.
        """
        import csv
        import zipfile
        from io import BytesIO, StringIO
        from django.http import HttpResponse
        from PIL import Image, ImageDraw

        customers = self.get_queryset()

        # Extract customer IDs for filtering
        customer_ids = None
        if request.method == "POST":
            customer_ids = request.data.get("ids") or request.data.get("customer_ids")
        else:
            customer_ids = request.query_params.get("ids") or request.query_params.get(
                "customer_ids"
            )

        if customer_ids is not None:
            import uuid

            parsed_ids = []
            if isinstance(customer_ids, str):
                try:
                    parsed_ids = [
                        uuid.UUID(x.strip())
                        for x in customer_ids.split(",")
                        if x.strip()
                    ]
                except ValueError:
                    return Response(
                        {
                            "detail": "Invalid format for ids. Expected a comma-separated list of UUIDs."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif isinstance(customer_ids, list):
                try:
                    parsed_ids = [uuid.UUID(str(x)) for x in customer_ids]
                except (ValueError, TypeError):
                    return Response(
                        {"detail": "Invalid format for ids. Expected a list of UUIDs."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {
                        "detail": "Invalid format for ids. Expected a list or a comma-separated string."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            customers = customers.filter(id__in=parsed_ids)
            if not customers.exists():
                return Response(
                    {"detail": "No active customers found for the specified IDs."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            if not customers.exists():
                return Response(
                    {"detail": "No active customers found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # --- 1. GENERATE PDF STICKERS ---
        # A4 page at 300 DPI
        page_width, page_height = 2480, 3508
        cols, rows = 3, 3
        # 600x850 aspect ratio stickers
        sticker_width, sticker_height = 750, 1060
        card_gap = 30  # Gap/gutter between stickers

        total_width = cols * sticker_width + (cols - 1) * card_gap
        total_height = rows * sticker_height + (rows - 1) * card_gap

        # Calculate margins for centering 3x3 grid with gutters
        margin_x = (page_width - total_width) // 2
        margin_y = (page_height - total_height) // 2

        def draw_dashed_line(
            draw, pt1, pt2, fill, width=1, dash_length=20, gap_length=15
        ):
            x1, y1 = pt1
            x2, y2 = pt2
            dx = x2 - x1
            dy = y2 - y1
            distance = (dx**2 + dy**2) ** 0.5
            if distance == 0:
                return

            ux = dx / distance
            uy = dy / distance

            current_dist = 0
            while current_dist < distance:
                sx = x1 + ux * current_dist
                sy = y1 + uy * current_dist

                current_dist += dash_length
                if current_dist > distance:
                    current_dist = distance
                ex = x1 + ux * current_dist
                ey = y1 + uy * current_dist

                draw.line([(sx, sy), (ex, ey)], fill=fill, width=width)
                current_dist += gap_length

        def finalize_page(page):
            draw_lines = ImageDraw.Draw(page)
            line_color = (80, 80, 80)  # Visible dark gray
            line_width = 4

            # Horizontal lines - drawn in the middle of gutters + outer borders
            for r in range(rows + 1):
                if r == 0:
                    ly = margin_y
                elif r == rows:
                    ly = margin_y + rows * sticker_height + (rows - 1) * card_gap
                else:
                    ly = (
                        margin_y
                        + r * sticker_height
                        + (r - 1) * card_gap
                        + card_gap // 2
                    )

                draw_dashed_line(
                    draw_lines,
                    (margin_x - 60, ly),
                    (margin_x + total_width + 60, ly),
                    fill=line_color,
                    width=line_width,
                )

            # Vertical lines - drawn in the middle of gutters + outer borders
            for c in range(cols + 1):
                if c == 0:
                    lx = margin_x
                elif c == cols:
                    lx = margin_x + cols * sticker_width + (cols - 1) * card_gap
                else:
                    lx = (
                        margin_x
                        + c * sticker_width
                        + (c - 1) * card_gap
                        + card_gap // 2
                    )

                draw_dashed_line(
                    draw_lines,
                    (lx, margin_y - 60),
                    (lx, margin_y + total_height + 60),
                    fill=line_color,
                    width=line_width,
                )

        pdf_pages = []
        current_page = Image.new("RGB", (page_width, page_height), "white")
        current_count = 0

        for customer in customers:
            sticker = self._generate_qr_label_image(request, customer)
            # Resize the 600x850 sticker to larger 750x1060 to fit 3x3 layout
            sticker_resized = sticker.resize(
                (sticker_width, sticker_height), Image.Resampling.LANCZOS
            )

            # Calculate grid position
            col = current_count % cols
            row = (current_count // cols) % rows

            x = margin_x + col * (sticker_width + card_gap)
            y = margin_y + row * (sticker_height + card_gap)

            current_page.paste(sticker_resized, (x, y))
            current_count += 1

            # If page is full, save it and create a new one
            if current_count % (cols * rows) == 0:
                finalize_page(current_page)
                pdf_pages.append(current_page)
                current_page = Image.new("RGB", (page_width, page_height), "white")

        # Append the last page if it has any stickers
        if current_count % (cols * rows) != 0:
            finalize_page(current_page)
            pdf_pages.append(current_page)

        pdf_data = b""
        if pdf_pages:
            pdf_buffer = BytesIO()
            pdf_pages[0].save(
                pdf_buffer,
                format="PDF",
                resolution=300.0,
                save_all=True,
                append_images=pdf_pages[1:],
            )
            pdf_data = pdf_buffer.getvalue()

        # --- 2. GENERATE EXCEL (CSV) MAPPING ---
        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["QR Sticker ID", "Customer Name", "Phone", "Address"])

        for customer in customers:
            unique_num = str(customer.qr_code_id.int)[:6]
            sticker_id = f"PENCH-{unique_num}"

            name = customer.name
            if not name and customer.user:
                name = customer.user.get_full_name() or customer.user.username

            phone = customer.phone or ""
            address = customer.address or ""

            writer.writerow([sticker_id, name, phone, address])

        csv_data = csv_buffer.getvalue().encode("utf-8")

        # --- 3. PACKAGE BOTH INTO A ZIP FILE ---
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("qr_stickers.pdf", pdf_data)
            zip_file.writestr("qr_mapping.csv", csv_data)

        zip_buffer.seek(0)

        response = HttpResponse(zip_buffer, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="bulk_qr_pack.zip"'
        return response

    @action(
        detail=False,
        methods=["get"],
        url_path="qr-resolve/(?P<qr_id>[^/.]+)",
        permission_classes=[AllowAny],
    )
    def qr_resolve(self, request, qr_id=None):
        """
        Resolves a Smart QR scan based on user role.
        """
        customer = Customer.objects.filter(qr_code_id=qr_id).first()
        if not customer:
            return Response({"detail": "Invalid QR Code."}, status=404)

        user = request.user
        from django.http import HttpResponseRedirect

        # Scenario 1: Delivery Person (Driver)
        if not user.is_anonymous and getattr(user, "is_driver", False):
            # Redirect to the driver app deep link
            return HttpResponseRedirect(f"pench-foods://delivery/qr/{qr_id}")

        # Scenario 2: The Customer themselves
        if not user.is_anonymous and getattr(user, "is_customer", False):
            if customer.user == user:
                # Redirect to the customer app deep link
                return HttpResponseRedirect(f"pench-foods://profile/qr/{qr_id}")
            else:
                # Scanned another customer's QR code -> route to marketing website
                return HttpResponseRedirect("https://penchfoods.com")

        # Scenario 3: Guest / Stranger / Anonymous Mobile System Scanner
        # Return a premium HTML page that triggers deep linking to launch the native app,
        # with store links and marketing info as a fallback.
        from django.http import HttpResponse

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pench Foods | Launch App</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{
            background-color: #0E1511;
            color: #FFFFFF;
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
            text-align: center;
        }}
        .container {{
            max-width: 420px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 40px 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }}
        .logo {{
            font-size: 28px;
            font-weight: 700;
            color: #009646;
            margin-bottom: 24px;
            letter-spacing: 1px;
        }}
        h1 {{
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 12px;
            color: #FFFFFF;
        }}
        p {{
            color: #A0AEC0;
            font-size: 16px;
            line-height: 1.5;
            margin-bottom: 32px;
        }}
        .btn {{
            background: #009646;
            color: #FFFFFF;
            text-decoration: none;
            padding: 16px 32px;
            border-radius: 14px;
            font-weight: 600;
            font-size: 16px;
            display: inline-block;
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(0, 150, 70, 0.3);
            border: none;
            cursor: pointer;
            width: 100%;
            box-sizing: border-box;
        }}
        .btn:hover {{
            background: #00b052;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 150, 70, 0.4);
        }}
        .footer {{
            margin-top: 40px;
            font-size: 12px;
            color: #718096;
        }}
    </style>
    <script>
        (function() {{
            var deepLink = "pench-foods://delivery/qr/{qr_id}";
            // 1. Immediate trigger
            window.location.replace(deepLink);
            
            // 2. Fallback on DOMContentLoaded
            document.addEventListener("DOMContentLoaded", function() {{
                window.location.replace(deepLink);
            }});
            
            // 3. Fallback on window load
            window.onload = function() {{
                setTimeout(function() {{
                    window.location.replace(deepLink);
                }}, 100);
            }};
        }})();
    </script>
</head>
<body>
    <div class="container">
        <div class="logo">PENCH FOODS</div>
        <h1>Opening in Native App...</h1>
        <p>If you have our mobile app installed, it should launch automatically. If it doesn't, tap below to open it manually.</p>
        
        <a href="pench-foods://delivery/qr/{qr_id}" class="btn">Open in App</a>
        
        <div class="footer">
            Powered by Polynexus Technologies
        </div>
    </div>
</body>
</html>"""
        return HttpResponse(html_content, content_type="text/html")

    @action(detail=False, methods=["post"], url_path="auto-assign-zones")
    def auto_assign_zones(self, request):
        """
        Scans all active customers in the city and auto-assigns zones based on their location.
        """
        from routing.models import Zone

        # 1. Fetch active customers with coordinates
        customers = Customer.objects.filter(is_active=True).exclude(location=None)

        # 2. Fetch active zones
        zones = Zone.objects.filter(is_active=True)

        scanned = 0
        updated = 0
        assignments = []

        # Pre-load zones to list
        zones_list = list(zones)

        for customer in customers:
            loc = customer.location
            if not loc:
                continue

            scanned += 1
            assigned_zone = None

            if HAS_GIS:
                from django.contrib.gis.geos import Point

                if not isinstance(loc, Point):
                    coords = _parse_coordinates(loc)
                    if coords:
                        loc = Point(coords[0], coords[1])
                    else:
                        continue
                assigned_zone = Zone.objects.filter(
                    boundary__contains=loc, is_active=True
                ).first()
            else:
                coords = _parse_coordinates(loc)
                if coords:
                    lng, lat = coords
                    for zone in zones_list:
                        if zone.boundary:
                            poly_coords = None
                            if isinstance(zone.boundary, dict):
                                geom_type = zone.boundary.get("type")
                                if geom_type == "Polygon":
                                    poly_coords = zone.boundary.get("coordinates")
                                elif geom_type == "MultiPolygon":
                                    poly_coords_list = zone.boundary.get(
                                        "coordinates", []
                                    )
                                    for sub_poly in poly_coords_list:
                                        if _point_in_polygon(lng, lat, sub_poly):
                                            assigned_zone = zone
                                            break
                            if assigned_zone:
                                break
                            if poly_coords and _point_in_polygon(lng, lat, poly_coords):
                                assigned_zone = zone
                                break

            if assigned_zone and customer.zone != assigned_zone:
                customer.zone = assigned_zone
                customer.save(update_fields=["zone"])
                updated += 1
                assignments.append(
                    {
                        "customer_id": str(customer.id),
                        "customer_name": customer.name,
                        "zone_id": str(assigned_zone.id),
                        "zone_name": assigned_zone.name,
                    }
                )

        return Response(
            {
                "message": "Auto-assignment completed successfully.",
                "scanned": scanned,
                "updated": updated,
                "assignments": assignments,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get", "post"], url_path="sync-refresh-customers")
    def sync_refresh_customers(self, request):
        """
        Synchronizes Customers and Users in both directions.
        GET: Check inconsistencies (Dry-run mode, does not write to database).
        POST: Performs the sync (creates or links missing accounts).
        """
        from accounts.models import User
        from django_tenants.utils import schema_context
        from django.db import connection
        from django.core.exceptions import ObjectDoesNotExist

        current_schema = connection.schema_name
        target_schema = current_schema
        
        if current_schema == "public":
            # 1. Check if a specific schema is passed in query params or POST body
            param_schema = request.query_params.get("tenant_schema") or request.data.get("tenant_schema")
            if param_schema:
                target_schema = param_schema
            # 2. Otherwise fallback to the authenticated user's tenant schema
            elif request.user and getattr(request.user, "tenant_schema", None):
                target_schema = request.user.tenant_schema

        if target_schema == "public":
            return Response(
                {"error": "This action cannot be performed in the public schema context. Please specify a tenant_schema or login as a tenant user."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Determine dry-run status
        dry_run = request.method == "GET"
        if not dry_run:
            val = request.data.get("dry_run")
            if val is not None:
                if isinstance(val, str):
                    dry_run = val.lower() == "true"
                else:
                    dry_run = bool(val)
            
            qp_val = request.query_params.get("dry_run")
            if qp_val is not None:
                dry_run = qp_val.lower() == "true"

        with schema_context(target_schema):
            # 1. Fetch current schema's default company name for new Customer profiles
            comp_name = ""
            try:
                from tenants.models import City
                city = City.objects.filter(schema_name=target_schema).select_related("company").first()
                if city and city.company:
                    comp_name = city.company.name
            except Exception:
                pass

            # Stats collections
            duplicates_merged = 0
            duplicates_deleted = 0
            duplicates_details = []

            # ──────────────────────────────────────────────────────────
            # PHASE 0: Clean up and merge duplicate customers
            # ──────────────────────────────────────────────────────────
            from collections import defaultdict
            from django.db import transaction

            all_customers = list(Customer.objects.all())
            groups = defaultdict(list)
            for c in all_customers:
                name_clean = c.name.strip().lower() if c.name else ""
                phone_clean = c.phone.strip() if c.phone else ""
                if name_clean and phone_clean:
                    groups[(name_clean, phone_clean)].append(c)

            for (name_key, phone_key), group in groups.items():
                if len(group) <= 1:
                    continue

                # Identify Primary customer
                with_user = [c for c in group if c.user_id is not None]
                if with_user:
                    primary = min(with_user, key=lambda c: c.created_at)
                else:
                    primary = min(group, key=lambda c: c.created_at)

                duplicates = [c for c in group if c.id != primary.id]

                for dup in duplicates:
                    if dup.user_id is not None:
                        continue

                    duplicates_details.append({
                        "primary_customer_id": str(primary.id),
                        "primary_customer_name": primary.name,
                        "duplicate_customer_id": str(dup.id),
                        "duplicate_customer_name": dup.name,
                        "phone": phone_key
                    })
                    
                    duplicates_merged += 1
                    duplicates_deleted += 1

                    if not dry_run:
                        with transaction.atomic():
                            # Merge key properties from dup to primary to prevent data loss.
                            # Since dup's orders and subscriptions are being moved to primary,
                            # the primary profile must adopt the delivery details (zone, location, address)
                            # of the active profile (dup).
                            primary_updated = False
                            if dup.zone and primary.zone != dup.zone:
                                primary.zone = dup.zone
                                primary_updated = True
                            if dup.location and primary.location != dup.location:
                                primary.location = dup.location
                                primary_updated = True
                            if dup.address and primary.address != dup.address:
                                primary.address = dup.address
                                primary_updated = True
                            if dup.trial_approved and not primary.trial_approved:
                                primary.trial_approved = True
                                primary_updated = True
                            if not dup.is_new and primary.is_new:
                                primary.is_new = False
                                primary_updated = True
                            if dup.is_active and not primary.is_active:
                                primary.is_active = True
                                primary_updated = True
                            if dup.email and not primary.email:
                                primary.email = dup.email
                                primary_updated = True
                            if primary_updated:
                                primary.save()


                            # 1. Update Lead.referred_by
                            from crm.models import Lead
                            Lead.objects.filter(referred_by=dup).update(referred_by=primary)

                            # 2. Update Order.customer
                            from orders.models import Order
                            Order.objects.filter(customer=dup).update(customer=primary)

                            # 3. Update Subscription.customer
                            from subscriptions.models import Subscription
                            Subscription.objects.filter(customer=dup).update(customer=primary)

                            # 4. Update BottleTransaction.customer
                            from inventory.models import BottleTransaction
                            BottleTransaction.objects.filter(customer=dup).update(customer=primary)

                            # 5. Merge CustomerBottleBalance
                            from inventory.models import CustomerBottleBalance
                            for bal in CustomerBottleBalance.objects.filter(customer=dup):
                                prim_bal, created = CustomerBottleBalance.objects.get_or_create(
                                    customer=primary,
                                    bottle_type=bal.bottle_type,
                                    defaults={'balance': 0}
                                )
                                prim_bal.balance += bal.balance
                                prim_bal.save()
                                bal.delete()

                            # 6. Merge CustomerProductPrice
                            from inventory.models import CustomerProductPrice
                            for cpp in CustomerProductPrice.objects.filter(customer=dup):
                                if not CustomerProductPrice.objects.filter(customer=primary, product=cpp.product).exists():
                                    cpp.customer = primary
                                    cpp.save()
                                else:
                                    cpp.delete()

                            # 7. Merge MonthlyBill
                            from finance.models import MonthlyBill
                            for bill in MonthlyBill.objects.filter(customer=dup):
                                if not MonthlyBill.objects.filter(customer=primary, billing_month=bill.billing_month).exists():
                                    bill.customer = primary
                                    bill.save()
                                else:
                                    prim_bill = MonthlyBill.objects.get(customer=primary, billing_month=bill.billing_month)
                                    for trans in bill.transactions.all():
                                        trans.bill = prim_bill
                                        trans.save()
                                    prim_bill.total_amount += bill.total_amount
                                    prim_bill.save()
                                    prim_bill.reconcile()
                                    bill.delete()

                            # 8. Delete the duplicate Customer profile
                            dup.delete()

            # Stats collections
            c_to_u_checked = 0
            c_to_u_already_linked = 0
            c_to_u_linked_existing = 0
            c_to_u_created_new = 0
            c_to_u_details = []

            # ──────────────────────────────────────────────────────────
            # DIRECTION 1: Customer -> User (Syncing Customers to Public Users)
            # ──────────────────────────────────────────────────────────
            customers = Customer.objects.all()
            for customer in customers:
                connection.set_schema(target_schema)
                c_to_u_checked += 1

                # If already linked, check if we need to update/verify the User settings
                if customer.user:
                    c_to_u_already_linked += 1
                    user = customer.user

                    # Verify that the user flags and tenant_schema are correct
                    user_updated = False
                    if not user.is_customer:
                        user.is_customer = True
                        user_updated = True
                    if user.tenant_schema != target_schema:
                        user.tenant_schema = target_schema
                        user_updated = True

                    if user_updated and not dry_run:
                        user.save(update_fields=['is_customer', 'tenant_schema'])
                    continue

                # Not linked. Search public User table by phone or email
                user = None
                if customer.phone:
                    phone_clean = customer.phone.strip()
                    if phone_clean:
                        user = User.objects.filter(phone=phone_clean).first()
                        if not user and len(phone_clean) >= 10:
                            last_10 = phone_clean[-10:]
                            user = User.objects.filter(phone__endswith=last_10).first()

                if not user and customer.email:
                    email_clean = customer.email.strip()
                    if email_clean:
                        user = User.objects.filter(email__iexact=email_clean).first()

                if user:
                    # Check if this user is already linked to another Customer profile
                    if Customer.objects.filter(user=user).exclude(id=customer.id).exists():
                        c_to_u_details.append({
                            "customer_id": str(customer.id),
                            "customer_name": customer.name,
                            "phone": customer.phone,
                            "email": customer.email,
                            "action": "skipped_conflict_user_already_linked",
                            "user_id": user.id,
                            "username": user.username
                        })
                        continue

                    # Link existing user
                    c_to_u_linked_existing += 1
                    c_to_u_details.append({
                        "customer_id": str(customer.id),
                        "customer_name": customer.name,
                        "phone": customer.phone,
                        "email": customer.email,
                        "action": "linked_existing_user",
                        "user_id": user.id,
                        "username": user.username
                    })

                    if not dry_run:
                        user.is_customer = True
                        user.tenant_schema = target_schema
                        user.save(update_fields=['is_customer', 'tenant_schema'])
                        
                        connection.set_schema(target_schema)
                        customer.user = user
                        customer.save(update_fields=['user'])
                else:
                    # Create a new User
                    c_to_u_created_new += 1

                    # Determine username
                    username = None
                    if customer.phone:
                        username = customer.phone.strip()
                    elif customer.email:
                        username = customer.email.strip()
                    else:
                        username = customer.name.lower().replace(" ", "")

                    if not username:
                        username = f"cust_{str(customer.id)[:8]}"

                    # Ensure username uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{counter}"
                        counter += 1

                    c_to_u_details.append({
                        "customer_id": str(customer.id),
                        "customer_name": customer.name,
                        "phone": customer.phone,
                        "email": customer.email,
                        "action": "created_new_user",
                        "username": username
                    })

                    if not dry_run:
                        name_parts = customer.name.split(None, 1)
                        first_name = name_parts[0] if name_parts else customer.name
                        last_name = name_parts[1] if len(name_parts) > 1 else ""

                        new_user = User.objects.create(
                            username=username,
                            phone=customer.phone.strip() if customer.phone else None,
                            email=customer.email.strip() if customer.email else f"{username}@penchfoods.in",
                            first_name=first_name,
                            last_name=last_name,
                            is_customer=False,
                            tenant_schema=target_schema,
                            is_active=True
                        )
                        new_user.set_unusable_password()
                        new_user.save()

                        connection.set_schema(target_schema)
                        customer.user = new_user
                        customer.save(update_fields=['user'])

                        # Now set is_customer=True on User and save
                        new_user.is_customer = True
                        new_user.save(update_fields=['is_customer'])

                        # Auto assign to Customers group
                        from django.contrib.auth.models import Group
                        group, _ = Group.objects.get_or_create(name="Customers")
                        new_user.groups.add(group)

            # Stats collections for Direction 2
            u_to_c_checked = 0
            u_to_c_already_linked = 0
            u_to_c_linked_existing = 0
            u_to_c_created_new = 0
            u_to_c_details = []

            # ──────────────────────────────────────────────────────────
            # DIRECTION 2: User -> Customer (Syncing Public Users to Customers)
            # ──────────────────────────────────────────────────────────
            connection.set_schema(target_schema)
            customer_users = User.objects.filter(is_customer=True, tenant_schema=target_schema)
            for user in customer_users:
                connection.set_schema(target_schema)
                u_to_c_checked += 1

                # Check if Customer profile exists linked to this user
                customer = Customer.objects.filter(user=user).first()
                if customer:
                    u_to_c_already_linked += 1
                    continue

                # Not linked. Search Customer by phone or email
                customer = None
                if user.phone:
                    phone_clean = user.phone.strip()
                    if phone_clean:
                        customer = Customer.objects.filter(phone=phone_clean).first()
                        if not customer and len(phone_clean) >= 10:
                            last_10 = phone_clean[-10:]
                            customer = Customer.objects.filter(phone__endswith=last_10).first()

                if not customer and user.email:
                    email_clean = user.email.strip()
                    if email_clean:
                        customer = Customer.objects.filter(email__iexact=email_clean).first()

                if customer:
                    if customer.user and customer.user != user:
                        u_to_c_details.append({
                            "user_id": user.id,
                            "username": user.username,
                            "phone": user.phone,
                            "email": user.email,
                            "action": "skipped_conflict_customer_already_linked",
                            "customer_id": str(customer.id),
                            "customer_name": customer.name
                        })
                        customer = None  # Fallback to create a new profile

                if customer:
                    # Link existing Customer to this User
                    u_to_c_linked_existing += 1
                    u_to_c_details.append({
                        "user_id": user.id,
                        "username": user.username,
                        "phone": user.phone,
                        "email": user.email,
                        "action": "linked_existing_customer",
                        "customer_id": str(customer.id),
                        "customer_name": customer.name
                    })

                    if not dry_run:
                        connection.set_schema(target_schema)
                        customer.user = user
                        customer.save(update_fields=['user'])
                else:
                    # Create a new Customer profile
                    u_to_c_created_new += 1

                    email = user.email or f"{user.username}_{user.id}@penchfoods.in"
                    base_email = email
                    counter = 1
                    while Customer.objects.filter(email=email).exists():
                        name_part, domain_part = base_email.split("@", 1) if "@" in base_email else (base_email, "penchfoods.in")
                        email = f"{name_part}_{counter}@{domain_part}"
                        counter += 1

                    u_to_c_details.append({
                        "user_id": user.id,
                        "username": user.username,
                        "phone": user.phone,
                        "email": email,
                        "action": "created_new_customer",
                        "customer_name": f"{user.first_name} {user.last_name}".strip() or user.username
                    })

                    if not dry_run:
                        connection.set_schema(target_schema)
                        Customer.objects.create(
                            user=user,
                            name=f"{user.first_name} {user.last_name}".strip() or user.username,
                            company=comp_name,
                            email=email,
                            phone=user.phone or "",
                            address="",
                            is_active=user.is_active
                        )

            return Response({
                "message": "Dry-run check completed." if dry_run else "Sync refresh completed successfully.",
                "dry_run": dry_run,
                "tenant_schema": target_schema,
                "duplicates_cleaned": {
                    "merged": duplicates_merged,
                    "deleted": duplicates_deleted,
                    "details": duplicates_details
                },
                "customer_to_user": {
                    "checked": c_to_u_checked,
                    "already_linked": c_to_u_already_linked,
                    "linked_existing_user": c_to_u_linked_existing,
                    "created_new_user": c_to_u_created_new,
                    "details": c_to_u_details
                },
                "user_to_customer": {
                    "checked": u_to_c_checked,
                    "already_linked": u_to_c_already_linked,
                    "linked_existing_customer": u_to_c_linked_existing,
                    "created_new_customer": u_to_c_created_new,
                    "details": u_to_c_details
                }
            }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="new-customers")
    def new_customers(self, request):
        """
        Endpoint to retrieve customers currently in trial mode (is_new=True).
        """
        queryset = self.get_queryset().filter(is_new=True)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve_trial(self, request, pk=None):
        """
        Approves a new customer for trial deliveries.
        Sets trial_approved = True.
        """
        customer = self.get_object()
        if not customer.is_new:
            return Response(
                {"detail": "Customer is not in trial mode (already subscribed)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer.trial_approved = True
        customer.save(update_fields=["trial_approved"])

        # Automatically assign any of this customer's pending/confirmed orders to active routes
        try:
            from orders.models import Order, OrderStatus
            from orders.services.route_generator import add_order_to_active_route_if_pending
            pending_orders = Order.objects.filter(
                customer=customer,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
            )
            for order in pending_orders:
                add_order_to_active_route_if_pending(order)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[Trial Approval Route Assignment Error] {e}")

        try:
            from notifications.services import send_push_notification
            if customer.user:
                title = "🎉 Trial Approved!"
                body = "Congratulations! Your trial has been approved. You'll receive your demo product shortly! 🚚"
                send_push_notification(
                    user=customer.user,
                    title=title,
                    body=body,
                    notification_type="general"
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[Trial Approval Notification Error] {e}")

        return Response(CustomerSerializer(customer).data)

    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve_trial(self, request):
        """
        Approves multiple new customers for trial deliveries in a single request.
        Accepts:
          - A list of customer UUIDs: `["uuid1", "uuid2"]`
          - A dict wrapper: `{"ids": ["uuid1", "uuid2"]}` or `{"customer_ids": ["uuid1", "uuid2"]}`
        """
        import uuid
        from django.db import transaction
        from orders.models import Order, OrderStatus
        from orders.services.route_generator import add_order_to_active_route_if_pending
        from notifications.services import send_push_notification
        import logging
        logger = logging.getLogger(__name__)

        data = request.data
        customer_ids = None

        if isinstance(data, list):
            customer_ids = data
        elif isinstance(data, dict):
            customer_ids = data.get("ids") or data.get("customer_ids")

        if not customer_ids or not isinstance(customer_ids, list):
            return Response(
                {
                    "detail": "Expected a list of customer IDs, either as a flat JSON array or wrapped in 'ids' or 'customer_ids'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse and validate UUIDs
        cleaned_ids = []
        for cid in customer_ids:
            try:
                cleaned_ids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                continue

        if not cleaned_ids:
            return Response(
                {"detail": "No valid UUIDs found in the provided list of customer IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customers_qs = Customer.objects.filter(id__in=cleaned_ids, is_new=True)
        if not customers_qs.exists():
            return Response(
                {"detail": "No trial customers found matching the provided IDs."},
                status=status.HTTP_404_NOT_FOUND,
            )

        approved_count = 0
        approved_customers = []

        with transaction.atomic():
            for customer in customers_qs:
                customer.trial_approved = True
                customer.save(update_fields=["trial_approved"])
                approved_count += 1
                approved_customers.append({
                    "id": str(customer.id),
                    "name": customer.name,
                    "phone": customer.phone
                })

                # Automatically assign pending orders to active routes
                try:
                    pending_orders = Order.objects.filter(
                        customer=customer,
                        status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
                    )
                    for order in pending_orders:
                        add_order_to_active_route_if_pending(order)
                except Exception as e:
                    logger.error(f"[Bulk Trial Approval Route Assignment Error] {e}")

                # Send push notification
                try:
                    if customer.user:
                        title = "🎉 Trial Approved!"
                        body = "Congratulations! Your trial has been approved. You'll receive your demo product shortly! 🚚"
                        send_push_notification(
                            user=customer.user,
                            title=title,
                            body=body,
                            notification_type="general"
                        )
                except Exception as e:
                    logger.error(f"[Bulk Trial Approval Notification Error] {e}")

        return Response(
            {
                "message": f"Successfully approved {approved_count} trial customers.",
                "approved_customers": approved_customers
            },
            status=status.HTTP_200_OK
        )



class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [HasGroupPermission]
    required_groups = ["CRM_Managers", "ERP_Admins"]

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated()]
