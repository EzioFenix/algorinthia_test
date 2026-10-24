// Interacciones mínimas. Delegación de eventos en `document`: sigue funcionando cuando HTMX
// cambia partes de la página (y no hay JavaScript en línea, así la CSP puede ser estricta).
(function () {
  "use strict";

  function enviarPregunta(texto) {
    var area = document.getElementById("pregunta");
    if (!area) return;
    area.value = texto;
    area.form.requestSubmit();
  }

  document.addEventListener("click", function (e) {
    var ejemplo = e.target.closest("[data-ejemplo]");
    if (ejemplo) return enviarPregunta(ejemplo.textContent.trim());

    var copiar = e.target.closest("[data-copiar]");
    if (copiar && navigator.clipboard) {
      navigator.clipboard.writeText(copiar.dataset.copiar).then(function () {
        var original = copiar.textContent;
        copiar.textContent = "Copiado";
        setTimeout(function () { copiar.textContent = original; }, 1400);
      });
      return;
    }

    if (e.target.closest("[data-tema]")) {
      var raiz = document.documentElement;
      var oscuro = raiz.dataset.theme
        ? raiz.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      raiz.dataset.theme = oscuro ? "light" : "dark";
      try { localStorage.setItem("tema", raiz.dataset.theme); } catch (err) { /* sin almacenamiento */ }
      return;
    }

    var salto = e.target.closest("[data-ir-fila]");
    if (salto) {
      var fila = document.querySelector('tr[data-id="' + salto.dataset.irFila + '"]');
      if (fila) { fila.scrollIntoView({ block: "center", behavior: "smooth" }); fila.click(); }
    }
  });

  // Enter envía la pregunta; Mayús+Enter agrega salto de línea.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && e.target.matches("[data-enviar-enter]")) {
      e.preventDefault();
      e.target.form.requestSubmit();
    }
  });

  // Limpia el formulario cuando la petición terminó bien.
  document.addEventListener("htmx:afterRequest", function (e) {
    var form = e.detail.elt;
    if (form && form.matches && form.matches("form[data-reset-ok]") && e.detail.successful) form.reset();
  });

  // Marca la fila seleccionada de la tabla de evaluación.
  document.addEventListener("htmx:beforeRequest", function (e) {
    var fila = e.detail.elt;
    if (fila && fila.matches && fila.matches("tr[data-id]")) {
      document.querySelectorAll("tr.sel").forEach(function (f) { f.classList.remove("sel"); });
      fila.classList.add("sel");
    }
  });

  // Filtros de la tabla de evaluación (en el navegador, sin pedir nada al servidor).
  function filtrar() {
    var tabla = document.getElementById("tabla-eval");
    if (!tabla) return;
    var q = (document.getElementById("f-texto").value || "").toLowerCase();
    var tipo = document.getElementById("f-tipo").value;
    var soloAlertas = document.getElementById("f-alertas").checked;
    tabla.querySelectorAll("tbody tr").forEach(function (fila) {
      var visible = (!q || fila.dataset.texto.indexOf(q) !== -1)
        && (!tipo || fila.dataset.tipo === tipo)
        && (!soloAlertas || fila.dataset.alerta === "1");
      fila.hidden = !visible;
    });
  }
  document.addEventListener("input", function (e) { if (e.target.closest("[data-filtro]")) filtrar(); });
  document.addEventListener("change", function (e) {
    if (e.target.closest("[data-filtro]")) filtrar();
    if (e.target.matches("#f-ciega")) {
      var tabla = document.getElementById("tabla-eval");
      if (tabla) tabla.classList.toggle("ciega", e.target.checked);
    }
  });
})();
