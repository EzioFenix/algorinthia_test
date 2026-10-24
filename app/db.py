"""SQLite: esquema y conexión. Una conexión por operación; WAL permite leer mientras se ingiere."""

import sqlite3
from contextlib import contextmanager

from app.config import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabajos (
    id TEXT PRIMARY KEY,
    estado TEXT NOT NULL,              -- pendiente | procesando | terminado | terminado_con_errores
    creado TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trabajo_documentos (
    id INTEGER PRIMARY KEY,
    trabajo_id TEXT NOT NULL REFERENCES trabajos(id),
    nombre TEXT NOT NULL,              -- nombre original (solo para mostrar)
    ruta TEXT NOT NULL,                -- ruta en disco con nombre UUID
    estado TEXT NOT NULL,              -- pendiente | procesando | terminado | error
    error TEXT,
    resumen TEXT                       -- JSON con artículos nuevos/modificados/eliminados
);

-- Una fila por ley. Al subir una reforma se actualiza la misma fila (clave única).
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,        -- LFT, CPEUM, ...
    nombre TEXT NOT NULL,
    version_dof TEXT,                  -- fecha de "Última Reforma DOF"
    sha256 TEXT NOT NULL,
    actualizado TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Texto canónico de cada artículo: base para verificar que una cita existe.
CREATE TABLE IF NOT EXISTS articulos (
    documento_id INTEGER NOT NULL REFERENCES documentos(id),
    articulo TEXT NOT NULL,            -- "47", "330-A", "170 Bis"
    texto TEXT NOT NULL,
    hash TEXT NOT NULL,
    PRIMARY KEY (documento_id, articulo)
);

CREATE TABLE IF NOT EXISTS fragmentos (
    id INTEGER PRIMARY KEY,
    documento_id INTEGER NOT NULL REFERENCES documentos(id),
    articulo TEXT NOT NULL,
    apartado TEXT,                     -- A/B en el Art. 123 constitucional
    fraccion TEXT,
    ruta TEXT NOT NULL,                -- "Título … › Capítulo …"
    texto TEXT NOT NULL,
    hash TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fragmentos_art ON fragmentos(documento_id, articulo);

-- BM25: el texto se guarda ya normalizado y con stemming en español.
CREATE VIRTUAL TABLE IF NOT EXISTS fragmentos_fts USING fts5(texto, tokenize='unicode61 remove_diacritics 2');

-- Caché de embeddings por hash de texto: una reforma no recalcula lo que no cambió.
CREATE TABLE IF NOT EXISTS cache_embeddings (
    hash TEXT NOT NULL,
    modelo TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (hash, modelo)
);
"""


def conectar() -> sqlite3.Connection:
    ruta = config().db_path
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def conexion():
    conn = conectar()
    try:
        with conn:  # commit al salir, rollback si hay excepción
            yield conn
    finally:
        conn.close()


def inicializar() -> None:
    with conexion() as conn:
        conn.executescript(ESQUEMA)
