"""Convierte el PDF de una ley de la Cámara de Diputados en artículos y fragmentos.

Formato observado en los PDF oficiales (LFT DOF 14-05-2026, CPEUM DOF 07-10-2026):
- Cada página empieza con un encabezado de 6 líneas que termina en "N de M".
- Las líneas cortadas a mitad de párrafo terminan en espacio; las que cierran párrafo, no.
- Notas editoriales en línea propia: "Párrafo reformado DOF 01-05-2019, 15-01-2026".
- Encabezados: "Artículo 1o.-", "Artículo 2º.-", "Artículo 15-A.", "Artículo 170 Bis.-", "Artículo 123."
- Los transitorios repiten números de artículo, así que no se indexan.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium

RE_PIE_ENCABEZADO = re.compile(r"^\d+ de \d+$")
RE_VERSION = re.compile(r"Última Reforma DOF (\d{2}-\d{2}-\d{4})", re.IGNORECASE)
RE_ARTICULO = re.compile(
    r"^Art[íi]culo (\d+)(?:o|º|°)?(?:\.? (Bis|Ter|Qu[áa]ter|Quinquies|Sexies))?(?:-([A-Z]{1,2}))?(?:\.-?|-)\s*(.*)$"
)
RE_NOTA = re.compile(
    r"^(Párrafos?|Fracci(ón|ones)|Art[íi]culos?|Incisos?|Apartados?|Denominación|T[íi]tulos?|Cap[íi]tulos?|"
    r"Secci(ón|ones)|Último|Base|Numeral|Reforma|Fe de erratas|Primer|Segundo|Tercer|Cuarto|Quinto)\b[^.]*\bDOF\b"
)
RE_SOLO_FECHAS = re.compile(r"^(\d{2}-\d{2}-\d{4},?\s*)+$")
RE_TITULO = re.compile(r"^T[ÍI]TULO\s+\S+", re.IGNORECASE)
RE_CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+[IVXLC]+(\s+Bis)?\s*$", re.IGNORECASE)
RE_TRANSITORIOS = re.compile(r"^(ARTÍCULOS? )?TRANSITORIOS?\b")
RE_FRACCION = re.compile(r"^([IVXLC]+)(?: (Bis|Ter|Qu[áa]ter))?\.-?\s")
RE_APARTADO = re.compile(r"^([AB])\.\s")

CLAVES_CONOCIDAS = {
    "LEY FEDERAL DEL TRABAJO": "LFT",
    "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS": "CPEUM",
}
# De la Constitución solo interesa el artículo 123 (lo que pide el enunciado).
ARTICULOS_POR_LEY = {"CPEUM": {"123"}}

MAX_FRAGMENTO = 1800  # caracteres (~450 tokens)
PREFIJO_FRACCION = 300  # contexto del encabezado del artículo que acompaña a cada fracción


@dataclass
class Articulo:
    numero: str
    ruta: str
    parrafos: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.parrafos)


@dataclass
class Fragmento:
    articulo: str
    apartado: str | None
    fraccion: str | None
    ruta: str
    texto: str

    @property
    def hash(self) -> str:
        return sha256_texto(self.texto)

    def etiqueta(self, clave: str) -> str:
        partes = [f"{clave} Art. {self.articulo}"]
        if self.apartado:
            partes.append(f"apartado {self.apartado}")
        if self.fraccion:
            partes.append(f"fracc. {self.fraccion}")
        return ", ".join(partes)


@dataclass
class Ley:
    clave: str
    nombre: str
    version_dof: str | None
    articulos: list[Articulo]


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def extraer_paginas(ruta: Path, max_paginas: int) -> list[str]:
    pdf = pdfium.PdfDocument(ruta)
    try:
        if len(pdf) > max_paginas:
            raise ValueError(f"El PDF tiene {len(pdf)} páginas (máximo {max_paginas})")
        return [pdf[i].get_textpage().get_text_range().replace("\r", "") for i in range(len(pdf))]
    finally:
        pdf.close()


def quitar_encabezado(pagina: str) -> list[str]:
    lineas = pagina.split("\n")
    for i, linea in enumerate(lineas[:8]):
        if RE_PIE_ENCABEZADO.match(linea.strip()):
            return lineas[i + 1 :]
    return lineas


def identificar_ley(primera_pagina: str) -> tuple[str, str, str | None]:
    nombre = primera_pagina.strip().split("\n")[0].strip()
    normal = sin_acentos(nombre).upper()
    clave = CLAVES_CONOCIDAS.get(normal)
    if clave is None:
        palabras = [p for p in re.findall(r"[A-Z]+", normal) if p not in {"DE", "DEL", "LA", "LOS", "LAS", "Y"}]
        clave = "".join(p[0] for p in palabras) or "DOC"
    version = RE_VERSION.search(primera_pagina)
    return clave, nombre, version.group(1) if version else None


def numero_articulo(m: re.Match) -> str:
    numero, ordinal, letra = m.group(1), m.group(2), m.group(3)
    if letra:
        numero += f"-{letra}"
    if ordinal:
        numero += f" {ordinal.capitalize()}"
    return numero


def armar_parrafos(lineas: list[str]) -> list[str]:
    """Une las líneas cortadas (terminan en espacio) en párrafos completos."""
    parrafos, actual = [], ""
    for linea in lineas:
        actual += linea
        if not linea.endswith(" "):
            if actual.strip():
                parrafos.append(" ".join(actual.split()))
            actual = ""
    if actual.strip():
        parrafos.append(" ".join(actual.split()))
    return parrafos


def parsear_ley(paginas: list[str]) -> Ley:
    clave, nombre, version = identificar_ley(paginas[0])
    lineas = [l for p in paginas for l in quitar_encabezado(p)]

    articulos: list[Articulo] = []
    lineas_articulo: list[str] = []
    titulo = capitulo = ""
    pendiente = None  # "titulo" | "capitulo": la siguiente línea es su nombre

    def cerrar():
        if articulos and lineas_articulo:
            articulos[-1].parrafos = armar_parrafos(lineas_articulo)

    for linea in lineas:
        limpia = linea.strip()
        if not limpia or RE_NOTA.match(limpia) or RE_SOLO_FECHAS.match(limpia):
            continue
        if RE_TRANSITORIOS.match(limpia) and articulos:
            break
        if pendiente:
            if pendiente == "titulo":
                titulo += f" {limpia}"
            else:
                capitulo += f" {limpia}"
            pendiente = None
            continue
        if len(limpia) < 40 and RE_TITULO.match(limpia):
            titulo, capitulo, pendiente = limpia, "", "titulo"
            continue
        if RE_CAPITULO.match(limpia):
            capitulo, pendiente = limpia, "capitulo"
            continue
        m = RE_ARTICULO.match(limpia)
        if m:
            cerrar()
            ruta = " › ".join(x for x in (titulo, capitulo) if x)
            articulos.append(Articulo(numero=numero_articulo(m), ruta=ruta))
            lineas_articulo = [m.group(4) + (" " if linea.endswith(" ") else "")]
            continue
        if articulos:
            lineas_articulo.append(linea)
    cerrar()

    # Un mismo número puede repetirse si el PDF tiene anexos; se conserva la primera aparición.
    vistos, unicos = set(), []
    for a in articulos:
        if a.numero not in vistos and a.parrafos:
            vistos.add(a.numero)
            unicos.append(a)
    if clave in ARTICULOS_POR_LEY:
        unicos = [a for a in unicos if a.numero in ARTICULOS_POR_LEY[clave]]
    return Ley(clave=clave, nombre=nombre, version_dof=version, articulos=unicos)


def _partir(texto: str, limite: int) -> list[str]:
    """Parte un texto largo por párrafos y, si hace falta, por palabras."""
    piezas, actual = [], ""
    for parrafo in texto.split("\n"):
        while len(parrafo) > limite:
            corte = parrafo.rfind(" ", 0, limite)
            corte = corte if corte > 0 else limite
            if actual:
                piezas.append(actual)
                actual = ""
            piezas.append(parrafo[:corte])
            parrafo = parrafo[corte:].strip()
        if actual and len(actual) + len(parrafo) + 1 > limite:
            piezas.append(actual)
            actual = ""
        actual = f"{actual}\n{parrafo}" if actual else parrafo
    if actual:
        piezas.append(actual)
    return piezas


def fragmentar(articulo: Articulo) -> list[Fragmento]:
    """Artículo corto → un fragmento. Largo → introducción + un fragmento por fracción."""
    texto = articulo.texto
    if len(texto) <= MAX_FRAGMENTO:
        return [Fragmento(articulo.numero, None, None, articulo.ruta, texto)]

    # Unidades: (apartado, fracción, párrafos)
    unidades: list[tuple[str | None, str | None, list[str]]] = [(None, None, [])]
    apartado = None
    for parrafo in articulo.parrafos:
        if m := RE_APARTADO.match(parrafo):
            apartado = m.group(1)
            unidades.append((apartado, None, [parrafo]))
        elif m := RE_FRACCION.match(parrafo):
            fraccion = m.group(1) + (f" {m.group(2)}" if m.group(2) else "")
            unidades.append((apartado, fraccion, [parrafo]))
        else:
            unidades[-1][2].append(parrafo)

    def resumen(texto: str) -> str:
        return texto[:PREFIJO_FRACCION].rsplit(" ", 1)[0] + "…\n" if len(texto) > PREFIJO_FRACCION else texto + "\n"

    # Cada fracción lleva como contexto el encabezado del artículo o de su apartado (A/B del 123).
    encabezados = {None: resumen("\n".join(unidades[0][2])) if unidades[0][2] else ""}
    for apartado, fraccion, parrafos in unidades:
        if apartado and fraccion is None and parrafos:
            encabezados[apartado] = resumen(parrafos[0])

    fragmentos = []
    for apartado, fraccion, parrafos in unidades:
        if not parrafos:
            continue
        cuerpo = "\n".join(parrafos)
        contexto = encabezados.get(apartado, "") if fraccion else ""
        for pieza in _partir(cuerpo, MAX_FRAGMENTO - len(contexto)):
            fragmentos.append(Fragmento(articulo.numero, apartado, fraccion, articulo.ruta, contexto + pieza))
    return fragmentos
