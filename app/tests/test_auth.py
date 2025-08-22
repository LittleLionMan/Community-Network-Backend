import pytest
from fastapi import status

class TestUserRegistration:

    def test_register_user_success(self, client):
        user_data = {
            "display_name": "testuser",
            "email": "test@example.com",
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User"
        }

        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data["display_name"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "password" not in data  # Password should not be returned
        assert "id" in data

    def test_register_duplicate_email(self, client):
        user_data = {
            "display_name": "testuser2",
            "email": "test2@example.com",
            "password": "TestPass123!"
        }

        # Register first user
        response1 = client.post("/api/auth/register", json=user_data)
        assert response1.status_code == status.HTTP_201_CREATED

        # Try to register with same email
        user_data["display_name"] = "testuser3"
        response2 = client.post("/api/auth/register", json=user_data)
        assert response2.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_display_name(self, client):
        user_data = {
            "display_name": "testuser4",
            "email": "test4@example.com",
            "password": "TestPass123!"
        }

        # Register first user
        response1 = client.post("/api/auth/register", json=user_data)
        assert response1.status_code == status.HTTP_201_CREATED

        # Try to register with same display name
        user_data["email"] = "test5@example.com"
        response2 = client.post("/api/auth/register", json=user_data)
        assert response2.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_invalid_password(self, client):
        user_data = {
            "display_name": "testuser6",
            "email": "test6@example.com",
            "password": "weak"  # Too weak
        }

        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

class TestUserLogin:

    def test_login_success(self, client):
        # Register user first
        user_data = {
            "display_name": "login_testuser",
            "email": "login_test@example.com",
            "password": "TestPass123!"
        }
        reg_response = client.post("/api/auth/register", json=user_data)
        print(f"Registration: {reg_response.status_code} - {reg_response.text}")

        # Login
        login_data = {
            "email": "login_test@example.com",
            "password": "TestPass123!"
        }

        response = client.post("/api/auth/login", json=login_data)
        print(f"Login: {response.status_code} - {response.text}")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        # Register user first
        user_data = {
            "display_name": "wrong_pw_testuser",
            "email": "wrong_pw_test@example.com",
            "password": "TestPass123!"
        }
        client.post("/api/auth/register", json=user_data)

        login_data = {
            "email": "wrong_pw_test@example.com",
            "password": "WrongPass123!"
        }

        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, client):
        login_data = {
            "email": "nonexistent@example.com",
            "password": "TestPass123!"
        }

        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
