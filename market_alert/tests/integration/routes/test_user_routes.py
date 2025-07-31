from app.models.models_users import User

def test_create_user(client, db_session, prepare_test_database):
    payload = {
        "name": "Novo Usuario",
        "email": "novo@example.com",
        "phone_number": "11987654321",
        "password": "senha123",
        "notifications_enabled": True
    }
    resp = client.post("/users/", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == payload["email"]
    created = db_session.query(User).filter_by(email=payload["email"]).first()
    assert created is not None

def test_toggle_user_status(client, db_session, test_user, prepare_test_database):
    resp = client.put(f"/users/{test_user.id}/status", params={"active": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is False

def test_get_current_user(client, test_user, prepare_test_database):
    resp = client.get("/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(test_user.id)
