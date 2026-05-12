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
        pench_green = (0, 150, 70) 
        dark_bg = (20, 30, 40)     
        text_color = (255, 255, 255)
        qr_pixel_color = (0, 0, 0) # Black is safest for scanners
        
        # 1. Generate QR Code
        from django.urls import reverse
        resolve_url = reverse('customer-qr-resolve', kwargs={'qr_id': str(customer.qr_code_id)})
        full_url = request.build_absolute_uri(resolve_url)

        qr = qrcode.QRCode(
            version=None, # Auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4, # More border for better separation
        )
        qr.add_data(full_url)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color=qr_pixel_color, back_color="white").convert('RGB')
        qr_w, qr_h = qr_img.size
        
        # 2. Canvas Setup (Ensure it fits the QR)
        canvas_width = max(600, qr_w + 100)
        canvas_height = qr_h + 400 # Space for header and footer
        
        canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        # 3. Draw Branded Header
        header_height = 200
        draw.rectangle([(0, 0), (canvas_width, header_height)], fill=dark_bg)
        
        # 4. Embed Logo in QR (Reduced size to 18%)
        logo_path = os.path.join(settings.BASE_DIR, 'Untitled design-8 (2).png')
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo_max_size = int(qr_w * 0.18) # 18% is safer than 25%
            logo.thumbnail((logo_max_size, logo_max_size), Image.Resampling.LANCZOS)
            
            logo_pos = ((qr_w - logo.size[0]) // 2, (qr_h - logo.size[1]) // 2)
            
            # White background for logo to clear QR pixels
            logo_bg = Image.new('RGBA', (logo.size[0] + 10, logo.size[1] + 10), (255, 255, 255, 255))
            qr_img.paste(logo_bg, (logo_pos[0]-5, logo_pos[1]-5), logo_bg)
            qr_img.paste(logo, logo_pos, logo)

        # 5. Paste QR onto Canvas (Centered below header)
        qr_x = (canvas_width - qr_w) // 2
        qr_y = header_height + 50
        canvas.paste(qr_img, (qr_x, qr_y))
        
        # 6. Load Fonts
        try:
            # Try to use Arial, fallback to default
            font_bold = ImageFont.truetype("arialbd.ttf", 60)
            font_small = ImageFont.truetype("arial.ttf", 20)
            font_title = ImageFont.truetype("arialbd.ttf", 45)
        except Exception:
            font_bold = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_title = ImageFont.load_default()

        # 7. Add Text
        # Title in Header
        draw.text((canvas_width/2, header_height/2), "PENCH FOODS", fill=text_color, anchor="mm", font=font_title)
        
        # SCAN HERE below QR
        text_y = qr_y + qr_h + 40
        draw.text((canvas_width/2, text_y), "SCAN HERE", fill=pench_green, anchor="mm", font=font_bold)
        
        # Footer
        footer_y = canvas_height - 40
        footer_text = "Powered by Polynexus Technologies"
        draw.text((canvas_width/2, footer_y), footer_text, fill=(100, 100, 100), anchor="mm", font=font_small)
        
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
