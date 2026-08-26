import requests

BASE_URL = "http://localhost:8000"

def test_login(username, password):
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": username, "password": password})
    if res.status_code == 200:
        return res.json()["access_token"]
    print(f"Failed to login as {username}: {res.json()}")
    return None

def test_inventory(token):
    res = requests.get(f"{BASE_URL}/api/inventory/items", headers={"Authorization": f"Bearer {token}"})
    return res.json()

if __name__ == "__main__":
    print("Testing User A...")
    token_a = test_login("usera", "user123")
    if token_a:
        items_a = test_inventory(token_a)
        print(f"User A sees {len(items_a)} items: {[i['name'] for i in items_a]}")
        
    print("\nTesting User B...")
    token_b = test_login("userb", "user123")
    if token_b:
        items_b = test_inventory(token_b)
        print(f"User B sees {len(items_b)} items: {[i['name'] for i in items_b]}")
        
    print("\nTesting Admin...")
    token_admin = test_login("admin", "admin123")
    if token_admin:
        items_admin = test_inventory(token_admin)
        print(f"Admin sees {len(items_admin)} items (should be all).")
