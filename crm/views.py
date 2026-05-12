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
        
        # 1. Generate QR Code
        from django.urls import reverse
        resolve_url = reverse('customer-qr-resolve', kwargs={'qr_id': str(customer.qr_code_id)})
        full_url = request.build_absolute_uri(resolve_url)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=9, # Reduced from 12 to prevent overlap with your "SCAN HERE" text
            border=2,
        )
        qr.add_data(full_url)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color=pench_green, back_color="white").convert('RGB')
        
        # 2. Canvas Setup (Increased Height for Spacing)
        width, height = qr_img.size
        canvas_width = 600
        canvas_height = 900
        
        canvas = Image.new('RGB', (canvas_width, canvas_height), pench_green)
        draw = ImageDraw.Draw(canvas)
        
        # 3. Draw Stylized Background
        draw.polygon([(0, 0), (canvas_width, 0), (canvas_width, 350), (0, 500)], fill=dark_bg)
        
        # 4. Embed Logo in QR
        logo_path = os.path.join(settings.BASE_DIR, 'Untitled design-8 (2).png')
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo_max_size = int(width * 0.25)
            logo.thumbnail((logo_max_size, logo_max_size), Image.Resampling.LANCZOS)
            
            qr_w, qr_h = qr_img.size
            logo_pos = ((qr_w - logo.size[0]) // 2, (qr_h - logo.size[1]) // 2)
            
            logo_bg = Image.new('RGBA', (logo.size[0] + 12, logo.size[1] + 12), (255, 255, 255, 255))
            qr_img.paste(logo_bg, (logo_pos[0]-6, logo_pos[1]-6), logo_bg)
            qr_img.paste(logo, logo_pos, logo)

        # 5. Paste QR onto Canvas (Higher Position)
        qr_x = (canvas_width - width) // 2
        qr_y = 180
        canvas.paste(qr_img, (qr_x, qr_y))
        
        # 6. Load Professional Font
        try:
            font_bold = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 60)
            font_small = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 18) # Smaller Footer
            font_title = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 45)
        except Exception:
            font_bold = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_title = ImageFont.load_default()

        # 7. Add Text with Impact
        # Title
        draw.text((canvas_width/2, 100), "PENCH FOODS", fill=text_color, anchor="mm", font=font_title)
        
        # Big Bold "SCAN HERE" (Moved Down)
        draw.text((canvas_width/2, 730), "SCAN HERE", fill=dark_bg, anchor="mm", font=font_bold)
        
        # Small Footer
        footer_text = "Powered by Polynexus Technologies"
        draw.text((canvas_width/2, 850), footer_text, fill=(255, 255, 255, 200), anchor="mm", font=font_small)
        
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
