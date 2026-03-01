## MongoBites – Sistema de Gestión de Pedidos con Flask + MongoDB

MongoBites es una aplicación web desarrollada con **Flask** y **MongoDB (Atlas)** para gestionar clientes, productos y pedidos de un restaurante / tienda de comida rápida.  
Incluye autenticación con roles, generación de facturas en PDF, reportes de ventas y manejo de imágenes (avatares y fotos de productos) en la base de datos.

---

## 🧩 Funcionalidades principales

### Autenticación y roles

- Login de usuarios con **Flask-Login**.
- Usuario **admin** creado automáticamente:
  - Email: `admin@demo`
  - Password: `admin123`
- Registro de usuarios normales:
  - Se crea un documento en `usuarios` con rol `user`.
  - Se crea su documento asociado en `clientes`.
- Roles:
  - **Admin**:
    - CRUD de clientes.
    - CRUD de productos.
    - Ver y gestionar todos los pedidos.
    - Cambiar estado de pedidos.
    - Ver reportes y descargar PDFs.
  - **User**:
    - Registrarse e iniciar sesión.
    - Crear pedidos con múltiples productos.
    - Ver sus propios pedidos.
    - Descargar factura PDF de sus pedidos.

---

## 📦 Módulos principales

### 1. Clientes

Colección: `clientes`

- Campos:
  - `nombre`, `email`, `telefono`, `ciudad`
  - `avatar_file_id` (GridFS) – opcional
  - `activo`, `creado_en`
- Funciones:
  - Listar clientes (solo admin).
  - Crear/editar/eliminar clientes.
  - Subir avatar opcional (almacenado en GridFS).

### 2. Productos

Colección: `productos`

- Campos:
  - `nombre`, `categoria`, `precio`, `stock`, `activo`, `creado_en`
  - `image_data` (BinData) + `image_mime` – imagen almacenada directamente en Mongo.
- Funciones:
  - Listar productos (solo admin).
  - Crear/editar/eliminar productos.
  - Subir imagen de producto.
  - Mostrar la imagen desde ruta `/producto_imagen/<id>`.

### 3. Pedidos

Colecciones: `pedidos` y `detalle_pedido`

- `pedidos`:
  - `id_cliente` (ObjectId de clientes)
  - `fecha`, `total`, `estado` (`CREADO`, `PAGADO`, `ENVIADO`, `CANCELADO`)
  - `metodo_pago`
  - `creado_por` (email del usuario app)
- `detalle_pedido`:
  - `id_pedido`, `id_producto`
  - `nombre_producto`, `cantidad`, `precio_unit`, `subtotal`
- Funciones:
  - Admin:
    - Ver listado de pedidos con nombre de cliente y estado.
    - Cambiar estado con transiciones válidas.
  - User:
    - Crear pedidos desde `/u/pedidos/nuevo`.
    - Ver detalle del pedido.
    - Consultar sus propios pedidos (vista “Mis pedidos”).

---

## 📊 Reportes

Colección usada: `pedidos` y `detalle_pedido`.

### 1. Ventas por día

Ruta: `/reportes` (admin)

- Agrupa pedidos por día (excepto cancelados).
- Muestra:
  - Fecha
  - Total vendido
  - Número de pedidos del día

PDF: `/reportes/pdf`  
Genera un PDF con tabla de ventas por día.

### 2. Top productos

Ruta: `/reportes/top` (admin)

- Agrupa por producto (`detalle_pedido` + lookup a `productos`).
- Muestra:
  - Nombre de producto
  - Categoría
  - Unidades vendidas
  - Ingreso total

---

## 🧾 Facturas en PDF

Ruta: `/factura/<id_pedido>.pdf` (admin + user autenticado)

- Genera una factura PDF para el pedido seleccionado.
- Incluye:
  - Datos del cliente.
  - Fecha, método de pago, estado.
  - Detalle de productos (cantidad, precio, subtotal).
  - Total a pagar.
  - Información del comercio (MongoBites + datos fijos).
- Implementado con **xhtml2pdf (pisa)** a partir de una plantilla HTML (`factura.html`).

---

## 🖼️ Manejo de imágenes

### Avatares de clientes (GridFS)

- Subidos desde el formulario de clientes.
- Guardados en **GridFS** (`fs`).
- Campo en `clientes`: `avatar_file_id`.
- Servidos vía ruta `/media/<file_id>`:
  - Lee desde GridFS, detecta `content_type` y retorna con `send_file`.

### Imágenes de productos (BinData en documento)

- Subidas desde el formulario de productos.
- Guardadas como:
  - `image_data`: `bson.binary.Binary`
  - `image_mime`: tipo MIME (`image/jpeg`, `image/png`, etc.).
- Servidas vía `/producto_imagen/<id>` usando `send_file` con `BytesIO`.

---

## 🏗️ Arquitectura y diseño

### Stack

- **Backend:** Flask (Python)
- **Base de datos:** MongoDB Atlas
- **ORM/Driver:** Flask-PyMongo / PyMongo
- **Templates:** Jinja2 + Bootstrap 5
- **Auth:** Flask-Login
- **PDF:** xhtml2pdf (pisa)
- **Storage binario:** GridFS + BinData

### Patrón general

- Arquitectura MVC ligera:
  - Rutas (controladores) en `app.py`.
  - Vistas: templates Jinja2 (`templates/*.html`).
  - Modelo: colecciones de MongoDB (clientes, productos, usuarios, pedidos, detalle_pedido).
- División por roles:
  - Rutas admin protegidas con `@role_required("admin")`.
  - Rutas de usuario con `@login_required`.

---

## 🔐 Seguridad

- Contraseñas con `werkzeug.security.generate_password_hash`.
- Login verificado con `check_password_hash`.
- Sesiones y control de acceso con `Flask-Login`.
- Rutas protegidas:
  - `@login_required` para pedido, factura, etc.
  - `@role_required("admin")` para administración y reportes.
- Conexión a MongoDB Atlas sobre TLS usando `certifi` para CA.

---

## 🗂️ Diagramas UML

La documentación en PDF incluye un anexo UML con:

- **Diagrama de casos de uso** (Admin vs Usuario, casos CU1–CU9).
- **Diagrama de clases simplificado:**
  - Usuario, Cliente, Producto, Pedido, DetallePedido.
  - Relaciones 1–1, 1–*, etc.
- **Diagrama de despliegue:**
  - Navegador web
  - Servidor Flask
  - MongoDB Atlas (DB + GridFS)

Consulta el archivo:  
`MongoBites_Documentacion_Tecnica_UML.pdf`

---

## ⚙️ Configuración y ejecución

### Requisitos

- Python 3.11+ (en tu caso 3.13)
- MongoDB Atlas (URI en `.env`)
- Paquetes Python:
  - `flask`
  - `flask_pymongo`
  - `python-dotenv`
  - `flask-login`
  - `werkzeug`
  - `xhtml2pdf`
  - `pymongo`
  - `gridfs`
  - `certifi`

Instalar dependencias (ejemplo):

```bash
pip install flask flask_pymongo python-dotenv flask-login xhtml2pdf pymongo gridfs certifi
]
