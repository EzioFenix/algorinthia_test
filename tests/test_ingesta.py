"""Reto 5: actualizar una ley reformada sin reprocesar todo, y aislar fallos por documento."""

from pathlib import Path

import pytest

from app.db import conexion
from app.ingesta import ingesta, worker
from app.ingesta.parser_ley import Articulo, Ley


def _ley(articulos: dict[str, str], version: str) -> Ley:
    return Ley("LFT", "LEY FEDERAL DEL TRABAJO", version,
               [Articulo(n, "Título", [t]) for n, t in articulos.items()])


@pytest.fixture
def pdf_falso(tmp_path, monkeypatch):
    """Simula PDFs: el contenido del archivo decide qué ley devuelve el parser."""
    leyes = {}

    def crear(nombre: str, ley: Ley) -> Path:
        ruta = tmp_path / nombre
        ruta.write_bytes(b"%PDF-" + nombre.encode())
        leyes[str(ruta)] = ley
        return ruta

    monkeypatch.setattr(ingesta, "extraer_paginas", lambda ruta, _: [str(ruta)])
    monkeypatch.setattr(ingesta, "parsear_ley", lambda paginas: leyes[paginas[0]])
    return crear


def test_reforma_solo_reprocesa_articulos_cambiados(pdf_falso, embeddings_falsos):
    v1 = pdf_falso("v1.pdf", _ley({"76": "seis días", "80": "prima 25%", "87": "aguinaldo"}, "01-01-2022"))
    r1 = ingesta.ingerir_pdf(v1)
    assert r1["articulos_nuevos"] == 3
    assert len(embeddings_falsos) == 3

    embeddings_falsos.clear()
    v2 = pdf_falso("v2.pdf", _ley({"76": "doce días", "80": "prima 25%", "90": "nuevo"}, "27-12-2022"))
    r2 = ingesta.ingerir_pdf(v2)
    assert (r2["articulos_nuevos"], r2["articulos_modificados"], r2["articulos_eliminados"],
            r2["articulos_sin_cambios"]) == (1, 1, 1, 1)
    assert len(embeddings_falsos) == 2  # solo el 76 reformado y el 90 nuevo

    with conexion() as conn:
        arts = dict(conn.execute("SELECT articulo, texto FROM articulos").fetchall())
        version = conn.execute("SELECT version_dof FROM documentos").fetchone()[0]
        fts = conn.execute("SELECT COUNT(*) FROM fragmentos_fts").fetchone()[0]
    assert arts == {"76": "doce días", "80": "prima 25%", "90": "nuevo"}
    assert version == "27-12-2022"
    assert fts == 3  # el índice BM25 no conserva fragmentos del artículo derogado


def test_mismo_pdf_no_se_reprocesa(pdf_falso, embeddings_falsos):
    ruta = pdf_falso("igual.pdf", _ley({"76": "doce días"}, "27-12-2022"))
    ingesta.ingerir_pdf(ruta)
    assert ingesta.ingerir_pdf(ruta)["sin_cambios"] is True


def test_un_pdf_roto_no_detiene_a_los_demas(pdf_falso, embeddings_falsos, tmp_path):
    bueno = pdf_falso("bueno.pdf", _ley({"76": "doce días"}, "27-12-2022"))
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"%PDF- roto")  # el parser falso no lo conoce → KeyError
    trabajo = worker.crear_trabajo([("roto.pdf", roto), ("bueno.pdf", bueno)])
    worker.procesar_trabajo(trabajo)

    estado = worker.estado_trabajo(trabajo)
    assert estado["estado"] == "terminado_con_errores"
    assert [d["estado"] for d in estado["documentos"]] == ["error", "terminado"]
