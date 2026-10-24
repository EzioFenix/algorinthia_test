from app import reportes
from app.asistente import Detalle
from app.busqueda.hibrida import Resultado
from app.busqueda.indice import MetaFragmento
from app.traza import construir
from eval import calificacion


def _resultado_busqueda(art="133", fraccion="XV", sim=0.56):
    meta = MetaFragmento(1, "LFT", "LEY FEDERAL DEL TRABAJO", art, None, fraccion, "ruta", "texto")
    return Resultado(meta, 0.03, sim, 2, 1)


def test_traza_completa_marca_el_fragmento_citado_y_los_pasos():
    d = Detalle(similitud_max=0.56, fragmentos=[_resultado_busqueda(), _resultado_busqueda("47", "XV")],
                glosario=["despido"], tokens_entrada=1500, tokens_salida=300, ms={"busqueda": 30, "generacion": 4000,
                                                                                  "validacion": 5, "total": 4040})
    r = {"citas": [{"ley": "LFT", "articulo": "133", "apartado": None, "fraccion": "XV"}], "encontrado_en_documentos": True}
    t = construir(r, d)
    assert [p["titulo"] for p in t["pasos"]] == ["Búsqueda", "Generación", "Validación"]
    assert [f["citado"] for f in t["fragmentos"]] == [True, False]
    assert t["costo_usd"] > 0 and t["glosario"] == ["despido"]
    assert sum(s["pct"] for s in t["segmentos"]) >= 100


def test_traza_del_corto_circuito_marca_generacion_y_validacion_como_omitidas():
    d = Detalle(similitud_max=0.3, fragmentos=[_resultado_busqueda(sim=0.3)], ms={"busqueda": 20, "total": 20})
    t = construir({"citas": [], "encontrado_en_documentos": False}, d)
    assert [p["estado"] for p in t["pasos"]] == ["ok", "omitido", "omitido"]
    assert "no se llamó al modelo" in t["pasos"][1]["resumen"]
    assert t["tokens_entrada"] == 0


def test_traza_con_reintento_y_citas_rechazadas():
    d = Detalle(similitud_max=0.6, fragmentos=[_resultado_busqueda()], reintentos=1,
                rechazadas=[{"cita": {}, "motivo": "El artículo F1 de LFT no existe"}],
                ms={"busqueda": 30, "generacion": 4000, "generacion_reintento": 3000, "validacion": 5, "total": 7100})
    t = construir({"citas": [], "encontrado_en_documentos": False}, d)
    assert [p["titulo"] for p in t["pasos"]] == ["Búsqueda", "Generación", "Reintento", "Validación"]
    assert t["pasos"][-1]["estado"] == "warn" and t["rechazadas"][0]["motivo"].startswith("El artículo F1")


def test_acuerdo_entre_persona_y_juez():
    filas = {
        1: {"id": "1", "pregunta": "p1", "humano_correcta_0a1": "1", "juez_correctness": "0.9", "humano_fiel_0a1": "",
            "juez_faithfulness": "1", "comentario": ""},
        2: {"id": "2", "pregunta": "p2", "humano_correcta_0a1": "0", "juez_correctness": "0.9", "humano_fiel_0a1": "",
            "juez_faithfulness": "1", "comentario": "el juez se equivoca"},
    }
    r = calificacion.acuerdo(filas)
    m = r["metricas"][0]
    assert (r["calificadas"], m["n"], m["acuerdos"], m["porcentaje"]) == (2, 2, 1, 0.5)
    assert m["juez_mas_laxo"] == 1 and m["discrepancias"][0]["id"] == 2


def test_historial_no_repite_la_misma_corrida(reporte, tmp_path):
    import json

    carpeta = tmp_path / "eval" / "reportes"
    copia = json.loads((carpeta / "ultimo.json").read_text())
    (carpeta / "v1_glosario_inicial.json").write_text(json.dumps(copia))  # misma fecha que eval_2026…
    corridas = reportes.historial()
    assert len(corridas) == 1 and corridas[0]["archivo"] == "v1_glosario_inicial"


def test_fusion_conserva_los_mejores_por_significado_aunque_bm25_no_los_vea():
    from app.busqueda.hibrida import fusionar

    densos = [100, 1, 2, 3, 4, 5, 6, 7]          # el 100 es el mejor por significado
    lexicos = [1, 2, 3, 4, 5, 6, 7, 8]           # pero la búsqueda por palabras no lo trae
    sin_garantia, *_ = fusionar(densos, lexicos, k=6, garantizados=0)
    con_garantia, *_ = fusionar(densos, lexicos, k=6)
    assert 100 not in sin_garantia                # el defecto que se vio en la traza de Langfuse
    assert 100 in con_garantia and len(con_garantia) == 6
    assert con_garantia[0] != 100                 # se ordena por RRF: entra, pero no se le regala el primer lugar


def test_fusion_no_duplica_ni_excede_k():
    from app.busqueda.hibrida import fusionar

    mejores, *_ = fusionar([1, 2, 3], [1, 2, 3], k=2)
    assert mejores == [1, 2]
    mejores, *_ = fusionar([1, 2], [], k=6)
    assert mejores == [1, 2]
