"""Interfaz web: un solo front end con tres secciones (Asistente, Evaluación y Documentos).

HTMX navega y actualiza partes de la página con fragmentos HTML. Las plantillas escapan todo
automáticamente: el texto del modelo, de la pregunta o de la ley nunca se inserta como HTML.
"""

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import reportes, traza
from app import trazas as lector_trazas
from app.api.rutas import guardar_pdfs, limite_preguntas, listar_documentos
from app.asistente import responder
from app.busqueda.indice import indice
from app.config import config
from app.ingesta.worker import crear_trabajo, estado_trabajo, trabajos_recientes
from eval import calificacion

router = APIRouter(prefix="", include_in_schema=False)
plantillas = Jinja2Templates(directory=Path(__file__).parent / "plantillas")

EJEMPLOS = [
    "¿Me pueden correr por estar embarazada?",
    "¿Cuántos días de vacaciones me tocan en mi primer año?",
    "¿Cómo me pagan las horas extra?",
    "Trabajo desde casa, ¿me tienen que pagar el internet?",
    "¿Cuánto es el salario mínimo este año?",
]

# Sin scripts ni estilos de terceros: todo sale de /static, así que la política puede ser estricta.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def _nivel(valor: float | None) -> str:
    if not isinstance(valor, int | float):  # None, o un campo que ese reporte no trae (p. ej. corridas sin juez)
        return ""
    return "ok" if valor >= 0.85 else "warn" if valor >= 0.7 else "bad"


def _ms(valor: float | None) -> str:
    if not valor:
        return "—"
    if valor < 1:
        return "<1 ms"
    return f"{valor:.0f} ms" if valor < 1000 else f"{valor / 1000:.1f} s"


plantillas.env.filters["pct"] = lambda v: f"{v * 100:.0f}%" if isinstance(v, int | float) else "—"
plantillas.env.filters["ms"] = _ms
plantillas.env.globals["nivel"] = _nivel


def mismo_origen(request: Request) -> None:
    """Rechaza envíos de formularios desde otros sitios (CSRF): un servicio en localhost también es un blanco."""
    sitio = request.headers.get("sec-fetch-site")
    if sitio and sitio not in ("same-origin", "none"):
        raise HTTPException(403, "Origen no permitido")
    origen = request.headers.get("origin")
    if origen and urlparse(origen).netloc != request.headers.get("host"):
        raise HTTPException(403, "Origen no permitido")


def _base(seccion: str) -> dict:
    c = config()
    return {
        "seccion": seccion,
        "modelo": c.llm_model,
        "modo": c.modo_app,
        "embeddings": c.embed_model,
        "fragmentos": len(indice),
        "langfuse": bool(c.langfuse_public_key and c.langfuse_secret_key),
        "escritura": not c.api_key,  # con API_KEY definida, la página no puede escribir (no puede guardar secretos)
        "cal_n": calificacion.acuerdo(calificacion.cargar())["calificadas"],
        "cal_min": calificacion.MINIMO,
    }


def _html(request: Request, plantilla: str, seccion: str = "", **contexto) -> HTMLResponse:
    respuesta = plantillas.TemplateResponse(request, plantilla, {**_base(seccion), **contexto})
    respuesta.headers["Content-Security-Policy"] = CSP
    return respuesta


def _error(request: Request, mensaje: str) -> HTMLResponse:
    return _html(request, "_error.html", mensaje=mensaje)


# ── Asistente ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def asistente(request: Request):
    c = config()
    return _html(request, "asistente.html", "asistente", ejemplos=EJEMPLOS,
                 umbrales={"sin_relacion": c.umbral_sin_relacion, "reescritura": c.umbral_reescritura, "top_k": c.top_k})


@router.post("/ui/preguntar", response_class=HTMLResponse, dependencies=[Depends(mismo_origen)])
async def ui_preguntar(request: Request, pregunta: str = Form(..., min_length=3, max_length=1000)):
    try:
        limite_preguntas(request)
    except HTTPException as e:
        return _error(request, e.detail)
    resultado, detalle = await responder(request.app.state.http, pregunta.strip())
    return _html(request, "_respuesta.html", pregunta=pregunta.strip(), r=resultado,
                 segundos=detalle.ms.get("total", 0) / 1000, t=traza.construir(resultado, detalle))


# ── Evaluación ──────────────────────────────────────────────────────────────

