"""La interfaz: un solo front end con Asistente, Evaluación y Documentos."""

import csv

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from eval import calificacion


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


def test_las_tres_secciones_y_los_estaticos_responden(cliente):
    for ruta, texto in [("/", "Pregunta sobre tus derechos"), ("/evaluacion", "Todavía no hay resultados"),
                        ("/ingesta", "Las leyes que consulta")]:
        r = cliente.get(ruta)
        assert r.status_code == 200 and texto in r.text, ruta
    for estatico in ("/static/app.css", "/static/app.js", "/static/htmx.min.js", "/static/icono.svg"):
        assert cliente.get(estatico).status_code == 200, estatico


def test_la_politica_de_seguridad_no_permite_scripts_ni_estilos_externos(cliente):
    csp = cliente.get("/").headers["content-security-policy"]
    assert "script-src 'self';" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert "http" not in csp  # nada de orígenes de terceros
    assert "https://" not in cliente.get("/").text  # y la página tampoco los pide


def test_evaluacion_muestra_metricas_filas_y_detalle(cliente, reporte):
    html = cliente.get("/evaluacion").text
    assert "Fidelidad" in html and "Pregunta 1 de prueba" in html and 'data-id="2"' in html
    detalle = cliente.get("/ui/evaluacion/1").text
    assert "Tu calificación" in detalle and "razón del juez" in detalle and "LFT 76" in detalle
    sin_respuesta = cliente.get("/ui/evaluacion/2").text
    assert "abstención" in sin_respuesta and "Guardar calificación" not in sin_respuesta
    assert "no está en este reporte" in cliente.get("/ui/evaluacion/999").text


def test_calificar_guarda_en_el_csv_y_actualiza_el_panel(cliente, reporte):
    r = cliente.post("/ui/evaluacion/1/calificar", data={"correcta": "0.5", "fiel": "0", "comentario": "=1+1 parcial"})
    assert r.status_code == 200 and "guardada" in r.text
    assert 'id="nav-cal"' in r.text and "1/15" in r.text  # contador de la barra lateral (actualización fuera de banda)
    fila = calificacion.cargar()[1]
    assert (fila["humano_correcta_0a1"], fila["humano_fiel_0a1"]) == ("0.5", "0.0")
    assert fila["comentario"] == "'=1+1 parcial"  # una fórmula no se ejecuta al abrir el CSV en Excel
    # el acuerdo con el juez se calcula con lo que ya está calificado
    assert calificacion.acuerdo(calificacion.cargar())["metricas"][0]["n"] == 1


def test_calificar_rechaza_valores_invalidos_y_preguntas_sin_respuesta(cliente, reporte):
    assert "no válida" in cliente.post("/ui/evaluacion/1/calificar", data={"correcta": "7"}).text
    assert "no se califica a mano" in cliente.post("/ui/evaluacion/2/calificar", data={"correcta": "1"}).text
    assert "no está en este reporte" in cliente.post("/ui/evaluacion/999/calificar", data={"correcta": "1"}).text


