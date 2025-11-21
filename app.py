from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort
)
from flask_pymongo import PyMongo
from dotenv import load_dotenv
from bson import ObjectId
from bson.binary import Binary
from datetime import datetime, UTC
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from functools import wraps
from gridfs import GridFS
from xhtml2pdf import pisa
from uuid import uuid4
import os
import certifi
from io import BytesIO

# ==========================
# APP + MONGO
# ==========================
load_dotenv()
app = Flask(__name__)
app.secret_key = "dev"   # cámbialo en producción

app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app, tls=True, tlsCAFile=certifi.where())

# GridFS (archivos binarios en Atlas)
fs = GridFS(mongo.db)

# ==========================
# LOGIN / ROLES
# ==========================
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.email = doc.get("email")
        self.role = doc.get("role", "user")

    @property
    def is_admin(self):
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id):
    doc = mongo.db.usuarios.find_one({"_id": ObjectId(user_id)})
    return User(doc) if doc else None


def role_required(role):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if role == "admin" and not current_user.is_admin:
                flash("Solo administradores.")
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        return wrapper
    return deco


# Seed admin (una sola vez)
def ensure_admin():
    if not mongo.db.usuarios.find_one({"email": "admin@demo"}):
        mongo.db.usuarios.insert_one({
            "email": "admin@demo",
            "password": generate_password_hash("admin123"),
            "role": "admin",
            "creado_en": datetime.now(UTC)
        })


ensure_admin()

# ==========================
# UTILIDADES
# ==========================


def save_to_gridfs(file_storage):
    """Guarda un archivo en GridFS y retorna el ObjectId, o None si no hay archivo."""
    if not file_storage or file_storage.filename == "":
        return None
    data = file_storage.read()
    if not data:
        return None
    content_type = file_storage.mimetype or "application/octet-stream"
    fname = file_storage.filename
    file_id = fs.put(data, filename=fname, content_type=content_type)
    return file_id


@app.route("/media/<file_id>")
def media(file_id):
    """
    Sirve un archivo (avatar, imagen de producto, etc.) almacenado en GridFS.
    """
    try:
        file = fs.get(ObjectId(file_id))
        filename = file.filename or "file.bin"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }.get(ext, "application/octet-stream")

        return send_file(
            BytesIO(file.read()),
            mimetype=mime,
            download_name=filename
        )
    except Exception as e:
        print("Error al servir media:", e)
        return "Archivo no encontrado", 404

# ==========================
# AUTENTICACIÓN
# ==========================


