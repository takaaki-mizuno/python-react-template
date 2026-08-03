from uuid import uuid4

from app.models.auth_errors import AuthSessionNotFoundError, UserNotFoundError


def test_user_not_found_error_keeps_user_id_and_message():
    user_id = uuid4()
    error = UserNotFoundError(user_id)

    assert isinstance(error, Exception)
    assert error.user_id == user_id
    assert "User" in str(error)
    assert str(user_id) in str(error)


def test_auth_session_not_found_error_keeps_session_id_and_message():
    session_id = uuid4()
    error = AuthSessionNotFoundError(session_id)

    assert isinstance(error, Exception)
    assert error.session_id == session_id
    assert "AuthSession" in str(error)
    assert str(session_id) in str(error)
