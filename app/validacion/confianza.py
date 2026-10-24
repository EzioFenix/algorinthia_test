"""Nivel de confianza de una respuesta a partir de señales medibles (no de lo que el modelo diga de sí mismo)."""

from app.validacion.citas import COINCIDENCIA_BUENA, CitaRechazada, CitaVerificada

SIM_BAJA, SIM_ALTA = 0.45, 0.70  # rango de similitud observado entre preguntas sin y con respuesta


def calcular(
    similitud_max: float,
    validas: list[CitaVerificada],
    rechazadas: list[CitaRechazada],
    reintentos: int,
    reescrita: bool,
) -> dict:
    motivos = []
    s_busqueda = min(max((similitud_max - SIM_BAJA) / (SIM_ALTA - SIM_BAJA), 0.0), 1.0)
    motivos.append(f"similitud máxima de búsqueda {similitud_max:.2f}")

    total = len(validas) + len(rechazadas)
    s_citas = len(validas) / total if total else 0.0
    motivos.append(f"{len(validas)}/{total} citas verificadas")

    s_textual = sum(min(c.coincidencia / COINCIDENCIA_BUENA, 1.0) for c in validas) / len(validas) if validas else 0.0

    puntaje = 0.4 * s_busqueda + 0.4 * s_citas + 0.2 * s_textual
    if reintentos:
        puntaje -= 0.1
        motivos.append("el modelo necesitó un reintento")
    if reescrita:
        puntaje -= 0.05
        motivos.append("la pregunta se reformuló para encontrar artículos")
    puntaje = round(min(max(puntaje, 0.0), 1.0), 2)
    nivel = "alta" if puntaje >= 0.75 else "media" if puntaje >= 0.5 else "baja"
    return {"nivel": nivel, "puntaje": puntaje, "motivos": motivos}