def _tabla(reporte: dict, calificadas: dict) -> list[dict]:
    return [
        {
            "id": f["id"], "tipo": f["tipo"], "categoria": f["categoria"], "pregunta": f["pregunta"],
            "ok": reportes.es_ok(f), "alerta": reportes.en_alerta(f),
            "faithfulness": f.get("faithfulness"), "correctness": f.get("correctness"),
            "recall": f.get("recall_articulos"), "segundos": f["segundos"],
            "calificada": calificacion.numero(calificadas.get(f["id"], {}).get("humano_correcta_0a1")) is not None,
        }
        for f in reporte["resultados"]
    ]


def _corrida(corrida: str) -> dict:
    """Qué reporte se está viendo y si la calificación manual le corresponde.

    El CSV de calificación guarda las respuestas y los puntajes del juez de UNA corrida. Calificar (o comparar con el
    juez) las respuestas de otra corrida mezclaría cosas distintas, así que solo se permite en la suya."""
    rep = reportes.cargar(corrida)
    if rep is None:
        corrida, rep = "", reportes.cargar("")
    fecha = rep["resumen"]["fecha"] if rep else ""
    csv_corrida = calificacion.corrida_csv()
    calificable = csv_corrida is None or csv_corrida == fecha or (csv_corrida == "" and not corrida)
    historial = reportes.historial()
    return {
        "rep": rep, "corrida": corrida, "calificable": calificable, "historial": historial,
        "archivo_calificado": next((h["archivo"] for h in historial if h["fecha"] == csv_corrida), ""),
        "fecha_calificada": csv_corrida,
    }


@router.get("/evaluacion", response_class=HTMLResponse)
async def evaluacion(request: Request, corrida: str = ""):
    ctx = _corrida(corrida)
    rep = ctx["rep"]
    if not rep:
        return _html(request, "evaluacion.html", "evaluacion", rep=None)
    res = rep["resumen"]
    calificadas = calificacion.cargar() if ctx["calificable"] else {}
    return _html(
        request, "evaluacion.html", "evaluacion", res=res, **ctx,
        kpis_juez=[{"clave": k, "nombre": n, "desc": d, "valor": res.get(k)} for k, n, d in reportes.METRICAS_JUEZ
                   if res.get(k) is not None],
        kpis_propias=[{"clave": k, "nombre": n, "desc": d, "valor": res.get(k)} for k, n, d in reportes.METRICAS_PROPIAS
                      if res.get(k) is not None],
        tabla=_tabla(rep, calificadas),
        tipos=sorted({f["tipo"] for f in rep["resultados"]}),
        ac=calificacion.acuerdo(calificacion.cargar()),
    )


def _detalle(request: Request, pregunta_id: int, corrida: str = "", oob: bool = False,
             guardado: bool = False) -> HTMLResponse:
    ctx = _corrida(corrida)
    rep = ctx["rep"]
    f = reportes.fila(rep, pregunta_id) if rep else None
    if f is None:
        return _error(request, "Esa pregunta no está en este reporte.")
    cal = calificacion.cargar()
    fila_cal = cal.get(pregunta_id) if ctx["calificable"] else None
    return _html(
        request, "_eval_detalle.html", f=f, oob=oob, guardado=guardado, corrida=ctx["corrida"],
        calificable=ctx["calificable"], archivo_calificado=ctx["archivo_calificado"],
        recuperados=list(dict.fromkeys(f["recuperados"])), citados=list(dict.fromkeys(f["citados"])),
        esperados=f["articulos_esperados"],
        hc=calificacion.numero(fila_cal["humano_correcta_0a1"]) if fila_cal else None,
        hf=calificacion.numero(fila_cal["humano_fiel_0a1"]) if fila_cal else None,
        comentario=fila_cal["comentario"] if fila_cal else "",
        califica=bool(f["articulos_esperados"]),  # solo se califican las que tienen respuesta en la ley
        juez=[{"clave": k, "nombre": n, "valor": f.get(k), "razon": f.get(f"{k}_razon")}
              for k, n, _ in reportes.METRICAS_JUEZ if f.get(k) is not None],
        ok=reportes.es_ok(f), ac=calificacion.acuerdo(cal),
    )


@router.get("/ui/evaluacion/{pregunta_id}", response_class=HTMLResponse)
async def ui_eval_detalle(request: Request, pregunta_id: int, corrida: str = ""):
    return _detalle(request, pregunta_id, corrida)


@router.post("/ui/evaluacion/{pregunta_id}/calificar", response_class=HTMLResponse,
             dependencies=[Depends(mismo_origen)])
