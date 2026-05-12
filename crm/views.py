from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.permissions import HasGroupPermission
from .models import Customer, Lead
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

    @action(detail=True, methods=['get'], url_path='download-qr')
    def download_qr(self, request, pk=None):
        """
        Generates and returns a Balanced, High-Impact Branded QR Label.
        """
        customer = self.get_object()
        import qrcode
        import os
        from io import BytesIO
        from django.http import HttpResponse
        from django.conf import settings
        from PIL import Image, ImageDraw, ImageFont

        # --- COLORS & CONFIG ---
        # --- COLORS & CONFIG ---
        pench_green = (0, 150, 70) 
        deep_forest = (0, 80, 40)   # Premium dark green for QR pixels
        dark_bg = (15, 25, 35)      # Navy/Black for header
        text_color = (255, 255, 255)
        
        # 1. Generate QR Code
        from django.urls import reverse
        resolve_url = reverse('customer-qr-resolve', kwargs={'qr_id': str(customer.qr_code_id)})
        full_url = request.build_absolute_uri(resolve_url)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12, # Slightly larger pixels
            border=2,
        )
        qr.add_data(full_url)
        qr.make(fit=True)
        
        # Use Deep Forest Green for pixels, White background
        qr_img = qr.make_image(fill_color=deep_forest, back_color="white").convert('RGB')
        qr_w, qr_h = qr_img.size
        
        # 2. Canvas Setup (Branded Background)
        canvas_width = 800
        canvas_height = 1200
        canvas = Image.new('RGB', (canvas_width, canvas_height), pench_green)
        draw = ImageDraw.Draw(canvas)
        
        # 3. Draw Premium Header (Dark)
        header_h = 250
        draw.rectangle([(0, 0), (canvas_width, header_h)], fill=dark_bg)
        
        # 4. Draw "White Card" for QR (Provides contrast on green BG)
        card_margin = 60
        card_x1 = card_margin
        card_y1 = header_h - 40 # Overlaps header slightly for modern look
        card_x2 = canvas_width - card_margin
        card_y2 = card_y1 + qr_h + 120
        
        # Rounded rectangle for the card
        draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=40, fill="white")
        
        # 5. Embed Large Logo (22%)
        logo_path = os.path.join(settings.BASE_DIR, 'Untitled design-8 (2).png')
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo_size = int(qr_w * 0.22) # Quite large
            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            logo_pos = ((qr_w - logo.size[0]) // 2, (qr_h - logo.size[1]) // 2)
            # Clear a slightly larger area for the logo to ensure no pixel bleed
            logo_bg = Image.new('RGBA', (logo.size[0] + 15, logo.size[1] + 15), (255, 255, 255, 255))
            qr_img.paste(logo_bg, (logo_pos[0]-7, logo_pos[1]-7), logo_bg)
            qr_img.paste(logo, logo_pos, logo)

        # 6. Paste QR onto Card
        qr_x = (canvas_width - qr_w) // 2
        qr_y = card_y1 + 40
        canvas.paste(qr_img, (qr_x, qr_y))
        
        # 7. Load Premium Fonts
        try:
            f_title = ImageFont.truetype("arialbd.ttf", 70)
            f_subtitle = ImageFont.truetype("arial.ttf", 30)
            f_bold = ImageFont.truetype("arialbd.ttf", 80)
            f_footer = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            f_title = f_bold = f_subtitle = f_footer = ImageFont.load_default()

        # 8. Add Text
        # Main Title
        draw.text((canvas_width/2, 100), "PENCH FOODS", fill=text_color, anchor="mm", font=f_title)
        draw.text((canvas_width/2, 160), "Pure. Fresh. Delivered.", fill=(200, 200, 200), anchor="mm", font=f_subtitle)
        
        # "SCAN HERE" in big white text on green background
        scan_y = card_y2 + 100
        draw.text((canvas_width/2, scan_y), "SCAN HERE", fill="white", anchor="mm", font=f_bold)
        
        # Bottom Branding
        footer_y = canvas_height - 60
        draw.text((canvas_width/2, footer_y), "Powered by Polynexus Technologies", fill=(220, 220, 220), anchor="mm", font=f_footer)
        
        # Save to buffer
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        buffer.seek(0)

        return HttpResponse(buffer, content_type="image/png")

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
            return HttpResponseRedirect(f"pench-driver://customer/{qr_id}")

        # Scenario 2: The Customer themselves
        if not user.is_anonymous and user == customer.user:
            # Redirect to the customer app deep link
            return HttpResponseRedirect(f"pench-customer://customer/{qr_id}")

        # Scenario 3: Guest / Stranger
        # Redirect guests directly to the website for marketing
        return HttpResponseRedirect("https://penchfoods.com")


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [HasGroupPermission]
    required_groups = ['CRM_Managers', 'ERP_Admins']
    
    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]
