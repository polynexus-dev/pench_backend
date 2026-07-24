import openpyxl

# Maps normalized field name -> accepted header aliases (case-insensitive, whitespace-stripped)
HEADER_ALIASES = {
    "name": ["name", "customer name", "customer"],
    "phone": ["phone", "phone number", "mobile", "contact"],
    "email": ["email", "email address"],
    "address": ["address", "delivery address"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "lng", "long", "longitude"],
    "driver_name": ["driver", "driver name", "rider", "rider name", "assigned driver", "assigned rider"],
    "driver_phone": ["driver phone", "rider phone", "driver contact"],
}


def _normalize_header(value):
    return str(value).strip().lower() if value is not None else ""


def _build_header_map(header_row):
    """
    Maps normalized field name -> column index, based on HEADER_ALIASES.
    """
    alias_to_field = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            alias_to_field[alias] = field

    header_map = {}
    for idx, cell_value in enumerate(header_row):
        header = _normalize_header(cell_value)
        field = alias_to_field.get(header)
        if field and field not in header_map:
            header_map[field] = idx
    return header_map


def parse_customer_excel(file):
    """
    Parses an uploaded Excel file of customers + their assigned driver/rider.

    Returns a dict:
        {
            "rows": [ { name, phone, email, address, lat, lon, driver_name, driver_phone, row_num }, ... ],
            "skipped": [ { row_num, reason }, ... ],
        }
    """
    workbook = openpyxl.load_workbook(file, data_only=True, read_only=True)
    sheet = workbook.active

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return {"rows": [], "skipped": [{"row_num": 1, "reason": "Sheet is empty."}]}

    header_map = _build_header_map(header_row)

    missing_required = [f for f in ("lat", "lon") if f not in header_map]
    if missing_required:
        raise ValueError(
            f"Could not find required column(s) in the sheet: {', '.join(missing_required)}. "
            f"Expected a latitude and longitude column (e.g. 'lat'/'latitude', 'lon'/'longitude')."
        )
    if "driver_name" not in header_map and "driver_phone" not in header_map:
        raise ValueError(
            "Could not find a driver/rider column in the sheet (e.g. 'Driver' or 'Driver Phone')."
        )

    def get(row, field):
        idx = header_map.get(field)
        if idx is None or idx >= len(row):
            return None
        value = row[idx]
        if isinstance(value, str):
            value = value.strip()
        return value or None

    rows = []
    skipped = []
    for row_num, row in enumerate(rows_iter, start=2):
        if row is None or all(v is None for v in row):
            continue

        lat_raw, lon_raw = get(row, "lat"), get(row, "lon")
        driver_name, driver_phone = get(row, "driver_name"), get(row, "driver_phone")

        if lat_raw is None or lon_raw is None:
            skipped.append({"row_num": row_num, "reason": "Missing latitude/longitude."})
            continue
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except (TypeError, ValueError):
            skipped.append({"row_num": row_num, "reason": "Latitude/longitude is not numeric."})
            continue

        if not driver_name and not driver_phone:
            skipped.append({"row_num": row_num, "reason": "Missing assigned driver/rider."})
            continue

        rows.append(
            {
                "row_num": row_num,
                "name": get(row, "name") or f"Customer (row {row_num})",
                "phone": get(row, "phone"),
                "email": get(row, "email"),
                "address": get(row, "address") or "",
                "lat": lat,
                "lon": lon,
                "driver_name": driver_name,
                "driver_phone": driver_phone,
            }
        )

    return {"rows": rows, "skipped": skipped}
