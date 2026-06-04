import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def find_request(items, target_name):
    for item in items:
        name = item.get("name")
        if "item" in item:
            res = find_request(item["item"], target_name)
            if res:
                return res
        elif name == target_name:
            return item
    return None

order_request = find_request(data.get("item", []), "POST Create Order")
if order_request:
    print(f"Request Name: {order_request['name']}")
    print(f"Method: {order_request['request']['method']}")
    print(f"URL: {order_request['request']['url']['raw']}")
    body = order_request['request'].get('body', {})
    print("Body Mode:", body.get('mode'))
    print("Body Raw:")
    print(body.get('raw', 'No body found'))
else:
    print("POST Create Order request not found in collection.")
