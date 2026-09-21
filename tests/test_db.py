from backend.app.db.session import SessionLocal, check_db_health, get_db


def test_db_health():
    assert check_db_health() is True


def test_db_session():
    db = SessionLocal()
    try:
        assert db is not None
    finally:
        db.close()


def test_get_db_generator():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass
