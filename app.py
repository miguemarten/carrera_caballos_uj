"""
🏇 Desafío: Galope con Propósito — Backend (Flask)
========================================
Servidor que maneja la lógica del juego, persiste datos en participantes.json
y transmite actualizaciones en tiempo real vía Server-Sent Events (SSE).
"""

import json
import os
import time
import threading
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

app = Flask(__name__)

# Route to serve the user's custom images directory "img_uj"
@app.route("/img_uj/<path:filename>")
def serve_img_uj(filename):
    img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img_uj")
    return send_from_directory(img_dir, filename)

# ──────────────────────────────────────────────
# ⚙️  CONFIGURACIÓN FÁCIL DE MODIFICAR
# ──────────────────────────────────────────────

# Puntaje necesario para cruzar la meta y ganar
PUNTAJE_META = 50  # <-- Cambia este valor para ajustar la meta
PUNTAJE_INTERMEDIO = 25  # <-- Meta intermedia

# Categorías de puntos: (etiqueta, valor)
# Modifica los nombres o valores a tu gusto
CATEGORIAS_PUNTOS = [
    {"nombre": "Puntualidad",      "valor": 1},   # Botón 1
    {"nombre": "Participación",    "valor": 1},   # Botón 2
    {"nombre": "Traer Biblia",     "valor": 1},   # Botón 3
    {"nombre": "Memorización",     "valor": 1},   # Botón 4
    {"nombre": "Traer Visita",     "valor": 2},   # Botón 5
]

# Ruta del archivo de datos
DATOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "participantes.json")

# ──────────────────────────────────────────────
# 📦  DATOS EN MEMORIA + PERSISTENCIA
# ──────────────────────────────────────────────

participantes = []
data_lock = threading.Lock()
# Contador de versiones para SSE (cada mutación lo incrementa)
data_version = 0


def cargar_datos():
    """Lee participantes.json del disco. Si no existe, lo crea vacío."""
    global participantes
    if os.path.exists(DATOS_PATH):
        with open(DATOS_PATH, "r", encoding="utf-8") as f:
            try:
                participantes = json.load(f)
            except json.JSONDecodeError:
                participantes = []
    else:
        participantes = []
        guardar_datos()


def guardar_datos():
    """Sobrescribe participantes.json con el estado actual."""
    with open(DATOS_PATH, "w", encoding="utf-8") as f:
        json.dump(participantes, f, ensure_ascii=False, indent=2)


def siguiente_id():
    """Devuelve el próximo ID disponible."""
    if not participantes:
        return 1
    return max(p["id"] for p in participantes) + 1


def notificar_cambio():
    """Incrementa la versión de datos para que SSE lo detecte."""
    global data_version
    data_version += 1


# ──────────────────────────────────────────────
# 🌐  RUTAS DE VISTAS
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """Redirige a la vista de admin por defecto."""
    return render_template("admin.html")


@app.route("/admin")
def admin():
    """Panel de control del administrador."""
    return render_template("admin.html")


@app.route("/proyector")
def proyector():
    """Vista de la carrera para proyectar al público."""
    return render_template("proyector.html")


# ──────────────────────────────────────────────
# 🔌  API REST
# ──────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config():
    """Devuelve la configuración del juego (meta, categorías)."""
    return jsonify({
        "puntaje_meta": PUNTAJE_META,
        "puntaje_intermedio": PUNTAJE_INTERMEDIO,
        "categorias": CATEGORIAS_PUNTOS
    })


@app.route("/api/participantes", methods=["GET"])
def api_listar():
    """Devuelve la lista completa de participantes."""
    with data_lock:
        return jsonify(participantes)


@app.route("/api/participantes", methods=["POST"])
def api_agregar():
    """Agrega un nuevo participante. Body: { "nombre": "..." }"""
    body = request.get_json(force=True)
    nombre = body.get("nombre", "").strip()
    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    with data_lock:
        nuevo = {
            "id": siguiente_id(),
            "nombre": nombre,
            "puntaje": 0,
            "ruta_imagen": "",  # <-- Asignar ruta a una foto para usar como avatar
            "emoji": body.get("emoji", "🐴")
        }
        participantes.append(nuevo)
        guardar_datos()
        notificar_cambio()

    return jsonify(nuevo), 201


@app.route("/api/participantes/<int:pid>/emoji", methods=["PUT"])
def api_update_emoji(pid):
    """Actualiza el emoji (skin) de un participante."""
    body = request.get_json(force=True)
    emoji = body.get("emoji", "🐴")
    with data_lock:
        for p in participantes:
            if p["id"] == pid:
                p["emoji"] = emoji
                guardar_datos()
                notificar_cambio()
                return jsonify(p)
        return jsonify({"error": "Participante no encontrado"}), 404

@app.route("/api/participantes/<int:pid>", methods=["DELETE"])
def api_eliminar(pid):
    """Elimina un participante por su ID."""
    global participantes
    with data_lock:
        original = len(participantes)
        participantes = [p for p in participantes if p["id"] != pid]
        if len(participantes) == original:
            return jsonify({"error": "Participante no encontrado"}), 404
        guardar_datos()
        notificar_cambio()
    return jsonify({"ok": True})


@app.route("/api/puntos", methods=["POST"])
def api_puntos():
    """
    Asigna puntos a un participante.
    Body: { "id": 1, "puntos": 10 }
    """
    body = request.get_json(force=True)
    pid = body.get("id")
    puntos = body.get("puntos", 0)

    if pid is None:
        return jsonify({"error": "Se requiere el ID del participante"}), 400

    with data_lock:
        for p in participantes:
            if p["id"] == pid:
                p["puntaje"] += puntos
                guardar_datos()
                notificar_cambio()
                return jsonify(p)
        return jsonify({"error": "Participante no encontrado"}), 404


@app.route("/api/sesion/nueva", methods=["POST"])
def api_nueva_sesion():
    """Reinicia todos los puntajes a 0 (mantiene nombres e IDs)."""
    with data_lock:
        for p in participantes:
            p["puntaje"] = 0
        guardar_datos()
        notificar_cambio()
    return jsonify({"ok": True, "participantes": participantes})


# ──────────────────────────────────────────────
# 📡  SERVER-SENT EVENTS (SSE)
# ──────────────────────────────────────────────

@app.route("/api/stream")
def api_stream():
    """
    Endpoint SSE — el proyector se suscribe aquí.
    Cada vez que hay un cambio, envía el JSON completo de participantes.
    """
    def generar():
        last_version = -1
        while True:
            if data_version != last_version:
                last_version = data_version
                with data_lock:
                    payload = json.dumps({
                        "participantes": participantes,
                        "puntaje_meta": PUNTAJE_META,
                        "puntaje_intermedio": PUNTAJE_INTERMEDIO
                    }, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            time.sleep(0.5)  # Polling interval interno (medio segundo)

    return Response(
        generar(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# ──────────────────────────────────────────────
# 🚀  ARRANQUE
# ──────────────────────────────────────────────

if __name__ == "__main__":
    cargar_datos()
    print("=" * 50)
    print("  Desafío: Galope con Propósito - Servidor iniciado")
    print(f"   Admin:     http://localhost:5000/admin")
    print(f"   Proyector: http://localhost:5000/proyector")
    print(f"   Meta:      {PUNTAJE_META} puntos")
    print(f"   Datos:     {DATOS_PATH}")
    print("=" * 50)
    # threaded=True para soportar SSE concurrente con peticiones normales
    app.run(debug=True, threaded=True, port=5000)
