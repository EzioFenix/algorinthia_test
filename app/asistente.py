"""Flujo de /preguntar: búsqueda → modelo → validación, cada etapa como observación de Langfuse."""

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.busqueda.hibrida import Resultado, buscar, expandir
from app.config import config
from app.llm import prompts
from app.llm.cliente import achat, aembeber, costo_usd
from app.observabilidad import observacion, url_traza
from app.validacion import confianza
from app.validacion.citas import verificar

# Un solo llamado al LLM a la vez: en una laptop, la concurrencia solo agrega latencia y memoria.
_semaforo_llm = asyncio.Semaphore(1)

MSG_SIN_RELACION = (
    "No encontré nada sobre esto en la Ley Federal del Trabajo ni en el artículo 123 constitucional. "
    "Te sugiero consultarlo directamente con Recursos Humanos."
)
MSG_SIN_RESPALDO = (
    "No encontré artículos que respalden una respuesta confiable a tu pregunta en los documentos consultados. "
    "Te sugiero consultarlo con Recursos Humanos."
)


class CitaLLM(BaseModel):
    ley: str
    articulo: str
    apartado: str | None = None
    fraccion: str | None = None
    cita_textual: str = ""


class SalidaLLM(BaseModel):
    citas: list[CitaLLM] = []
    no_encontrado: bool
    respuesta: str = Field(min_length=1)


@dataclass
class Detalle:
    """Información interna que usa la evaluación (no se expone en la API)."""

    consulta_lexica: str = ""
    consulta_reescrita: str | None = None
    glosario: list[str] = field(default_factory=list)
    similitud_max: float = 0.0
    fragmentos: list[Resultado] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_embedding: int = 0
    reintentos: int = 0
    rechazadas: list[dict] = field(default_factory=list)
    ms: dict[str, float] = field(default_factory=dict)


async def _embeber_y_buscar(http: httpx.AsyncClient, pregunta: str, k: int, detalle: Detalle):
    consulta, agregados = expandir(pregunta)
    with observacion("embedding", tipo="embedding", model=config().embed_model, input=pregunta) as emb_obs:
        emb = await aembeber(http, pregunta)
        emb_obs.update(usage_details={"input": emb.tokens}, cost_details=costo_usd(emb.tokens, 0))
    detalle.tokens_embedding += emb.tokens
    resultados, sim_max = await asyncio.to_thread(buscar, consulta, emb.vectores[0], k)
    return consulta, agregados, resultados, sim_max


async def _reescribir(http: httpx.AsyncClient, pregunta: str, detalle: Detalle) -> str | None:
    mensajes = [{"role": "system", "content": prompts.REESCRITURA}, {"role": "user", "content": pregunta}]
    with observacion("reescritura", tipo="generation", model=config().llm_model, input=mensajes) as gen:
        async with _semaforo_llm:
            r = await achat(http, mensajes, prompts.ESQUEMA_REESCRITURA)
        detalle.tokens_entrada += r.tokens_entrada
        detalle.tokens_salida += r.tokens_salida
        gen.update(
            output=r.contenido,
            usage_details={"input": r.tokens_entrada, "output": r.tokens_salida},
            cost_details=costo_usd(r.tokens_entrada, r.tokens_salida),
        )
    try:
        return json.loads(r.contenido)["consulta"].strip() or None
    except (json.JSONDecodeError, KeyError, AttributeError):
        return None


async def _buscar(http: httpx.AsyncClient, pregunta: str, detalle: Detalle) -> None:
    c = config()
    inicio = time.perf_counter()
    with observacion("busqueda", tipo="retriever", input={"pregunta": pregunta}) as span:
        consulta, agregados, resultados, sim_max = await _embeber_y_buscar(http, pregunta, c.top_k, detalle)
        # Reto 2: si la pregunta coloquial apenas se parece a la ley, se reformula con el LLM y se busca de nuevo.
        if c.umbral_sin_relacion <= sim_max < c.umbral_reescritura:
            reescrita = await _reescribir(http, pregunta, detalle)
            if reescrita:
                detalle.consulta_reescrita = reescrita
                consulta2, _, resultados2, sim2 = await _embeber_y_buscar(http, reescrita, c.top_k, detalle)
                if sim2 > sim_max:
                    consulta, resultados, sim_max = consulta2, resultados2, sim2
        detalle.consulta_lexica, detalle.fragmentos, detalle.similitud_max = consulta, resultados, sim_max
        detalle.glosario = agregados
        span.update(
            output=[
                {"etiqueta": r.fragmento.etiqueta, "similitud": round(r.similitud, 3), "rrf": round(r.rrf, 4),
                 "rango_bm25": r.rango_bm25, "rango_denso": r.rango_denso}
                for r in resultados
            ],
            metadata={"similitud_max": round(sim_max, 3), "glosario": agregados,
                      "tokens": detalle.tokens_embedding, "costo_usd": costo_usd(detalle.tokens_embedding, 0)["total"],
                      "consulta_reescrita": detalle.consulta_reescrita},
        )
    detalle.ms["busqueda"] = (time.perf_counter() - inicio) * 1000


async def _generar(http: httpx.AsyncClient, mensajes: list[dict], detalle: Detalle, nombre: str):
    c = config()
    inicio = time.perf_counter()
    with observacion(nombre, tipo="generation", model=c.llm_model, input=mensajes,
                     model_parameters={"temperature": c.llm_temperature, "num_ctx": c.llm_num_ctx}) as gen:
        async with _semaforo_llm:
            r = await achat(http, mensajes, prompts.ESQUEMA_RESPUESTA)
        detalle.tokens_entrada += r.tokens_entrada
        detalle.tokens_salida += r.tokens_salida
        try:
            salida, error = SalidaLLM.model_validate_json(r.contenido), None
        except ValidationError as e:
            salida, error = None, str(e)[:500]
        gen.update(
            output=r.contenido,
            usage_details={"input": r.tokens_entrada, "output": r.tokens_salida},
            cost_details=costo_usd(r.tokens_entrada, r.tokens_salida),
            level="WARNING" if error else "DEFAULT",
            status_message=error,
        )
    detalle.ms[nombre] = (time.perf_counter() - inicio) * 1000
    return salida, r.contenido, error


