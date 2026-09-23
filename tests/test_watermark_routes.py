from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.routes.watermark_routes import router


def test_manual_remove_watermark_smoke(tmp_path, monkeypatch):
    src = tmp_path / "manual.jpg"
    Image.new("RGB", (40, 40), (9, 9, 9)).save(src)

    class MockLama:
        def __call__(self, image, mask):
            return image.copy()

    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: MockLama())
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/api/remove-watermark",
        json={
            "image_path": str(src).replace("\\", "/"),
            "regions": [{"x": 2, "y": 2, "width": 8, "height": 8}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["regions_count"] == 1
