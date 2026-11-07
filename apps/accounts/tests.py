import pytest
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_custom_user_authenticates_with_email():
    User = get_user_model()
    user = User.objects.create_user(username="cliente", email="cliente@example.com", password="secret123")
    assert user.check_password("secret123")
