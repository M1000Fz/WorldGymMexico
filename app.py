from flask import Flask, render_template, request, redirect, flash, session, Response
from functools import wraps
import psycopg2
import requests
import csv
import io

app = Flask(__name__)
app.secret_key = 'clave_secreta_world_gym' 
DATABASE_URL = "postgresql://neondb_owner:npg_cpbBGC6hKV8x@ep-twilight-unit-aejcmcmn-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

ADMIN_USER = "admin"
ADMIN_PASS = "m1000"

def obtener_conexion():
    return psycopg2.connect(DATABASE_URL)

# --- PROTECCIÓN DE RUTAS ADMIN ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Acceso denegado. Se requiere credencial.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# --- ACCESO UNIFICADO (RUTA PRINCIPAL) ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        credencial_1 = request.form['usuario_correo'].strip()
        credencial_2 = request.form['password_codigo'].strip()
        
        # 1. Verificación de Administrador
        if credencial_1 == ADMIN_USER and credencial_2 == ADMIN_PASS:
            session['admin_logged_in'] = True
            return redirect('/panel_admin')
            
        # 2. Verificación de Cliente
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        consulta = """
            SELECT nombre, apellido, tipo_membresia, 
            (CASE 
                WHEN tipo_membresia = 'Mensual' THEN fecha_registro + interval '1 month'
                WHEN tipo_membresia = 'Trimestral' THEN fecha_registro + interval '3 months'
                WHEN tipo_membresia = 'Anual' THEN fecha_registro + interval '1 year'
                ELSE fecha_registro + interval '100 years'
            END)::date - CURRENT_DATE AS dias_restantes
            FROM clientes WHERE email = %s AND codigo_acceso = %s;
        """
        cursor.execute(consulta, (credencial_1, credencial_2))
        cliente = cursor.fetchone()
        cursor.close()
        conexion.close()
        
        if cliente:
            session['cliente_logged_in'] = True
            session['cliente_datos'] = {
                'nombre': f"{cliente[0]} {cliente[1]}",
                'membresia': cliente[2],
                'dias': cliente[3]
            }
            return redirect('/mi_portal')
        else:
            flash('Datos incorrectos. Verifica tu usuario/correo y contraseña.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión finalizada de manera segura.', 'success')
    return redirect('/')

# --- RUTAS DEL ADMINISTRADOR ---
@app.route('/panel_admin')
@login_required
def index():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    
    consulta_clientes = """
    SELECT id, nombre, apellido, email, telefono, tipo_membresia,
        (CASE 
            WHEN tipo_membresia = 'Mensual' THEN fecha_registro + interval '1 month'
            WHEN tipo_membresia = 'Trimestral' THEN fecha_registro + interval '3 months'
            WHEN tipo_membresia = 'Anual' THEN fecha_registro + interval '1 year'
            WHEN tipo_membresia = 'VIP' THEN fecha_registro + interval '100 years'
            ELSE fecha_registro + interval '1 month'
        END)::date - CURRENT_DATE AS dias_restantes
    FROM clientes ORDER BY id ASC;
    """
    cursor.execute(consulta_clientes)
    clientes = cursor.fetchall()
    
    cursor.execute("SELECT tipo_membresia, COUNT(*) FROM clientes GROUP BY tipo_membresia;")
    resultados_stats = cursor.fetchall()
    stats = {'Mensual': 0, 'Trimestral': 0, 'Anual': 0, 'VIP': 0}
    for fila in resultados_stats:
        if fila[0] in stats:
            stats[fila[0]] = fila[1]
            
    cursor.close()
    conexion.close()
    return render_template('index.html', clientes=clientes, stats=stats)

@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    email = request.form['email']
    telefono = request.form['telefono']
    membresia = request.form['membresia']

    codigo_promo = "GYM-NUEVO"
    try:
        respuesta = requests.get("https://random-word-api.herokuapp.com/word?length=5")
        if respuesta.status_code == 200:
            palabra = respuesta.json()[0].upper()
            codigo_promo = f"{palabra}-{membresia[:3].upper()}"
    except:
        pass 

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        consulta = "INSERT INTO clientes (nombre, apellido, email, telefono, tipo_membresia, codigo_acceso) VALUES (%s, %s, %s, %s, %s, %s);"
        cursor.execute(consulta, (nombre, apellido, email, telefono, membresia, codigo_promo))
        conexion.commit()
        flash(f'Cliente registrado. Código de Acceso: {codigo_promo}', 'success')
    except psycopg2.IntegrityError:
        conexion.rollback()
        flash('Ese correo electrónico ya está registrado.', 'error')
    finally:
        cursor.close()
        conexion.close()
    return redirect('/panel_admin')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        email = request.form['email']
        telefono = request.form['telefono']
        membresia = request.form['membresia']
        try:
            consulta = "UPDATE clientes SET nombre = %s, apellido = %s, email = %s, telefono = %s, tipo_membresia = %s WHERE id = %s;"
            cursor.execute(consulta, (nombre, apellido, email, telefono, membresia, id))
            conexion.commit()
            flash('Datos actualizados correctamente.', 'success')
        except psycopg2.IntegrityError:
            conexion.rollback()
            flash('El nuevo correo ya pertenece a otra persona.', 'error')
        cursor.close()
        conexion.close()
        return redirect('/panel_admin')
    else:
        cursor.execute("SELECT id, nombre, apellido, email, telefono, tipo_membresia FROM clientes WHERE id = %s;", (id,))
        cliente = cursor.fetchone()
        cursor.close()
        conexion.close()
        return render_template('editar.html', cliente=cliente)

@app.route('/borrar/<int:id>')
@login_required
def borrar(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = %s;", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('El cliente ha sido purgado del sistema.', 'success')
    return redirect('/panel_admin')

@app.route('/exportar')
@login_required
def exportar_csv():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, apellido, email, telefono, tipo_membresia FROM clientes ORDER BY id ASC;")
    clientes = cursor.fetchall()
    cursor.close()
    conexion.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nombre', 'Apellido', 'Email', 'Telefono', 'Plan'])
    for c in clientes:
        writer.writerow(c)
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=Reporte_Gym.csv"})

@app.route('/notificar_vencimientos')
@login_required
def notificar_vencimientos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    consulta = """
    SELECT email FROM clientes 
    WHERE (CASE 
        WHEN tipo_membresia = 'Mensual' THEN fecha_registro + interval '1 month'
        WHEN tipo_membresia = 'Trimestral' THEN fecha_registro + interval '3 months'
        WHEN tipo_membresia = 'Anual' THEN fecha_registro + interval '1 year'
        ELSE fecha_registro + interval '100 years'
    END)::date - CURRENT_DATE <= 5 AND email IS NOT NULL AND tipo_membresia != 'VIP';
    """
    cursor.execute(consulta)
    correos = cursor.fetchall()
    cursor.close()
    conexion.close()
    if len(correos) > 0:
        flash(f'Alertas simuladas para {len(correos)} clientes en riesgo.', 'success')
    else:
        flash('Ningún cliente requiere recordatorio.', 'success')
    return redirect('/panel_admin')

# --- RUTAS DEL PORTAL CLIENTE ---
@app.route('/mi_portal')
def mi_portal():
    if 'cliente_logged_in' not in session:
        return redirect('/')
    datos = session.get('cliente_datos')
    return render_template('portal_cliente.html', vista='dashboard', datos=datos)

if __name__ == '__main__':
    app.run(debug=True)