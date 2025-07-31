from app.core.password import hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("secret")
    assert hashed != b"secret"
    assert verify_password("secret", hashed)