async def ui_calificar(request: Request, pregunta_id: int, correcta: str = Form(...), fiel: str = Form(""),
                       comentario: str = Form("", max_length=500), corrida: str = Form("")):
    if config().api_key:
        return _error(request, "Con API_KEY definida, la calificación desde la página está deshabilitada.")
    valor_c, valor_f = calificacion.numero(correcta), calificacion.numero(fiel)
    if valor_c not in (0, 0.5, 1) or (fiel != "" and valor_f not in (0, 0.5, 1)):
        return _error(request, "Calificación no válida.")
    ctx = _corrida(corrida)
    rep = ctx["rep"]
    if not rep or reportes.fila(rep, pregunta_id) is None:
        return _error(request, "Esa pregunta no está en este reporte.")
    if not ctx["calificable"]:
        return _error(request, "Tu calificación manual pertenece a otra corrida; ábrela para calificar o corregir.")
    calificacion.asegurar(rep["resultados"], rep["resumen"]["fecha"])
    try:
        calificacion.guardar(pregunta_id, valor_c, valor_f, comentario)
    except KeyError:
        return _error(request, "Esa pregunta no se califica a mano (no tiene respuesta esperada en la ley).")
    return _detalle(request, pregunta_id, ctx["corrida"], oob=True, guardado=True)


# ── Trazas (Langfuse local, leído desde el servidor) ────────────────────────

ENTORNOS = {"": "Todas", "default": "Uso real", "evaluacion": "Evaluación"}


def _aviso(request: Request, mensaje: str) -> HTMLResponse:
    return _html(request, "_aviso.html", mensaje=mensaje)


@router.get("/trazas", response_class=HTMLResponse)
async def trazas(request: Request, abrir: str = ""):
    return _html(request, "trazas.html", "trazas", entornos=ENTORNOS,
                 abrir=abrir if lector_trazas.ID_VALIDO.match(abrir) else "")


@router.get("/ui/trazas/lista", response_class=HTMLResponse)
async def ui_trazas_lista(request: Request, entorno: str = ""):
    if entorno not in ENTORNOS:
        return _error(request, "Entorno no válido.")
    try:
        filas = await lector_trazas.listar(30, entorno)
    except lector_trazas.LangfuseNoDisponible as e:
        return _aviso(request, str(e))
    return _html(request, "_trazas_lista.html", filas=filas)


@router.get("/ui/trazas/{trace_id}", response_class=HTMLResponse)
async def ui_traza_detalle(request: Request, trace_id: str, n: int = 0):
    try:
        t = await lector_trazas.detalle(trace_id)
    except ValueError:
        return _error(request, "Identificador de traza no válido.")
    except lector_trazas.LangfuseNoDisponible as e:
        return _aviso(request, str(e))
    if t is None:  # Langfuse tarda unos segundos en procesar la traza recién creada
        return _html(request, "_traza_espera.html", trace_id=trace_id, n=n + 1, rendido=n >= 10)
    return _html(request, "_traza_detalle.html", t=t)


# ── Documentos ──────────────────────────────────────────────────────────────

@router.get("/ingesta", response_class=HTMLResponse)
async def ingesta(request: Request):
    docs = await listar_documentos()
    return _html(request, "ingesta.html", "ingesta", documentos=docs, trabajos=trabajos_recientes(),
                 total_articulos=sum(d["articulos"] for d in docs), total_fragmentos=sum(d["fragmentos"] for d in docs))


@router.post("/ui/documentos", response_class=HTMLResponse, dependencies=[Depends(mismo_origen)])
async def ui_documentos(request: Request, archivos: list[UploadFile] = File(...)):
    if config().api_key:
        return _error(request, "La subida desde la página está deshabilitada; usa la API con X-API-Key.")
    try:
        guardados = await guardar_pdfs(archivos)
    except HTTPException as e:
        return _error(request, e.detail)
    return _html(request, "_trabajo.html", t=estado_trabajo(crear_trabajo(guardados)), refrescar=False)


@router.get("/ui/trabajo/{trabajo_id}", response_class=HTMLResponse)
async def ui_trabajo(request: Request, trabajo_id: str):
    t = estado_trabajo(trabajo_id)
    if not t:
        return _error(request, "Trabajo no encontrado")
    return _html(request, "_trabajo.html", t=t, refrescar=True)


@router.get("/ui/documentos", response_class=HTMLResponse)
async def ui_lista_documentos(request: Request):
    return _html(request, "_documentos.html", documentos=await listar_documentos())
