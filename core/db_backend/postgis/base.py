from django.contrib.gis.db.backends.postgis.base import DatabaseWrapper as PostGISDatabaseWrapper
from django_tenants.postgresql_backend.base import _check_schema_name

class DatabaseWrapper(PostGISDatabaseWrapper):
    """
    Custom database backend that combines django-tenants with PostGIS.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = None
        self.schema_name = 'public'
        self.include_public = True
        self.search_path_set = False
        self._setting_search_path = False

    def set_tenant(self, tenant, include_public=True, *args, **kwargs):
        """
        Standard django-tenants method to set the active tenant.
        """
        self.tenant = tenant
        self.schema_name = tenant.schema_name
        self.include_public = include_public
        self.set_settings_schema(self.schema_name)
        self.search_path_set = False

    def set_schema(self, schema_name, include_public=True, *args, **kwargs):
        """
        Internal method to switch schema directly.
        """
        self.tenant = None
        self.schema_name = schema_name
        self.include_public = include_public
        self.set_settings_schema(schema_name)
        self.search_path_set = False

    def set_schema_to_public(self):
        self.set_schema('public')

    def set_settings_schema(self, schema_name):
        self.settings_dict['SCHEMA'] = schema_name

    def _cursor(self, name=None):
        cursor = super()._cursor(name=name)
        
        # Prevent recursion loop
        if not self.search_path_set and not self._setting_search_path:
            self._setting_search_path = True
            try:
                _check_schema_name(self.schema_name)
                if self.schema_name == 'public':
                    search_path = 'public'
                elif self.include_public:
                    search_path = f'"{self.schema_name}", public'
                else:
                    search_path = f'"{self.schema_name}"'
                
                with self.connection.cursor() as base_cursor:
                    base_cursor.execute(f"SET search_path TO {search_path}")
                
                self.search_path_set = True
            finally:
                self._setting_search_path = False
                
        return cursor
