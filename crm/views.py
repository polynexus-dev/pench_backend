from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.permissions import HasGroupPermission
from .models import Customer, Lead, HAS_GIS, _parse_coordinates, _point_in_polygon
from .serializers import CustomerSerializer, LeadSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().filter(is_active=True)
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasGroupPermission]
    required_groups = ['CRM_Managers', 'ERP_Admins']
    search_fields = ['name', 'company', 'email', 'phone']
    ordering_fields = ['name', 'created_at']

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple customers in a single POST request.
        Just send a JSON list instead of a single object.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates multiple customers at once. 
        Each object in the list MUST have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list of objects."}, status=status.HTTP_400_BAD_REQUEST)

        updated_customers = []
        for item in data:
            customer_id = item.get('id')
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
        resolve_url = reverse('customer-qr-resolve', kwargs={'qr_id': str(customer.qr_code_id)})
        full_url = request.build_absolute_uri(resolve_url)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=7, # Shrunk to ensure it never overlaps text
            border=2,
        )
        qr.add_data(full_url)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color=pench_green, back_color="white").convert('RGB')
        
        # 2. Canvas Setup (Optimized for A4 aspect ratio to minimize margins)
        width, height = qr_img.size
        canvas_width = 600
        canvas_height = 850
        
        canvas = Image.new('RGB', (canvas_width, canvas_height), pench_green)
        draw = ImageDraw.Draw(canvas)
        
        # 3. Draw Stylized Background
        draw.polygon([(0, 0), (canvas_width, 0), (canvas_width, 420), (0, 590)], fill=dark_bg)
        
        # 3.5. Draw Inclined Watermark
        logo_path = os.path.join(settings.BASE_DIR, 'Untitled design-8 (2).png')
        wm_layer = Image.new('RGBA', (canvas_width * 2, canvas_height * 2), (0,0,0,0))
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
            
        wm_text_color = (255, 255, 255, 30) # Low opacity white text
        
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
                        wm_draw.text((offset_x, y), "PENCH", fill=wm_text_color, font=wm_font)
                else:
                    wm_draw.text((offset_x, y), "PENCH FOODS", fill=wm_text_color, font=wm_font)
                    
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
            
            logo_bg = Image.new('RGBA', (logo.size[0] + 12, logo.size[1] + 12), (255, 255, 255, 255))
            qr_img.paste(logo_bg, (logo_pos[0]-6, logo_pos[1]-6), logo_bg)
            qr_img.paste(logo, logo_pos, logo)

        # 5. Paste QR onto Canvas (Centered vertically)
        qr_x = (canvas_width - width) // 2
        qr_y = 190
        canvas.paste(qr_img, (qr_x, qr_y))
        
        # 6. Load Professional Font
        try:
            # Using Segoe UI for a more modern, premium look instead of basic Arial
            font_bold = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 60)
            font_small = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 18) # Smaller Footer
            font_title = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 45)
            font_scan = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 35) # Smaller SCAN HERE
            font_customer = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 28) # Customer Name
        except Exception:
            font_bold = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_title = ImageFont.load_default()
            font_scan = ImageFont.load_default()
            font_customer = ImageFont.load_default()

        # 7. Add Text with Impact
        # Title
        draw.text((canvas_width/2, 80), "PENCH FOODS", fill=text_color, anchor="mm", font=font_title)
        
        # Privacy-Safe Identifier (NO NAME, NO ADDRESS)
        # We generate a readable 6-digit ID like "PENCH-482917" from the QR UUID.
        # This will be printed on the sticker AND can be exported to Excel later.
        unique_num = str(customer.qr_code_id.int)[:6]
        display_text = f"ID: PENCH-{unique_num}"
            
        # Draw the ID right beneath the QR code (tight gap)
        draw.text((canvas_width/2, 650), display_text, fill=dark_bg, anchor="mm", font=font_customer)
        
        # Smaller "SCAN HERE" close to the ID
        draw.text((canvas_width/2, 715), "SCAN HERE", fill=dark_bg, anchor="mm", font=font_scan)
        
        # Small Footer sitting neatly at the bottom edge
        footer_text = "Powered by Polynexus Technologies"
        draw.text((canvas_width/2, 810), footer_text, fill=(255, 255, 255, 200), anchor="mm", font=font_small)
        
        return canvas

    @action(detail=True, methods=['get'], url_path='download-qr')
    def download_qr(self, request, pk=None):
        """
        Generates and returns a single Balanced, High-Impact Branded QR Label.
        """
        customer = self.get_object()
        from io import BytesIO
        from django.http import HttpResponse
        
        canvas = self._generate_qr_label_image(request, customer)
        
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        buffer.seek(0)
        return HttpResponse(buffer, content_type="image/png")

    @action(detail=False, methods=['get', 'post'], url_path='bulk-download-qr')
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
        if request.method == 'POST':
            customer_ids = request.data.get('ids') or request.data.get('customer_ids')
        else:
            customer_ids = request.query_params.get('ids') or request.query_params.get('customer_ids')
            
        if customer_ids is not None:
            import uuid
            parsed_ids = []
            if isinstance(customer_ids, str):
                try:
                    parsed_ids = [uuid.UUID(x.strip()) for x in customer_ids.split(',') if x.strip()]
                except ValueError:
                    return Response({"detail": "Invalid format for ids. Expected a comma-separated list of UUIDs."}, status=status.HTTP_400_BAD_REQUEST)
            elif isinstance(customer_ids, list):
                try:
                    parsed_ids = [uuid.UUID(str(x)) for x in customer_ids]
                except (ValueError, TypeError):
                    return Response({"detail": "Invalid format for ids. Expected a list of UUIDs."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"detail": "Invalid format for ids. Expected a list or a comma-separated string."}, status=status.HTTP_400_BAD_REQUEST)
            
            customers = customers.filter(id__in=parsed_ids)
            if not customers.exists():
                return Response({"detail": "No active customers found for the specified IDs."}, status=status.HTTP_404_NOT_FOUND)
        else:
            if not customers.exists():
                return Response({"detail": "No active customers found."}, status=status.HTTP_404_NOT_FOUND)
            
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
        
        def draw_dashed_line(draw, pt1, pt2, fill, width=1, dash_length=20, gap_length=15):
            x1, y1 = pt1
            x2, y2 = pt2
            dx = x2 - x1
            dy = y2 - y1
            distance = (dx**2 + dy**2)**0.5
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
                    ly = margin_y + r * sticker_height + (r - 1) * card_gap + card_gap // 2
                    
                draw_dashed_line(
                    draw_lines,
                    (margin_x - 60, ly),
                    (margin_x + total_width + 60, ly),
                    fill=line_color,
                    width=line_width
                )
                
            # Vertical lines - drawn in the middle of gutters + outer borders
            for c in range(cols + 1):
                if c == 0:
                    lx = margin_x
                elif c == cols:
                    lx = margin_x + cols * sticker_width + (cols - 1) * card_gap
                else:
                    lx = margin_x + c * sticker_width + (c - 1) * card_gap + card_gap // 2
                    
                draw_dashed_line(
                    draw_lines,
                    (lx, margin_y - 60),
                    (lx, margin_y + total_height + 60),
                    fill=line_color,
                    width=line_width
                )
        
        pdf_pages = []
        current_page = Image.new('RGB', (page_width, page_height), 'white')
        current_count = 0
        
        for customer in customers:
            sticker = self._generate_qr_label_image(request, customer)
            # Resize the 600x850 sticker to larger 750x1060 to fit 3x3 layout
            sticker_resized = sticker.resize((sticker_width, sticker_height), Image.Resampling.LANCZOS)
            
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
                current_page = Image.new('RGB', (page_width, page_height), 'white')
                
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
                append_images=pdf_pages[1:]
            )
            pdf_data = pdf_buffer.getvalue()
            
        # --- 2. GENERATE EXCEL (CSV) MAPPING ---
        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['QR Sticker ID', 'Customer Name', 'Phone', 'Address'])
        
        for customer in customers:
            unique_num = str(customer.qr_code_id.int)[:6]
            sticker_id = f"PENCH-{unique_num}"
            
            name = customer.name
            if not name and customer.user:
                name = customer.user.get_full_name() or customer.user.username
            
            phone = customer.phone or ""
            address = customer.address or ""
            
            writer.writerow([sticker_id, name, phone, address])
            
        csv_data = csv_buffer.getvalue().encode('utf-8')
        
        # --- 3. PACKAGE BOTH INTO A ZIP FILE ---
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('qr_stickers.pdf', pdf_data)
            zip_file.writestr('qr_mapping.csv', csv_data)
            
        zip_buffer.seek(0)
        
        response = HttpResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="bulk_qr_pack.zip"'
        return response

    @action(detail=False, methods=['get'], url_path='qr-resolve/(?P<qr_id>[^/.]+)', permission_classes=[AllowAny])
    def qr_resolve(self, request, qr_id=None):
        """
        Resolves a Smart QR scan based on user role.
        """
        customer = Customer.objects.filter(qr_code_id=qr_id).first()
        if not customer:
            return Response({'detail': 'Invalid QR Code.'}, status=404)

        user = request.user
        from django.http import HttpResponseRedirect
        
        # Scenario 1: Delivery Person (Driver)
        if not user.is_anonymous and getattr(user, 'is_driver', False):
            # Redirect to the driver app deep link
            return HttpResponseRedirect(f"pench-foods://delivery/qr/{qr_id}")

        # Scenario 2: The Customer themselves
        if not user.is_anonymous and user == customer.user:
            # Redirect to the customer app deep link
            return HttpResponseRedirect(f"pench-foods://profile/qr/{qr_id}")

        # Scenario 3: Guest / Stranger
        # Redirect guests directly to the website for marketing
        return HttpResponseRedirect("https://penchfoods.com")

    @action(detail=False, methods=['post'], url_path='auto-assign-zones')
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
                assigned_zone = Zone.objects.filter(boundary__contains=loc, is_active=True).first()
            else:
                coords = _parse_coordinates(loc)
                if coords:
                    lng, lat = coords
                    for zone in zones_list:
                        if zone.boundary:
                            poly_coords = None
                            if isinstance(zone.boundary, dict):
                                geom_type = zone.boundary.get('type')
                                if geom_type == 'Polygon':
                                    poly_coords = zone.boundary.get('coordinates')
                                elif geom_type == 'MultiPolygon':
                                    poly_coords_list = zone.boundary.get('coordinates', [])
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
                customer.save(update_fields=['zone'])
                updated += 1
                assignments.append({
                    "customer_id": str(customer.id),
                    "customer_name": customer.name,
                    "zone_id": str(assigned_zone.id),
                    "zone_name": assigned_zone.name
                })
                
        return Response({
            "message": "Auto-assignment completed successfully.",
            "scanned": scanned,
            "updated": updated,
            "assignments": assignments
        }, status=status.HTTP_200_OK)


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [HasGroupPermission]
    required_groups = ['CRM_Managers', 'ERP_Admins']
    
    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]
