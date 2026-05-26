import os
import json
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon, LinearRing
from django.contrib.gis.gdal import DataSource
from .models import Company, City, HolidayCalendar


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
                # Silently ignore invalid rings
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


class CitySerializer(serializers.ModelSerializer):
    schema_name = serializers.CharField(required=False)
    boundary = GeometryField(required=False, allow_null=True)
    boundary_file = serializers.FileField(
        required=False,
        write_only=True,
        help_text="Upload a .geojson, .kml, or zipped shapefile (.zip) to set the city geofencing limits.",
    )
    company_name = serializers.CharField(source="company.name", read_only=True)
    company_code = serializers.CharField(source="company.code", read_only=True)

    class Meta:
        model = City
        fields = [
            "id",
            "company",
            "company_name",
            "company_code",
            "schema_name",
            "name",
            "state",
            "code",
            "boundary",
            "boundary_file",
            "is_active",
            "timezone",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
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
        return data

    def create(self, validated_data):
        import re

        def clean_name(val):
            if not val:
                return ""
            val = val.lower()
            val = re.sub(r"[^a-z0-9_]", "_", val)
            val = re.sub(r"_+", "_", val)
            return val.strip("_")

        company = validated_data.get("company")
        schema_name = validated_data.get("schema_name", "")

        if company:
            clean_company = clean_name(company.code)
            clean_schema = clean_name(schema_name)
            if not clean_schema:
                clean_schema = clean_name(validated_data.get("name", ""))

            prefix = f"{clean_company}_"
            if not clean_schema.startswith(prefix):
                schema_name = f"{prefix}{clean_schema}"
            else:
                schema_name = clean_schema
        else:
            if not schema_name:
                schema_name = clean_name(validated_data.get("name", ""))
            else:
                schema_name = clean_name(schema_name)

        validated_data["schema_name"] = schema_name[:63]
        return super().create(validated_data)


class HolidayCalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HolidayCalendar
        fields = ["id", "city", "name", "date", "is_recurring", "description"]


class CompanySerializer(serializers.ModelSerializer):
    cities = CitySerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "code", "is_active", "cities"]
