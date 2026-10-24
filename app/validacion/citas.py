"""Verificación de las citas que propone el modelo.

Una cita se acepta solo si:
1. el artículo existe en la base (para esa ley),
2. estaba entre los fragmentos que se le dieron al modelo, y
3. el texto que dice citar se parece al texto real (fuzzy match).
El texto entregado al usuario siempre es el canónico de la base, nunca el que escribió el modelo.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.busqueda.indice import MetaFragmento
from app.db import conexion
from app.ingesta.parser_ley import sin_acentos

COINCIDENCIA_MINIMA = 60  # por debajo: el texto citado no corresponde al artículo
COINCIDENCIA_BUENA = 85

ROMANOS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
           (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


@dataclass
class CitaVerificada:
    ley: str
    articulo: str
    apartado: str | None
    fraccion: str | None
    texto: str
    coincidencia: float


@dataclass
class CitaRechazada:
    cita: dict
    motivo: str


def a_romano(n: int) -> str:
    salida = ""
    for valor, letra in ROMANOS:
        while n >= valor:
            salida, n = salida + letra, n - valor
    return salida


def normalizar_ley(ley: str) -> str:
    normal = sin_acentos(ley or "").upper()
    if "CONSTITU" in normal or "CPEUM" in normal:
        return "CPEUM"
    if "TRABAJO" in normal or normal.strip() == "LFT":
        return "LFT"
    return normal.strip()


def normalizar_articulo(articulo: str) -> str:
    """'Artículo 3o.' → '3', '330 a' → '330-A', '170 bis' → '170 Bis'."""
    a = re.sub(r"(?i)^\s*(art[íi]culo|art\.?)\s*", "", articulo or "").strip().rstrip(".-")
    m = re.match(r"(?i)^(\d+)\s*(?:o|º|°)?\.?\s*(bis|ter|qu[áa]ter)?\s*-?\s*([a-z]{1,2})?\b", a)
    if not m:
        return a
    numero, ordinal, letra = m.groups()
    if letra and letra.lower() in {"o"}:
        letra = None
    resultado = numero
    if letra:
        resultado += f"-{letra.upper()}"
    if ordinal:
        resultado += f" {ordinal.capitalize()}"
    return resultado


def normalizar_fraccion(fraccion: str | None) -> str | None:
    if not fraccion:
        return None
    f = re.sub(r"(?i)^\s*(fracci[óo]n|fracc?\.?)\s*", "", fraccion).strip().rstrip(".-")
    if f.isdigit():
        return a_romano(int(f))
    m = re.match(r"(?i)^([ivxlc]+)\s*(bis|ter)?$", f)
    if not m:
        return None
    return m.group(1).upper() + (f" {m.group(2).capitalize()}" if m.group(2) else "")


def _normal(texto: str) -> str:
    return " ".join(sin_acentos(texto.lower()).split())


def verificar(citas: list[dict], recuperados: list[MetaFragmento]) -> tuple[list[CitaVerificada], list[CitaRechazada]]:
    validas: list[CitaVerificada] = []
    rechazadas: list[CitaRechazada] = []
    vistas = set()

    with conexion() as conn:
        for cita in citas:
            ley = normalizar_ley(cita.get("ley", ""))
            articulo = normalizar_articulo(cita.get("articulo", ""))
            fraccion = normalizar_fraccion(cita.get("fraccion"))
            apartado = (cita.get("apartado") or "").strip().upper()[:1] or None

            existe = conn.execute(
                "SELECT 1 FROM articulos a JOIN documentos d ON d.id = a.documento_id"
                " WHERE d.clave = ? AND a.articulo = ?",
                (ley, articulo),
            ).fetchone()
            if not existe:
                rechazadas.append(CitaRechazada(cita, f"El artículo {articulo} de {ley} no existe en los documentos"))
                continue

            del_articulo = [f for f in recuperados if f.ley == ley and f.articulo == articulo]
            if not del_articulo:
                rechazadas.append(CitaRechazada(cita, f"{ley} Art. {articulo} existe pero no estaba en los fragmentos dados"))
                continue

            # Se elige el fragmento con la fracción indicada; si no, el que mejor coincide con el texto citado.
            texto_citado = _normal(cita.get("cita_textual", ""))
            candidatos = [f for f in del_articulo if fraccion and f.fraccion == fraccion] or del_articulo
            mejor = max(candidatos, key=lambda f: fuzz.partial_ratio(texto_citado, _normal(f.texto)))
            coincidencia = fuzz.partial_ratio(texto_citado, _normal(mejor.texto)) if texto_citado else 0.0
            if coincidencia < COINCIDENCIA_MINIMA:
                rechazadas.append(CitaRechazada(
                    cita, f"El texto citado no corresponde a {ley} Art. {articulo} (coincidencia {coincidencia:.0f}%)"))
                continue

            clave = (ley, articulo, mejor.apartado, mejor.fraccion)
            if clave in vistas:
                continue
            vistas.add(clave)
            validas.append(CitaVerificada(ley, articulo, mejor.apartado or apartado, mejor.fraccion,
                                          mejor.texto, round(coincidencia, 1)))
    return validas, rechazadas
