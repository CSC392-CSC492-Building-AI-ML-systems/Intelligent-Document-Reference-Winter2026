"""Model tests for file-processor."""

from src.models import ServiceRequest, ServiceResponse


def test_request_creation():
    req = ServiceRequest(id="123", payload={"key": "value"})
    assert req.id == "123"


def test_response_defaults():
    resp = ServiceResponse(id="123", result={})
    assert resp.status == "success"
