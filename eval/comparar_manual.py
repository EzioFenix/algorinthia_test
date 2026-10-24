"""Compara la calificación manual con la del juez de DeepEval (la misma lógica que muestra la pestaña Evaluación).

Uso:  uv run python -m eval.comparar_manual
"""

from eval import calificacion


def main() -> None:
    resumen = calificacion.acuerdo(calificacion.cargar())
    if not resumen["metricas"]:
        print("Sin calificaciones manuales todavía: usa la pestaña Evaluación o edita eval/calificacion_manual.csv")
    for m in resumen["metricas"]:
        print(f"\n## {m['nombre']}: {m['n']} respuestas calificadas")
        print(f"Acuerdo aprueba/reprueba: {m['acuerdos']}/{m['n']} ({m['porcentaje']:.0%})")
        print(f"Diferencia media de puntaje: {m['diferencia_media']:.2f}")
        print(f"Juez reprueba lo que la persona aprueba: {m['juez_mas_estricto']} · "
              f"Juez aprueba lo que la persona reprueba: {m['juez_mas_laxo']}")
        print("Discrepancias (para explicar en el README):")
        for d in m["discrepancias"]:
            print(f"  [{d['id']}] humano={d['humano']} juez={d['juez']:.2f} · {d['pregunta'][:70]} · {d['comentario']}")
    if resumen["calificadas"] < resumen["minimo"]:
        print(f"\n⚠ Solo {resumen['calificadas']} respuestas calificadas a mano; el enunciado pide al menos {resumen['minimo']}.")


if __name__ == "__main__":
    main()
