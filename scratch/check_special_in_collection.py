import json

def verify():
    with open("documentation/postman_collection.json", "r") as f:
        collection = json.load(f)
    
    # Traverse collection to find "GET Special Orders"
    found = False
    def search_items(items):
        nonlocal found
        for item in items:
            if item.get("name") == "GET Special Orders":
                found = True
                print("SUCCESS: Found 'GET Special Orders' request!")
                print("URL:", item["request"]["url"]["raw"])
            if "item" in item:
                search_items(item["item"])
                
    search_items(collection["item"])
    if not found:
        print("ERROR: Did not find 'GET Special Orders' request in collection!")

if __name__ == "__main__":
    verify()
