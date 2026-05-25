import os
import json

path = "documentation/postman_collection.json"
size_bytes = os.path.getsize(path)
size_kb = size_bytes / 1024

print("=== POSTMAN COLLECTION FILE DETAILS ===")
print(f"File Path: {path}")
print(f"File Size: {size_kb:.2f} KB ({size_bytes} bytes)")

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

def count_items(items):
    folders = 0
    requests = 0
    for item in items:
        if "item" in item:
            folders += 1
            sub_folders, sub_requests = count_items(item["item"])
            folders += sub_folders
            requests += sub_requests
        else:
            requests += 1
    return folders, requests

folders, requests = count_items(data.get("item", []))
print(f"Total Folders: {folders}")
print(f"Total Requests: {requests}")
