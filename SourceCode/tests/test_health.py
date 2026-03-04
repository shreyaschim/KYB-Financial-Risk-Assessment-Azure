import requests

def test_health(base_url):
    r = requests.get(f"{base_url}/health", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"