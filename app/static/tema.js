// Se carga en <head> antes de pintar: aplica el tema guardado sin parpadeo.
try {
  var t = localStorage.getItem("tema");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) { /* almacenamiento bloqueado: se usa el tema del sistema */ }
