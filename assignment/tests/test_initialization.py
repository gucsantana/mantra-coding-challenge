import pytest
from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestInitialization:
    def test_initialize_data_loads_default_mock_users(self):
        return True # init_data currently commented out due to being an unrestricted destructive method
        # client = APIClient()

        # response = client.post("/init_data", {"file": "MOCK_DATA.json"}, format="json")

        # assert response.status_code == status.HTTP_200_OK
        # assert response.data["message"] == "Data initialized successfully from MOCK_DATA.json"
        # assert User.objects.filter(username="testuser").exists()
        # assert User.objects.filter(username="testuser5").exists()
