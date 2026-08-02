from app.models.auth_csrf import SessionCsrfStatus


def test_session_csrf_status_values_are_stable():
    assert SessionCsrfStatus.VALID == "valid"
    assert SessionCsrfStatus.MISMATCH == "mismatch"
    assert SessionCsrfStatus.NO_SESSION == "no_session"