def _validar(salida: SalidaLLM | None, detalle: Detalle, nombre: str):
    inicio = time.perf_counter()
    with observacion(nombre, tipo="guardrail", input=salida.model_dump() if salida else None) as span:
        if salida is None or salida.no_encontrado:
            validas, rechazadas = [], []
        else:
            validas, rechazadas = verificar([x.model_dump() for x in salida.citas], [r.fragmento for r in detalle.fragmentos])
        span.update(
            output={"validas": [f"{v.ley} Art. {v.articulo} {v.fraccion or ''}".strip() for v in validas],
                    "rechazadas": [r.motivo for r in rechazadas]},
            metadata={"tokens": 0, "costo_usd": 0.0},  # validación determinista: no usa el modelo
            level="WARNING" if rechazadas else "DEFAULT",
        )
    detalle.ms[nombre] = (time.perf_counter() - inicio) * 1000
    return validas, rechazadas


def _sin_respuesta(mensaje: str, nivel: str, motivos: list[str], trace_id: str | None) -> dict:
    return {
        "respuesta": mensaje,
        "encontrado_en_documentos": False,
        "citas": [],
        "confianza": {"nivel": nivel, "puntaje": None, "motivos": motivos},
        "trace_id": trace_id,
        "trace_url": url_traza(trace_id),
    }


async def responder(http: httpx.AsyncClient, pregunta: str) -> tuple[dict, Detalle]:
    detalle = Detalle()
    inicio = time.perf_counter()
    with observacion("preguntar", input={"pregunta": pregunta}) as traza:
        trace_id = getattr(traza, "trace_id", None)
        await _buscar(http, pregunta, detalle)

        # Reto 3: sin nada parecido en los documentos, se responde sin llamar al modelo (rápido y sin inventar).
        if detalle.similitud_max < config().umbral_sin_relacion or not detalle.fragmentos:
            resultado = _sin_respuesta(
                MSG_SIN_RELACION, "alta",
                [f"similitud máxima {detalle.similitud_max:.2f} < umbral {config().umbral_sin_relacion}"], trace_id)
        else:
            mensajes = [
                {"role": "system", "content": prompts.SISTEMA},
                {"role": "user", "content": prompts.mensaje_usuario(
                    pregunta, [r.fragmento for r in detalle.fragmentos])},
            ]
            salida, crudo, error = await _generar(http, mensajes, detalle, "generacion")
            validas, rechazadas = _validar(salida, detalle, "validacion")

            # Reto 4: un reintento si la salida no es válida o si ninguna cita resistió la verificación.
            if salida is None or (not salida.no_encontrado and not validas):
                detalle.reintentos = 1
                problema = error or "; ".join(r.motivo for r in rechazadas) or "no incluiste citas"
                mensajes += [
                    {"role": "assistant", "content": crudo},
                    {"role": "user", "content": f"Tu respuesta tiene problemas: {problema}. Corrígela usando solo los "
                                                "FRAGMENTOS y sus etiquetas exactas, o marca no_encontrado si no alcanzan."},
                ]
                salida, crudo, error = await _generar(http, mensajes, detalle, "generacion_reintento")
                validas, rechazadas = _validar(salida, detalle, "validacion_reintento")
            detalle.rechazadas = [{"cita": r.cita, "motivo": r.motivo} for r in rechazadas]

            if salida is None:
                resultado = _sin_respuesta(MSG_SIN_RESPALDO, "baja", ["el modelo no devolvió una respuesta válida"], trace_id)
            elif salida.no_encontrado:
                resultado = _sin_respuesta(salida.respuesta, "media",
                                           ["el modelo indicó que los fragmentos no contienen la respuesta"], trace_id)
            elif not validas:
                resultado = _sin_respuesta(MSG_SIN_RESPALDO, "baja",
                                           ["ninguna cita del modelo se pudo verificar"], trace_id)
            else:
                resultado = {
                    "respuesta": salida.respuesta,
                    "encontrado_en_documentos": True,
                    "citas": [
                        {"ley": v.ley, "articulo": v.articulo, "apartado": v.apartado, "fraccion": v.fraccion,
                         "texto": v.texto}
                        for v in validas
                    ],
                    "confianza": confianza.calcular(detalle.similitud_max, validas, rechazadas,
                                                    detalle.reintentos, detalle.consulta_reescrita is not None),
                    "trace_id": trace_id,
                    "trace_url": url_traza(trace_id),
                }

        detalle.ms["total"] = (time.perf_counter() - inicio) * 1000
        traza.update(output=resultado, metadata={"tokens_entrada": detalle.tokens_entrada,
                                                 "tokens_salida": detalle.tokens_salida,
                                                 "costo_usd": costo_usd(detalle.tokens_entrada, detalle.tokens_salida)})
        puntaje = resultado["confianza"]["puntaje"]
        if puntaje is not None:
            traza.score_trace(name="confianza", value=puntaje)
        traza.score_trace(name="encontrado_en_documentos", value=float(resultado["encontrado_en_documentos"]))
        traza.score_trace(name="citas_rechazadas", value=float(len(detalle.rechazadas)))
    return resultado, detalle
