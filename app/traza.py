"""Arma, para la interfaz, el recorrido de una respuesta: pasos, tiempos y datos de cada etapa."""

from app.asistente import Detalle
from app.config import config
from app.llm.cliente import costo_usd


def _clave(cita: dict) -> tuple:
    return (cita["ley"], cita["articulo"], cita.get("apartado"), cita.get("fraccion"))


def construir(resultado: dict, d: Detalle) -> dict:
    citadas = {_clave(c) for c in resultado["citas"]}
    fragmentos = [
        {
            "etiqueta": r.fragmento.etiqueta,
            "similitud": r.similitud,
            "rrf": r.rrf,
            "bm25": r.rango_bm25,
            "denso": r.rango_denso,
            "citado": (r.fragmento.ley, r.fragmento.articulo, r.fragmento.apartado, r.fragmento.fraccion) in citadas,
        }
        for r in d.fragmentos
    ]
    pasos = [{
        "clave": "busqueda", "titulo": "Búsqueda", "estado": "ok", "ms": d.ms.get("busqueda", 0.0),
        "resumen": f"{len(fragmentos)} fragmentos · similitud máxima {d.similitud_max:.2f}",
    }]

    if "generacion" not in d.ms:  # corto-circuito: nada se parece a la pregunta, no se llamó al modelo
        pasos.append({"clave": "generacion", "titulo": "Generación", "estado": "omitido", "ms": 0.0,
                      "resumen": f"Omitida: similitud {d.similitud_max:.2f} < {config().umbral_sin_relacion}, "
                                 "no se llamó al modelo"})
        pasos.append({"clave": "validacion", "titulo": "Validación", "estado": "omitido", "ms": 0.0,
                      "resumen": "Omitida: no hay respuesta que validar"})
    else:
        pasos.append({"clave": "generacion", "titulo": "Generación", "estado": "ok", "ms": d.ms["generacion"],
                      "resumen": f"{config().llm_model} · respuesta en JSON validado por esquema"})
        if d.reintentos:
            pasos.append({"clave": "reintento", "titulo": "Reintento", "estado": "warn",
                          "ms": d.ms.get("generacion_reintento", 0.0) + d.ms.get("validacion_reintento", 0.0),
                          "resumen": "La primera respuesta no pasó la validación; se le pidió corregirla una vez"})
        validas, rechazadas = len(resultado["citas"]), len(d.rechazadas)
        if not validas and not rechazadas and not resultado["encontrado_en_documentos"]:
            resumen, estado = "El modelo indicó que no está en los documentos: no hay citas que verificar", "ok"
        else:
            resumen = f"{validas} {'cita verificada' if validas == 1 else 'citas verificadas'} · {rechazadas} rechazadas"
            estado = "warn" if rechazadas else "ok"
        pasos.append({"clave": "validacion", "titulo": "Validación", "estado": estado,
                      "ms": d.ms.get("validacion", 0.0),
                      "resumen": resumen})

    medidos = [(p["titulo"], p["ms"]) for p in pasos if p["ms"] > 0]
    suma = sum(ms for _, ms in medidos) or 1.0
    return {
        "pasos": pasos,
        "segmentos": [{"titulo": t, "ms": ms, "pct": max(ms / suma * 100, 2.0)} for t, ms in medidos],
        "fragmentos": fragmentos,
        "glosario": d.glosario,
        "reescrita": d.consulta_reescrita,
        "rechazadas": d.rechazadas,
        "total_ms": d.ms.get("total", 0.0),
        "tokens_entrada": d.tokens_entrada,
        "tokens_salida": d.tokens_salida,
        "tokens_embedding": d.tokens_embedding,
        "costo_usd": costo_usd(d.tokens_entrada + d.tokens_embedding, d.tokens_salida)["total"],
        "umbral": config().umbral_sin_relacion,
    }