@app.route("/login", methods=["GET", "POST"])
def login():
    # Si ya está logueado, redirigimos según rol
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("pedidos_list"))
        else:
            return redirect(url_for("mis_pedidos"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pwd = request.form.get("password") or ""

        u = mongo.db.usuarios.find_one({"email": email})
        if u and check_password_hash(u.get("password", ""), pwd):
            login_user(User(u))
            flash("Bienvenido.")

            # redirigimos según rol
            if User(u).is_admin:
                return redirect(url_for("pedidos_list"))
            else:
                return redirect(url_for("mis_pedidos"))

        flash("Credenciales inválidas.")

    # hide_navbar=True lo usaremos en base.html para ocultar el header
    return render_template("login.html", hide_navbar=True)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    # si ya está autenticado, no tiene sentido registrarse de nuevo
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        pwd = request.form.get("password") or ""
        pwd2 = request.form.get("password2") or ""
        ciudad = (request.form.get("ciudad") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()

        if not nombre or not email or not pwd:
            flash("Nombre, correo y contraseña son obligatorios.")
            return redirect(url_for("register"))

        if pwd != pwd2:
            flash("Las contraseñas no coinciden.")
            return redirect(url_for("register"))

        if mongo.db.usuarios.find_one({"email": email}):
            flash("Ya existe un usuario con ese correo.")
            return redirect(url_for("register"))

        # Creamos cliente
        cliente_doc = {
            "nombre": nombre,
            "email": email,
            "telefono": telefono or None,
            "ciudad": ciudad or None,
            "avatar_file_id": None,
            "activo": True,
            "creado_en": datetime.now(UTC)
        }
        res_cliente = mongo.db.clientes.insert_one(cliente_doc)
        cliente_id = res_cliente.inserted_id

        # Creamos usuario (rol user)
        user_doc = {
            "email": email,
            "password": generate_password_hash(pwd),
            "role": "user",
            "cliente_id": cliente_id,
            "creado_en": datetime.now(UTC)
        }
        res_user = mongo.db.usuarios.insert_one(user_doc)
        user_doc["_id"] = res_user.inserted_id

        login_user(User(user_doc))
        flash("Cuenta creada correctamente. ¡Bienvenido!")
        # usuario normal va directo a sus pedidos
        return redirect(url_for("mis_pedidos"))

    # GET
    return render_template("register.html", hide_navbar=True)

# ==========================
# HOME
# ==========================


@app.route("/")
def home():
    return render_template("index.html")

# ==========================
# CLIENTES (ADMIN)
# ==========================


@app.route("/clientes")
@role_required("admin")
def clientes_list():
    clientes = list(mongo.db.clientes.find())
    return render_template("clientes_list.html", clientes=clientes)


@app.route("/clientes/nuevo")
@role_required("admin")
def clientes_nuevo():
    return render_template("clientes_form.html", modo="crear", cliente={})


@app.route("/clientes", methods=["POST"])
@role_required("admin")
def clientes_crear():
    try:
        nombre = (request.form.get("nombre") or "").strip()
        if not nombre:
            flash("El nombre es obligatorio.")
            return redirect(url_for("clientes_nuevo"))

        file_avatar = request.files.get("avatar")
        avatar_id = save_to_gridfs(file_avatar)

        doc = {
            "nombre": nombre,
            "email": (request.form.get("email") or "").strip() or None,
            "telefono": (request.form.get("telefono") or "").strip() or None,
            "ciudad": (request.form.get("ciudad") or "").strip() or None,
            "avatar_file_id": avatar_id,  # <- GridFS
            "activo": True,
            "creado_en": datetime.now(UTC)
        }
        mongo.db.clientes.insert_one(doc)
        flash("Cliente creado.")
        return redirect(url_for("clientes_list"))
    except Exception as e:
        flash(f"Error al crear cliente: {e}")
        return redirect(url_for("clientes_nuevo"))


@app.route("/clientes/<id>/editar")
@role_required("admin")
def clientes_editar(id):
    cliente = mongo.db.clientes.find_one({"_id": ObjectId(id)})
    if not cliente:
        flash("Cliente no encontrado.")
        return redirect(url_for("clientes_list"))
    return render_template("clientes_form.html", modo="editar", cliente=cliente)


@app.route("/clientes/<id>/actualizar", methods=["POST"])
@role_required("admin")
def clientes_actualizar(id):
    try:
        nombre = (request.form.get("nombre") or "").strip()
        if not nombre:
            flash("El nombre es obligatorio.")
            return redirect(url_for("clientes_editar", id=id))

        existing = mongo.db.clientes.find_one({"_id": ObjectId(id)}, {"avatar_file_id": 1})
        avatar_id = existing.get("avatar_file_id") if existing else None
        file_avatar = request.files.get("avatar")
        new_id = save_to_gridfs(file_avatar)
        if new_id:
            avatar_id = new_id

        upd = {
            "nombre": nombre,
            "email": (request.form.get("email") or "").strip() or None,
            "telefono": (request.form.get("telefono") or "").strip() or None,
            "ciudad": (request.form.get("ciudad") or "").strip() or None,
            "activo": request.form.get("activo") == "on",
            "avatar_file_id": avatar_id
        }
        mongo.db.clientes.update_one({"_id": ObjectId(id)}, {"$set": upd})
        flash("Cliente actualizado.")
        return redirect(url_for("clientes_list"))
    except Exception as e:
        flash(f"Error al actualizar: {e}")
        return redirect(url_for("clientes_editar", id=id))


@app.route("/clientes/<id>/eliminar", methods=["POST"])
@role_required("admin")
def clientes_eliminar(id):
    try:
        mongo.db.clientes.delete_one({"_id": ObjectId(id)})
        flash("Cliente eliminado.")
    except Exception as e:
        flash(f"Error al eliminar: {e}")
    return redirect(url_for("clientes_list"))

# ==========================
# PRODUCTOS (ADMIN)
# ==========================


@app.route("/productos")
@role_required("admin")
def productos_list():
    productos = list(mongo.db.productos.find())
    return render_template("productos_list.html", productos=productos)


@app.route("/productos/nuevo")
@role_required("admin")
def productos_nuevo():
    return render_template("productos_form.html", modo="crear", producto={})


@app.route("/productos", methods=["POST"])
@role_required("admin")
def productos_crear():
    try:
        nombre = (request.form.get("nombre") or "").strip()
        categoria = (request.form.get("categoria") or "").strip()
        precio = float(request.form.get("precio") or 0)
        stock = int(request.form.get("stock") or 0)
        activo = request.form.get("activo") == "on"

        if not nombre:
            flash("El nombre es obligatorio.")
            return redirect(url_for("productos_nuevo"))

        # archivo de imagen (opcional) guardado como BinData en la colección
        file_img = request.files.get("imagen")
        image_data = None
        image_mime = None
        if file_img and file_img.filename:
            raw = file_img.read()               # bytes
            image_data = Binary(raw)            # BinData para Mongo
            image_mime = file_img.mimetype or "image/jpeg"

        doc = {
            "nombre": nombre,
            "categoria": categoria or "Sin categoría",
            "precio": precio,
            "stock": stock,
            "activo": activo,
            "creado_en": datetime.now(UTC),
        }
        if image_data:
            doc["image_data"] = image_data
            doc["image_mime"] = image_mime

        mongo.db.productos.insert_one(doc)
        flash("Producto creado correctamente.")
        return redirect(url_for("productos_list"))
    except Exception as e:
        print("ERROR productos_crear:", e)
        flash(f"Error al crear producto: {e}")
        return redirect(url_for("productos_nuevo"))


@app.route("/productos/<id>/editar")
@role_required("admin")
def productos_editar(id):
    prod = mongo.db.productos.find_one({"_id": ObjectId(id)})
    if not prod:
        flash("Producto no encontrado.")
        return redirect(url_for("productos_list"))
    return render_template("productos_form.html", modo="editar", producto=prod)


@app.route("/productos/<id>/actualizar", methods=["POST"])
@role_required("admin")
def productos_actualizar(id):
    try:
        nombre = (request.form.get("nombre") or "").strip()
        categoria = (request.form.get("categoria") or "").strip()
        precio = float(request.form.get("precio") or 0)
        stock = int(request.form.get("stock") or 0)
        activo = request.form.get("activo") == "on"

        if not nombre:
            flash("El nombre es obligatorio.")
            return redirect(url_for("productos_editar", id=id))

        # Traer producto actual para conservar imagen si no suben otra
        prod_actual = mongo.db.productos.find_one(
            {"_id": ObjectId(id)},
            {"image_data": 1, "image_mime": 1}
        )
        image_data = prod_actual.get("image_data") if prod_actual else None
        image_mime = prod_actual.get("image_mime") if prod_actual else None

        # si suben nueva imagen, sustituimos
        file_img = request.files.get("imagen")
        if file_img and file_img.filename:
            raw = file_img.read()
            image_data = Binary(raw)
            image_mime = file_img.mimetype or "image/jpeg"

        upd = {
            "nombre": nombre,
            "categoria": categoria or "Sin categoría",
            "precio": precio,
            "stock": stock,
            "activo": activo,
        }
        if image_data:
            upd["image_data"] = image_data
            upd["image_mime"] = image_mime

        mongo.db.productos.update_one({"_id": ObjectId(id)}, {"$set": upd})
        flash("Producto actualizado.")
        return redirect(url_for("productos_list"))
    except Exception as e:
        print("ERROR productos_actualizar:", e)
        flash(f"Error al actualizar producto: {e}")
        return redirect(url_for("productos_editar", id=id))


@app.route("/productos/<id>/eliminar", methods=["POST"])
@role_required("admin")
def productos_eliminar(id):
    try:
        mongo.db.productos.delete_one({"_id": ObjectId(id)})
        flash("Producto eliminado.")
    except Exception as e:
        flash(f"Error al eliminar: {e}")
    return redirect(url_for("productos_list"))


@app.route("/producto_imagen/<id>")
def producto_imagen(id):
    """
    Devuelve la imagen (BinData) asociada al producto.
    """
    prod = mongo.db.productos.find_one(
        {"_id": ObjectId(id)},
        {"image_data": 1, "image_mime": 1}
    )
    if not prod or not prod.get("image_data"):
        return "Sin imagen", 404

    return send_file(
        BytesIO(prod["image_data"]),
        mimetype=prod.get("image_mime", "image/jpeg")
    )

# ==========================
# REPORTES (ADMIN)
# ==========================


@app.route("/reportes")
@role_required("admin")
def reportes_ventas_por_dia_html():
    pipeline = [
        {"$match": {"estado": {"$ne": "CANCELADO"}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$fecha"}},
            "ventas_del_dia": {"$sum": "$total"},
            "pedidos": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    data = list(mongo.db.pedidos.aggregate(pipeline))
    return render_template("reportes.html", data=data)


@app.route("/reportes/top")
@role_required("admin")
def reportes_top_productos_html():
    pipeline = [
        {"$group": {"_id": "$id_producto", "unidades": {"$sum": "$cantidad"}, "ingreso": {"$sum": "$subtotal"}}},
        {"$lookup": {"from": "productos", "localField": "_id", "foreignField": "_id", "as": "prod"}},
        {"$unwind": "$prod"},
        {"$project": {"_id": 0, "producto": "$prod.nombre", "categoria": "$prod.categoria", "unidades": 1, "ingreso": 1}},
        {"$sort": {"unidades": -1}}
    ]
    data = list(mongo.db.detalle_pedido.aggregate(pipeline))
    return render_template("reportes_top.html", data=data)


# ---- PDF ventas por día
@app.route("/reportes/pdf")
@role_required("admin")
def reportes_pdf():
    pipeline = [
        {"$match": {"estado": {"$ne": "CANCELADO"}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$fecha"}},
            "ventas_del_dia": {"$sum": "$total"},
            "pedidos": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    data = list(mongo.db.pedidos.aggregate(pipeline))
    html = render_template("reportes_pdf.html", data=data, generado=datetime.now(UTC))
    pdf_io = BytesIO()
    pisa.CreatePDF(html, dest=pdf_io)
    pdf_io.seek(0)
    return send_file(pdf_io, mimetype="application/pdf", as_attachment=True, download_name="ventas_por_dia.pdf")

# ==========================
# PEDIDOS (ADMIN + USER)
# ==========================


@app.route("/pedidos")
@role_required("admin")
def pedidos_list():
    pipeline = [
        {"$sort": {"fecha": -1}},
        {"$addFields": {
            "id_cliente_fix": {
                "$cond": [
                    {"$eq": [{"$type": "$id_cliente"}, "string"]},
                    {"$toObjectId": "$id_cliente"},
                    "$id_cliente"
                ]
            }
        }},
        {"$lookup": {"from": "clientes", "localField": "id_cliente_fix", "foreignField": "_id", "as": "cli"}},
        {"$unwind": {"path": "$cli", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 1, "fecha": 1, "total": 1, "estado": 1, "metodo_pago": 1,
            "nombre_cliente": {"$ifNull": ["$cli.nombre", "—"]}
        }}
    ]
    pedidos = list(mongo.db.pedidos.aggregate(pipeline))
    for p in pedidos:
        p["_id"] = str(p["_id"])
    return render_template("pedidos_list.html", pedidos=pedidos)

# ==========================
# MIS PEDIDOS (USER)
# ==========================
@app.route("/mis-pedidos")
@login_required
def mis_pedidos():
    # Buscar el usuario actual en la colección usuarios
    u = mongo.db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    cliente_id = u.get("cliente_id") if u else None

    if not cliente_id:
        flash("Tu usuario no está asociado a un cliente. Habla con el administrador.")
        return redirect(url_for("pedidos_nuevo"))

    pipeline = [
        {"$match": {"id_cliente": cliente_id}},
        {"$sort": {"fecha": -1}},
        {"$project": {
            "_id": 1,
            "fecha": 1,
            "total": 1,
            "estado": 1,
            "metodo_pago": 1
        }}
    ]
    pedidos = list(mongo.db.pedidos.aggregate(pipeline))
    for p in pedidos:
        p["_id"] = str(p["_id"])

    return render_template("mis_pedidos.html", pedidos=pedidos)


# Página de pedido (para USER o ADMIN)
@app.route("/u/pedidos/nuevo")
@login_required
def pedidos_nuevo():
    if current_user.is_admin:
        clientes = list(mongo.db.clientes.find())
    else:
        # Usuario normal: solo su propio cliente
        clientes = []
        u = mongo.db.usuarios.find_one({"_id": ObjectId(current_user.id)})
        if u and u.get("cliente_id"):
            cli = mongo.db.clientes.find_one({"_id": u["cliente_id"]})
            if cli:
                clientes = [cli]

    productos = list(mongo.db.productos.find({"activo": True}))
    return render_template("pedidos_nuevo.html", clientes=clientes, productos=productos)


# Crear pedido con múltiples ítems
@app.route("/u/pedidos", methods=["POST"])
@login_required
def pedidos_crear():
    try:
        id_cliente = request.form.get("id_cliente")
        ids = request.form.getlist("id_producto[]") or request.form.getlist("id_producto")
        cants = request.form.getlist("cantidad[]") or request.form.getlist("cantidad")

        metodo_pago = request.form.get("metodo_pago", "EFECTIVO")
        if not id_cliente or not ids or not cants:
            flash("Faltan datos del pedido.")
            return redirect(url_for("pedidos_nuevo"))

        # Normaliza pares producto-cantidad
        items = []
        for pid, cant in zip(ids, cants):
            try:
                q = int(cant)
                if q > 0:
                    items.append((ObjectId(pid), q))
            except Exception:
                pass
        if not items:
            flash("No hay ítems válidos.")
            return redirect(url_for("pedidos_nuevo"))

        # Validar stock y calcular total
        total = 0.0
        detalles = []
        for pid, q in items:
            prod = mongo.db.productos.find_one({"_id": pid, "activo": True})
            if not prod:
                flash("Producto no encontrado o inactivo.")
                return redirect(url_for("pedidos_nuevo"))
            if int(prod.get("stock", 0)) < q:
                flash(f"Stock insuficiente para {prod['nombre']}. Disponible: {prod['stock']}")
                return redirect(url_for("pedidos_nuevo"))
            subtotal = float(prod["precio"]) * q
            total += subtotal
            detalles.append({
                "id_producto": prod["_id"],
                "nombre_producto": prod["nombre"],
                "cantidad": q,
                "precio_unit": float(prod["precio"]),
                "subtotal": subtotal
            })

        # Crear pedido
        pedido = {
            "id_cliente": ObjectId(id_cliente),
            "fecha": datetime.now(UTC),
            "total": total,
            "estado": "CREADO",
            "metodo_pago": metodo_pago,
            "creado_por": current_user.email
        }
        res = mongo.db.pedidos.insert_one(pedido)
        id_pedido = res.inserted_id

        # Insertar detalle + descontar stock
        for d in detalles:
            d["id_pedido"] = id_pedido
            mongo.db.detalle_pedido.insert_one(d)
            mongo.db.productos.update_one({"_id": d["id_producto"]}, {"$inc": {"stock": -int(d["cantidad"])}})

        flash("Pedido creado correctamente.")
        # admin: vuelve al listado; user: ver detalle
        if current_user.is_admin:
            return redirect(url_for("pedidos_list"))
        return redirect(url_for("pedido_detalle", id_pedido=str(id_pedido)))

    except Exception as e:
        flash(f"Error: {e}")
        return redirect(url_for("pedidos_nuevo"))


@app.route("/pedidos/<id_pedido>")
@login_required
def pedido_detalle(id_pedido):
    pedido = mongo.db.pedidos.find_one({"_id": ObjectId(id_pedido)})
    if not pedido:
        return "Pedido no encontrado", 404
    detalles = list(mongo.db.detalle_pedido.find({"id_pedido": ObjectId(id_pedido)}))
    cliente = mongo.db.clientes.find_one({"_id": pedido["id_cliente"]})
    return render_template("pedido_detalle.html", pedido=pedido, detalles=detalles, cliente=cliente)


# Cambiar estado (ADMIN)
@app.route("/pedidos/<id_pedido>/estado", methods=["POST"])
@role_required("admin")
def cambiar_estado_pedido(id_pedido):
    try:
        nuevo = (request.form.get("estado") or "").strip().upper()
        if nuevo not in ("CREADO", "PAGADO", "ENVIADO", "CANCELADO"):
            flash("Estado inválido.")
            return redirect(url_for("pedidos_list"))

        pedido = mongo.db.pedidos.find_one({"_id": ObjectId(id_pedido)})
        if not pedido:
            flash("Pedido no encontrado.")
            return redirect(url_for("pedidos_list"))

        estado_actual = (pedido.get("estado") or "CREADO").strip().upper()
        transiciones = {
            "CREADO": {"PAGADO", "ENVIADO", "CANCELADO"},
            "PAGADO": {"ENVIADO", "CANCELADO"},
            "ENVIADO": {"PAGADO"},
            "CANCELADO": set()
        }
        if nuevo not in transiciones.get(estado_actual, set()):
            flash(f"No se puede cambiar de {estado_actual} a {nuevo}.")
            return redirect(url_for("pedidos_list"))

        if nuevo == "CANCELADO" and estado_actual != "CANCELADO":
            detalles = list(mongo.db.detalle_pedido.find({"id_pedido": ObjectId(id_pedido)}))
            for d in detalles:
                mongo.db.productos.update_one({"_id": d["id_producto"]}, {"$inc": {"stock": int(d["cantidad"])}})

        mongo.db.pedidos.update_one({"_id": ObjectId(id_pedido)}, {"$set": {"estado": nuevo}})
        mongo.db.auditoria.insert_one({
            "entidad": "pedido", "entidad_id": ObjectId(id_pedido),
            "accion": "CAMBIAR_ESTADO",
            "antes": {"estado": estado_actual},
            "despues": {"estado": nuevo},
            "usuario_app": current_user.email,
            "fecha": datetime.now(UTC)
        })
        flash(f"Estado actualizado de {estado_actual} a {nuevo}.")
        return redirect(url_for("pedidos_list"))
    except Exception as e:
        flash(f"Error al cambiar estado: {e}")
        return redirect(url_for("pedidos_list"))

# ==========================
# FACTURA PDF (ADMIN + USER)
# ==========================


@app.route("/factura/<id_pedido>.pdf")
@login_required
def factura_pdf(id_pedido):
    pedido = mongo.db.pedidos.find_one({"_id": ObjectId(id_pedido)})
    if not pedido:
        return "Pedido no encontrado", 404
    cliente = mongo.db.clientes.find_one({"_id": pedido["id_cliente"]})
    detalles = list(mongo.db.detalle_pedido.find({"id_pedido": ObjectId(id_pedido)}))

    html = render_template("factura.html", pedido=pedido, cliente=cliente,
                           detalles=detalles, generado=datetime.now(UTC))
    pdf_io = BytesIO()
    pisa.CreatePDF(html, dest=pdf_io)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"factura_{id_pedido}.pdf"
    )

# ==========================
# HEALTH CHECK
# ==========================
try:
    mongo.cx.admin.command("ping")
    print("✅ MongoDB listo (ping ok).")
except Exception as e:
    print("❌ MongoDB no disponible:", repr(e))

# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
