import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Find 00. SPECIAL: Driver Mobile App folder
driver_folder = None
for folder in data.get("item", []):
    if folder.get("name") == "00. SPECIAL: Driver Mobile App":
        driver_folder = folder
        break

if driver_folder:
    # Print the first request in it as formatted JSON
    print(json.dumps(driver_folder["item"][0], indent=2))
else:
    print("Driver folder not found!")
