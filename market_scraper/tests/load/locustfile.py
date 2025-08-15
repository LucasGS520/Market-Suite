from locust import HttpUser, task, between
import os
import uuid


class WebsiteUser(HttpUser):
    """ Usuário que realiza requisições de teste ao serviço de scraping """
    wait_time = between(1, 3)
    host = os.getenv("LOCUST_HOST", "http://localhost:8000")

    def on_start(self):
        """ Efetua o login para obter o token de autenticação """
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
        """ Retorna cabeçalhos com o token JWT quando disponível """
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(2)
    def scrape_monitored(self):
        """ Simula o scraping de um produto monitorado """
        payload = {
            "url": "https://example.com/product",
            "product_type": "monitored",
            "user_id": str(uuid.uuid4()),
        }
        self.client.post("/scrape/parse", json=payload, headers=self._headers())

    @task(1)
    def scrape_competitor(self):
        """ Simula o scraping de um produto concorrente """
        payload = {
            "url": "https://example.com/competitor",
            "product_type": "competitor",
            "user_id": str(uuid.uuid4()),
        }
        self.client.post("/scrape/parse", json=payload, headers=self._headers())
