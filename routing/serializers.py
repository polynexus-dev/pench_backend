import os
import json
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_gis.fields import GeometryField
from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon, LinearRing
from django.contrib.gis.gdal import DataSource
from .models import Route, Driver, TrackingEvent, DailyReconciliation, Zone


def parse_geojson(content):
    """
    Parse a GeoJSON string/dict into a single GEOS Geometry (Polygon or MultiPolygon).
    """
    data = json.loads(content)
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
        if not features:
            raise ValueError("Empty FeatureCollection")
        geom_data = features[0].get("geometry")
    elif data.get("type") == "Feature":
        geom_data = data.get("geometry")
    else:
        geom_data = data

    geom = GEOSGeometry(json.dumps(geom_data))
    if geom.geom_type not in ["Polygon", "MultiPolygon"]:
        raise ValueError(
            f"Geometry must be Polygon or MultiPolygon, got {geom.geom_type}"
        )
    return geom


def parse_kml(content):
    """
    Parse a KML string and extract linear coordinates to build a GEOS Polygon/MultiPolygon.
    """
    root = ET.fromstring(content)
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    coordinates_tags = root.findall(".//coordinates")
    if not coordinates_tags:
        raise ValueError("No <coordinates> elements found in KML file.")

    polygons = []
    for tag in coordinates_tags:
        text = tag.text.strip()
        pts = []
        for coord_str in text.split():
            parts = coord_str.split(",")
            if len(parts) >= 2:
                try:
                    pts.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    continue
        if len(pts) >= 4:
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            try:
                ring = LinearRing(pts)
                polygons.append(Polygon(ring))
            except Exception as e:
                continue

    if not polygons:
        raise ValueError("Could not parse any valid Polygons from KML coordinates.")

    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def parse_zip_shapefile(zip_filepath):
    """
    Extract a zipped shapefile and parse it using GDAL DataSource.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        shp_file = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.lower().endswith(".shp"):
                    shp_file = os.path.join(root, file)
                    break
            if shp_file:
                break

        if not shp_file:
            raise ValueError("No .shp file found in the uploaded zip archive.")

        ds = DataSource(shp_file)
        layer = ds[0]
        geoms = []
        for feature in layer:
            geom = feature.geom.geos
            if geom.geom_type in ["Polygon", "MultiPolygon"]:
                geoms.append(geom)

        if not geoms:
            raise ValueError(
                "No valid Polygon or MultiPolygon geometries found in shapefile."
            )

        if len(geoms) == 1:
            return geoms[0]
        return MultiPolygon(geoms)


def parse_single_shapefile(shp_filepath):
    """
    Parse a single .shp file using GDAL DataSource.
    """
    ds = DataSource(shp_filepath)
    layer = ds[0]
    geoms = []
    for feature in layer:
        geom = feature.geom.geos
        if geom.geom_type in ["Polygon", "MultiPolygon"]:
            geoms.append(geom)

    if not geoms:
        raise ValueError(
            "No valid Polygon or MultiPolygon geometries found in shapefile."
        )

    if len(geoms) == 1:
        return geoms[0]
    return MultiPolygon(geoms)


class ZoneSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(
        source="assigned_driver.get_full_name", read_only=True
    )
    boundary = GeometryField(required=False, allow_null=True)
    boundary_file = serializers.FileField(
        required=False,
        write_only=True,
        help_text="Upload a .geojson, .kml, or zipped shapefile (.zip) to set the zone limits.",
    )

    class Meta:
        model = Zone
        fields = [
            "id",
            "name",
            "description",
            "boundary",
            "boundary_file",
            "assigned_driver",
            "driver_name",
            "is_active",
        ]
        read_only_fields = ["id", "driver_name"]

    def validate(self, data):
        from django.db import connection

        boundary_file = data.pop("boundary_file", None)
        if boundary_file:
            content = boundary_file.read()
            filename = boundary_file.name.lower()

            try:
                if filename.endswith(".kml"):
                    geom = parse_kml(content.decode("utf-8"))
                elif filename.endswith(".json") or filename.endswith(".geojson"):
                    geom = parse_geojson(content.decode("utf-8"))
                elif filename.endswith(".zip") or filename.endswith(".shp"):
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=os.path.splitext(filename)[1]
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    try:
                        if filename.endswith(".zip"):
                            geom = parse_zip_shapefile(tmp_path)
                        else:
                            geom = parse_single_shapefile(tmp_path)
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                else:
                    raise serializers.ValidationError(
                        {
                            "boundary_file": "Unsupported file format. Please upload a .geojson, .kml, or .zip shapefile."
                        }
                    )
                data["boundary"] = geom
            except Exception as e:
                raise serializers.ValidationError(
                    {"boundary_file": f"Failed to parse boundary file: {str(e)}"}
                )

        boundary = data.get("boundary")
        city = connection.tenant

        # Geofencing Validation
        if boundary and city and hasattr(city, "boundary") and city.boundary:
            if not city.boundary.contains(boundary):
                raise serializers.ValidationError(
                    {
                        "boundary": f"This zone boundary is outside the permitted city limits for {city.name}."
                    }
                )

        return data

    def create(self, validated_data):
        validated_data.pop("city", None)
        return super().create(validated_data)


class DriverSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    current_route = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", required=False)

    class Meta:
        model = Driver
        fields = [
            "id",
            "user",
            "full_name",
            "username",
            "phone",
            "vehicle_plate",
            "vehicle_type",
            "max_capacity_kg",
            "is_available",
            "on_trip",
            "zone",
            "current_route",
            "warehouse",
            "warehouse_name",
            "is_active",
        ]

    def get_username(self, obj):
        return obj.user.username if obj and obj.user else ""

    def get_phone(self, obj):
        return obj.user.phone if obj and obj.user else ""

    def update(self, instance, validated_data):
        user = instance.user

        # Extract potential user/rider fields passed in payload
        raw_data = {}
        if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
            raw_data = self.initial_data
        elif hasattr(self, "context") and self.context.get("request"):
            req = self.context["request"]
            if isinstance(req.data, dict):
                raw_data = req.data

        full_name = raw_data.get("full_name")
        username = raw_data.get("username")
        password = raw_data.get("password") or raw_data.get("new_password")
        phone = raw_data.get("phone")
        is_active = raw_data.get("is_active")

        if user:
            user_updated = False
            if full_name and isinstance(full_name, str):
                parts = full_name.strip().split(" ", 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ""
                user_updated = True

            if username and isinstance(username, str) and username.strip() and username.strip() != user.username:
                from accounts.models import User
                new_username = username.strip()
                if not User.objects.filter(username=new_username).exclude(id=user.id).exists():
                    user.username = new_username
                    user_updated = True

            if phone is not None and isinstance(phone, str) and phone.strip() != user.phone:
                user.phone = phone.strip()
                user_updated = True

            if password and isinstance(password, str) and password.strip():
                user.set_password(password.strip())
                user_updated = True

            if is_active is not None:
                user.is_active = bool(is_active)
                user_updated = True

            if user_updated:
                user.save()

                # Sync with Employee profile if exists
                try:
                    from hr.models import Employee
                    employee = Employee.objects.filter(user=user).first()
                    if employee:
                        if full_name:
                            employee.first_name = user.first_name
                            employee.last_name = user.last_name
                        if phone is not None:
                            employee.phone = user.phone
                        employee.is_active = user.is_active
                        employee.save()
                except Exception:
                    pass

        return super().update(instance, validated_data)


    def get_full_name(self, obj):
        try:
            return obj.user.get_full_name() if obj.user else "Unknown User"
        except Exception:
            return "User Profile Error"

    def get_current_route(self, obj):
        # Look for the most recent route that isn't completed or failed
        route = obj.routes.filter(status__in=["pending", "in_progress"]).first()
        return route.id if route else None

    def create(self, validated_data):
        from django.db import connection
        from hr.models import Employee, Department
        from django.utils import timezone

        zone = validated_data.get("zone")
        driver = super().create(validated_data)

        # 1. Sync the tenant_schema back to the User model
        user = driver.user
        if user:
            user.tenant_schema = connection.schema_name
            user.save()

        # 2. Automatically create an Employee record in the HR module
        logistics_dept, _ = Department.objects.get_or_create(
            name="Logistics", defaults={"description": "Fleet and delivery management."}
        )

        # Generate a unique Employee ID for the driver
        import random

        emp_id = f"DRV-{timezone.now().year}-{random.randint(1000, 9999)}"

        Employee.objects.get_or_create(
            user=user,
            defaults={
                "department": logistics_dept,
                "job_title": "Delivery Driver",
                "employee_id": emp_id,
                "date_joined": timezone.now().date(),
                "is_active": True,
            },
        )

        # 3. If a zone was provided, set this driver as the primary driver for that zone
        if zone:
            zone.assigned_driver = user
            zone.save()

        return driver


class TrackingEventSerializer(serializers.ModelSerializer):
    collection_method_display = serializers.CharField(
        source="get_collection_method_display", read_only=True
    )

    class Meta:
        model = TrackingEvent
        fields = [
            "id",
            "route",
            "order",
            "status",
            "location",
            "notes",
            "timestamp",
            "photo_proof",
            "collection_amount",
            "collection_method",
            "collection_method_display",
            "customer_signature",
        ]
        read_only_fields = ["id", "timestamp"]


class RouteSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(
        source="driver.user.get_full_name", read_only=True
    )
    order_ids = serializers.PrimaryKeyRelatedField(
        source="orders", many=True, read_only=True
    )
    status = serializers.SerializerMethodField()
    dispatch_bottles_1L = serializers.SerializerMethodField()
    dispatch_bottles_500ml = serializers.SerializerMethodField()

    additional_drivers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Driver.objects.all(), required=False
    )
    additional_driver_names = serializers.SerializerMethodField()
    is_secured = serializers.SerializerMethodField()

    def get_status(self, obj):
        if obj.status == "in_progress":
            return "in_transit"
        return obj.status

    def get_additional_driver_names(self, obj):
        return [
            drv.user.get_full_name() for drv in obj.additional_drivers.all() if drv.user
        ]

    def get_is_secured(self, obj):
        if getattr(obj, "is_secured", False):
            return True
        from administration.models import AdminConfiguration
        try:
            return AdminConfiguration.get_solo().is_secured
        except Exception:
            return False

    class Meta:
        model = Route
        fields = [
            "id",
            "driver",
            "driver_name",
            "order_ids",
            "status",
            "is_secured",
            "geometry",
            "waypoints",
            "estimated_duration_minutes",
            "estimated_distance_km",
            "optimization_error",
            "created_at",
            "updated_at",
            "dispatch_bottles_1L",
            "dispatch_bottles_500ml",
            "additional_drivers",
            "additional_driver_names",
        ]
        read_only_fields = [
            "id",
            "status",
            "geometry",
            "waypoints",
            "estimated_duration_minutes",
            "estimated_distance_km",
            "optimization_error",
            "created_at",
            "updated_at",
        ]

    def get_dispatch_bottles_1L(self, obj):
        total = 0
        try:
            for order in obj.orders.all():
                for item in order.items.all():
                    product = item.product
                    if product.bottle_type and product.bottle_type.volume_ml == 1000:
                        total += item.quantity
        except Exception:
            pass
        return total

    def get_dispatch_bottles_500ml(self, obj):
        total = 0
        try:
            for order in obj.orders.all():
                for item in order.items.all():
                    product = item.product
                    if product.bottle_type and product.bottle_type.volume_ml == 500:
                        total += item.quantity
        except Exception:
            pass
        return total


class RouteGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Route
        geo_field = "geometry"
        fields = ["id", "driver", "status", "estimated_duration_minutes", "waypoints"]


class DailyReconciliationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(
        source="driver.user.get_full_name", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reconciled_by_name = serializers.CharField(
        source="reconciled_by.get_full_name", read_only=True
    )

    class Meta:
        model = DailyReconciliation
        fields = [
            "id",
            "driver",
            "driver_name",
            "route",
            "date",
            "total_cash_collected",
            "total_upi_collected",
            "total_wallet_deducted",
            "expected_total",
            "actual_total",
            "discrepancy",
            "status",
            "status_display",
            "reconciled_by",
            "reconciled_by_name",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ReconcileActionSerializer(serializers.Serializer):
    actual_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
