# This middleware is now superseded by django_tenants.middleware.main.TenantMainMiddleware
# which handles schema switching based on the request domain.

class CityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # request.tenant is already set by TenantMainMiddleware
        return self.get_response(request)
