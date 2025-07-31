from locust import HttpUser, task, between
import os
import random
import uuid

class WebsiteUser(HttpUser):
    wait_time = between(1, 3)
    host = os.getenv("LOCUST_HOST", "http://localhost:8000")

    def on_start(self):
        self.token = None
        email = os.getenv("LOCUST_LOGIN_EMAIL")
        password = os.getenv("LOCUST_LOGIN_PASSWORD")
        if email and password:
            with self.client.post("/auth", data={"username": email, "password": password}, catch_response=True) as resp:
                if resp.status_code == 200:
                    self.token = resp.json().get("access_token")
                else:
                    resp.failure(f"Failed login: {resp.status_code}")

    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(2)
    def scrape_monitored(self):
        payload = {
            "product_url": "https://example.com/product",
            "name_identification": f"load-{random.randint(1,10000)}",
            "target_price": 100.0
        }
        self.client.post("/monitored/scrape", json=payload, headers=self._headers())

    @task(1)
    def scrape_competitor(self):
        payload = {
            "monitored_product_id": str(uuid.uuid4()),
            "product_url": "https://example.com/competitor"
        }
        self.client.post("/competitors/scrape", json=payload, headers=self._headers())