def test_los_formularios_rechazan_peticiones_de_otros_sitios(cliente, reporte):
    datos = {"correcta": "1"}
    assert cliente.post("/ui/evaluacion/1/calificar", data=datos, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert cliente.post("/ui/evaluacion/1/calificar", data=datos, headers={"Origin": "https://malo.example"}).status_code == 403
    assert cliente.post("/ui/preguntar", data={"pregunta": "hola mundo"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    ok = cliente.post("/ui/evaluacion/1/calificar", data=datos,
                      headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"})
    assert ok.status_code == 200


def test_con_api_key_la_pagina_no_escribe(cliente, reporte, monkeypatch):
    monkeypatch.setattr(config(), "api_key", "secreta")
    assert "deshabilitada" in cliente.post("/ui/evaluacion/1/calificar", data={"correcta": "1"}).text
    assert "deshabilitada" in cliente.post(
        "/ui/documentos", files={"archivos": ("a.pdf", b"%PDF-1.5", "application/pdf")}).text
    assert not calificacion.ruta().exists()


def test_la_calificacion_no_se_pierde_al_regenerar_la_plantilla(reporte):
    calificacion.asegurar(reporte)
    calificacion.guardar(1, 1.0, None, "bien")
    calificacion.asegurar(reporte)  # una nueva evaluación no debe borrar lo calificado
    assert calificacion.cargar()[1]["humano_correcta_0a1"] == "1.0"
    with open(calificacion.ruta(), newline="") as f:
        assert len(list(csv.DictReader(f))) == 1  # solo las preguntas con respuesta en la ley


def test_se_puede_calificar_aunque_el_csv_todavia_no_exista(cliente, reporte):
    # una evaluación sin juez no crea el CSV; el formulario debe aparecer igual y mirar no debe escribir nada
    assert "Guardar calificación" in cliente.get("/ui/evaluacion/1").text
    assert not calificacion.ruta().exists()


# ── Trazas (Langfuse local) ──────────────────────────────────────────────────

ID = "a" * 32
OBS = [  # el padre y el hijo empiezan en el mismo instante: debe salir primero el padre
    {"id": "h1", "parentObservationId": "r", "name": "busqueda", "type": "RETRIEVER", "startTime": "2026-10-23T22:00:00.000Z",
     "latency": 0.05, "level": "DEFAULT", "metadata": '{"scope.name": "ruido", "tokens": 18}'},
    {"id": "r", "parentObservationId": None, "name": "preguntar", "type": "SPAN", "startTime": "2026-10-23T22:00:00.000Z",
     "latency": 2.0, "level": "DEFAULT", "environment": "default",
     "input": '{"pregunta": "¿Cuántas vacaciones?"}',
     "output": '{"respuesta": "Doce días", "encontrado_en_documentos": true, "confianza": {"nivel": "alta", "puntaje": 0.9}}'},
    {"id": "h2", "parentObservationId": "r", "name": "generacion", "type": "GENERATION", "startTime": "2026-10-23T22:00:00.100Z",
     "latency": 1.8, "level": "WARNING", "statusMessage": "JSON incompleto", "usageDetails": {"input": 1000, "output": 100},
     "totalCost": 0.00012},
]


def test_detalle_de_traza_ordena_padre_primero_y_calcula_cascada(monkeypatch):
    import asyncio

    from app import trazas

    async def falso(params):
        return [dict(o) for o in OBS]

    monkeypatch.setattr(trazas, "_observaciones", falso)
    t = asyncio.run(trazas.detalle(ID))
    assert [e["nombre"] for e in t["etapas"]] == ["preguntar", "busqueda", "generacion"]
    assert [e["profundidad"] for e in t["etapas"]] == [0, 1, 1]
    assert t["pregunta"] == "¿Cuántas vacaciones?" and t["confianza"]["nivel"] == "alta"
    gen = t["etapas"][2]
    assert (gen["tokens_entrada"], gen["tokens_salida"], gen["costo"]) == (1000, 100, 0.00012)
    assert 4 < gen["izq_pct"] < 6 and 88 < gen["ancho_pct"] < 92  # 0.1 s de 2 s y 1.8 s de 2 s
    assert "scope.name" not in (t["etapas"][1]["metadata"] or "")  # el ruido de OpenTelemetry se quita
    assert t["tokens_total"] == 1100


def test_detalle_de_traza_rechaza_ids_raros_y_devuelve_none_si_no_llego(monkeypatch):
    import asyncio

    from app import trazas

    async def vacio(params):
        return []

    monkeypatch.setattr(trazas, "_observaciones", vacio)
    assert asyncio.run(trazas.detalle(ID)) is None
    with pytest.raises(ValueError):
        asyncio.run(trazas.detalle("../../etc/passwd"))


def test_paginas_de_trazas_sin_langfuse_explican_que_falta(cliente):
    assert cliente.get("/trazas").status_code == 200
    assert "Langfuse está desactivado" in cliente.get("/ui/trazas/lista").text  # sin llaves en el entorno de pruebas
    assert "no válido" in cliente.get("/ui/trazas/zzz").text
    assert "no válido" in cliente.get("/ui/trazas/lista?entorno=x").text


def test_traza_recien_creada_reintenta_y_luego_se_rinde(cliente, monkeypatch):
    from app import trazas as lector

    async def no_llega(trace_id):
        return None

    monkeypatch.setattr(lector, "detalle", no_llega)
    espera = cliente.get(f"/ui/trazas/{ID}?n=1").text
    assert "procesando la traza" in espera and f"/ui/trazas/{ID}?n=2" in espera
    final = cliente.get(f"/ui/trazas/{ID}?n=10").text
    assert "no llegó" in final and "hx-trigger" not in final  # deja de preguntar para siempre


# ── Varias corridas: la calificación manual pertenece a UNA ──────────────────

@pytest.fixture
def dos_corridas(reporte, tmp_path):
    """La corrida principal y una variante «max» (otro modelo) con otras respuestas."""
    import json

    carpeta = tmp_path / "eval" / "reportes"
    base = json.loads((carpeta / "ultimo.json").read_text())
    base["resumen"].update(fecha="2026-10-23T23:30:00", modelo="qwen3.8:27b-mlx", etiqueta="max")
    base["resultados"][0]["respuesta"] = "respuesta distinta del modelo grande"
    (carpeta / "eval_20261023-233000_max.json").write_text(json.dumps(base))
    return "eval_20261023-233000_max"


def test_la_calificacion_solo_se_permite_en_su_corrida(cliente, dos_corridas):
    principal = "2026-10-23T14:22:16"
    ok = cliente.post("/ui/evaluacion/1/calificar", data={"correcta": "1", "corrida": ""})
    assert "guardada" in ok.text and calificacion.corrida_csv() == principal  # el CSV queda ligado a la corrida principal

    # en la variante «max» no se puede calificar: mezclaría sus respuestas con los puntajes del juez de la otra corrida
    rechazo = cliente.post("/ui/evaluacion/1/calificar", data={"correcta": "0", "corrida": dos_corridas})
    assert "pertenece a otra corrida" in rechazo.text
    assert calificacion.cargar()[1]["humano_correcta_0a1"] == "1.0"  # lo calificado no se tocó

    detalle = cliente.get(f"/ui/evaluacion/1?corrida={dos_corridas}").text
    assert "respuesta distinta del modelo grande" in detalle and "Guardar calificación" not in detalle
    assert "pertenece a otra corrida" in detalle
    assert "Guardar calificación" in cliente.get("/ui/evaluacion/1").text  # en la principal sí


def test_pagina_de_evaluacion_elige_corrida_y_lista_las_variantes(cliente, dos_corridas):
    html = cliente.get(f"/evaluacion?corrida={dos_corridas}").text
    assert "qwen3.8:27b-mlx" in html and "Volver a la corrida principal" in html
    assert f"corrida={dos_corridas}" in html  # el detalle de cada pregunta conserva la corrida elegida
    # una corrida inexistente o con un nombre malicioso cae a la principal sin error
    for malo in ("no_existe", "../../etc/passwd", "a/b"):
        r = cliente.get("/evaluacion", params={"corrida": malo})
        assert r.status_code == 200 and "Volver a la corrida principal" not in r.text


def test_una_variante_no_reemplaza_el_reporte_principal_ni_crea_calificacion(tmp_path):
    import json

    from eval import correr_eval

    correr_eval.DIR_REPORTES = tmp_path / "rep"
    resultados = [{"id": 1, "tipo": "directa", "encontrado": True, "confianza": "alta", "citados": [], "articulos_esperados": ["LFT 76"],
                   "recall_articulos": 1.0, "pregunta": "p", "respuesta": "r"}]
    res = {"fecha": "2026-10-24T10:00:00", "modelo": "m", "etiqueta": "max", "embeddings": "e", "juez": "j", "por_tipo": {}}
    ruta = correr_eval.escribir_reportes(resultados, res, con_juez=True, etiqueta="max")
    assert ruta.name.endswith("_max.json") and (tmp_path / "rep" / "ultimo_max.json").exists()
    assert not (tmp_path / "rep" / "ultimo.json").exists()      # la corrida principal no se pisa
    assert not calificacion.ruta().exists()                      # y no se crea una plantilla de calificación
    assert json.loads(ruta.read_text())["resumen"]["etiqueta"] == "max"
