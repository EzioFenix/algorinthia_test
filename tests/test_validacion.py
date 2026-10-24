from app.busqueda.indice import MetaFragmento
from app.db import conexion
from app.validacion.citas import normalizar_articulo, normalizar_fraccion, normalizar_ley, verificar

TEXTO_133_XV = "Queda prohibido…\nXV. Despedir a una trabajadora o coaccionarla para que renuncie por estar embarazada"


def _sembrar():
    with conexion() as conn:
        doc = conn.execute("INSERT INTO documentos (clave, nombre, sha256) VALUES ('LFT', 'LEY FEDERAL DEL TRABAJO', 'x')").lastrowid
        for art in ("133", "5", "330-E"):
            conn.execute("INSERT INTO articulos VALUES (?, ?, ?, 'h')", (doc, art, f"texto {art}"))


def _fragmento(articulo="133", fraccion="XV", texto=TEXTO_133_XV):
    return MetaFragmento(1, "LFT", "LEY FEDERAL DEL TRABAJO", articulo, None, fraccion, "ruta", texto)


def test_normalizaciones():
    assert normalizar_articulo("Artículo 3o.") == "3"
    assert normalizar_articulo("330 a") == "330-A"
    assert normalizar_articulo("170 bis") == "170 Bis"
    assert normalizar_fraccion("fracción xv") == "XV"
    assert normalizar_fraccion("15") == "XV"
    assert normalizar_ley("Ley Federal del Trabajo") == "LFT"
    assert normalizar_ley("Constitución") == "CPEUM"


def test_cita_correcta_se_acepta_con_texto_canonico():
    _sembrar()
    validas, rechazadas = verificar(
        [{"ley": "LFT", "articulo": "133", "fraccion": "XV",
          "cita_textual": "Despedir a una trabajadora o coaccionarla para que renuncie por estar embarazada"}],
        [_fragmento()],
    )
    assert not rechazadas
    assert validas[0].texto == TEXTO_133_XV  # el texto entregado es el de la base, no el del modelo


def test_articulo_inexistente_se_rechaza():
    _sembrar()
    validas, rechazadas = verificar([{"ley": "LFT", "articulo": "999 Bis", "cita_textual": "x"}], [_fragmento()])
    assert not validas and "no existe" in rechazadas[0].motivo


def test_articulo_real_pero_no_recuperado_se_rechaza():
    _sembrar()
    validas, rechazadas = verificar([{"ley": "LFT", "articulo": "5", "cita_textual": "texto 5"}], [_fragmento()])
    assert not validas and "no estaba en los fragmentos" in rechazadas[0].motivo


def test_texto_citado_inventado_se_rechaza():
    _sembrar()
    validas, rechazadas = verificar(
        [{"ley": "LFT", "articulo": "133", "cita_textual": "El aguinaldo será de noventa días de salario"}],
        [_fragmento()],
    )
    assert not validas and "no corresponde" in rechazadas[0].motivo
