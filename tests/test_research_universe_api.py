from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
