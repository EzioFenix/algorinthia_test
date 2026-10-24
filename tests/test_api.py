from fastapi.testclient import TestClient

from app.config import config
from app.main import app


def _cliente() -> TestClient:
    return TestClient(app)


def test_rechaza_archivo_que_no_es_pdf():
    with _cliente() as c:
        r = c.post("/documentos", files={"archivos": ("falso.pdf", b"hola, no soy un pdf", "application/pdf")})
    assert r.status_code == 400 and "no es un PDF" in r.json()["detail"]


def test_acepta_pdf_y_devuelve_trabajo_de_inmediato(monkeypatch):
    from app.ingesta import worker

    monkeypatch.setattr(worker, "procesar_trabajo", lambda _id: None)  # no procesa: solo se prueba la respuesta
    with _cliente() as c:
        r = c.post("/documentos", files={"archivos": ("ley.pdf", b"%PDF-1.5 contenido", "application/pdf")})
        assert r.status_code == 202
        trabajo_id = r.json()["trabajo_id"]
        assert c.get(f"/trabajo/{trabajo_id}").json()["estado"] in {"pendiente", "procesando"}


def test_trabajo_inexistente_es_404_y_id_invalido_422():
    with _cliente() as c:
        assert c.get("/trabajo/00000000-0000-4000-8000-000000000000").status_code == 404
        assert c.get("/trabajo/1 OR 1=1").status_code == 422


def test_pregunta_demasiado_corta_o_larga():
    with _cliente() as c:
        assert c.post("/preguntar", json={"pregunta": "a"}).status_code == 422
        assert c.post("/preguntar", json={"pregunta": "x" * 1001}).status_code == 422


def test_api_key_obligatoria_si_esta_configurada(monkeypatch):
    monkeypatch.setattr(config(), "api_key", "secreta")
    with _cliente() as c:
        assert c.get("/documentos").status_code == 401
        assert c.get("/documentos", headers={"X-API-Key": "secreta"}).status_code == 200


def test_enlace_a_la_traza_apunta_al_langfuse_local_sin_llamar_a_la_red(monkeypatch):
    from app import observabilidad

    c = config()
    monkeypatch.setattr(c, "langfuse_public_key", "pk-lf-prueba")
    monkeypatch.setattr(c, "langfuse_secret_key", "sk-lf-prueba")
    monkeypatch.setattr(observabilidad, "cliente", lambda: object())  # sin SDK real: no debe usarse la red
    assert observabilidad.url_traza("abc123") == "http://localhost:3000/project/asistente-laboral/traces/abc123"
    assert observabilidad.url_traza(None) is None
    monkeypatch.setattr(observabilidad, "cliente", lambda: None)  # Langfuse desactivado
    assert observabilidad.url_traza("abc123") is None
