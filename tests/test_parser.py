from app.ingesta.parser_ley import (
    RE_ARTICULO,
    Articulo,
    armar_parrafos,
    fragmentar,
    numero_articulo,
    parsear_ley,
)

ENCABEZADO = "LEY FEDERAL DEL TRABAJO\nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\nSecretaría General\n" \
             "Secretaría de Servicios Parlamentarios\nÚltima Reforma DOF 14-05-2026\n{n} de 2\n"


def test_variantes_de_encabezado_de_articulo():
    casos = {
        "Artículo 1o.- La presente Ley": "1",
        "Artículo 2º.- Las normas": "2",
        "Artículo 15-A. Se deroga.": "15-A",
        "Artículo 170 Bis.- Los padres": "170 Bis",
        "Artículo 123. Toda persona": "123",
        "Artículo 890- Se deroga.": "890",
    }
    for linea, esperado in casos.items():
        assert numero_articulo(RE_ARTICULO.match(linea)) == esperado


def test_referencia_en_texto_no_es_encabezado():
    assert RE_ARTICULO.match("Artículo 123 Constitucional; de la Ley Reglamentaria") is None


def test_une_lineas_cortadas_en_parrafos():
    assert armar_parrafos(["Primera parte ", "del párrafo.", "Segundo párrafo."]) == [
        "Primera parte del párrafo.",
        "Segundo párrafo.",
    ]


def test_parsea_ley_quita_encabezados_notas_y_transitorios():
    pagina1 = ENCABEZADO.format(n=1) + (
        "TITULO TERCERO\nCondiciones de Trabajo\nCAPITULO IV\nVacaciones\n"
        "Artículo 76.- Las personas trabajadoras disfrutarán de un periodo anual de \n"
        "vacaciones pagadas.\nArtículo reformado DOF 27-12-2022\n"
    )
    pagina2 = ENCABEZADO.format(n=2) + (
        "Artículo 80.- Prima no menor de veinticinco por ciento.\n"
        "TRANSITORIOS\nArtículo 1º.- Esta Ley entrará en vigor.\n"
    )
    ley = parsear_ley([pagina1, pagina2])
    assert (ley.clave, ley.version_dof) == ("LFT", "14-05-2026")
    assert [a.numero for a in ley.articulos] == ["76", "80"]  # el transitorio "1" no se indexa
    assert ley.articulos[0].texto == "Las personas trabajadoras disfrutarán de un periodo anual de vacaciones pagadas."
    assert "Vacaciones" in ley.articulos[0].ruta


def test_articulo_largo_se_parte_por_fraccion_con_contexto():
    parrafos = ["Queda prohibido a las personas empleadoras:"] + [
        f"{r}. {'texto de la fracción ' * 20}" for r in ["I", "II", "III", "XV"]
    ] + ["II Bis.- fracción adicionada " * 5]
    fragmentos = fragmentar(Articulo("133", "Título Cuarto", parrafos))
    assert [f.fraccion for f in fragmentos] == [None, "I", "II", "III", "XV", "II Bis"]
    assert all(f.texto.startswith("Queda prohibido") for f in fragmentos)
