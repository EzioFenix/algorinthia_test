"""Normalización para BM25: minúsculas, sin acentos, sin palabras vacías y con stemming en español."""

import re

import Stemmer

from app.ingesta.parser_ley import sin_acentos

_stemmer = Stemmer.Stemmer("spanish")

PALABRAS_VACIAS = frozenset(
    """a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del desde
    donde durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha
    han hasta hay la las le les lo los mas me mi mis mucho muy ni no nos o os otra otro para pero por porque que
    quien se sea ser si sin sobre son su sus tambien te tiene tu tus un una uno unos y ya yo puedo pueden puede
    cuanto cuantos cuanta cuantas tengo tener debo deben debe hacer hago""".split()
)


def tokens(texto: str) -> list[str]:
    palabras = re.findall(r"\w+", sin_acentos(texto.lower()))
    return [_stemmer.stemWord(p) for p in palabras if p not in PALABRAS_VACIAS and len(p) > 1]


def para_indice(texto: str) -> str:
    return " ".join(tokens(texto))


def consulta_fts(texto: str) -> str:
    """Consulta FTS5 segura: cada término entrecomillado (sin operadores del usuario) y unidos con OR."""
    unicos = dict.fromkeys(tokens(texto))
    return " OR ".join(f'"{t}"' for t in unicos)
