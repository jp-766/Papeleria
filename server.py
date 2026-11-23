import os
import json
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

app.config['MYSQL_HOST'] = os.getenv('DB_HOST')
app.config['MYSQL_USER'] = os.getenv('DB_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('DB_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('DB_NAME')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

csrf = CSRFProtect(app)

mysql = MySQL(app)

# Verificar si el usuario tiene el rol permitido
def requiere_rol(*roles_permitidos): 
    if 'id_usuario' not in session:
        flash('Inicia sesión para continuar', 'warning')
        return False

    if session.get('id_rol') not in roles_permitidos:
        flash('No tienes permisos para realizar esta acción', 'danger')
        return False

    return True

@app.route('/')
def inicio():
    return render_template('index.html')

# Iniciar sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('lCorreo', '').strip()
        password = request.form.get('lPass', '')

        try:
            cursor = mysql.connection.cursor()
            cursor.execute("""SELECT id_usuario, nombre, apellidos, email, pass_hash, id_rol FROM usuarios WHERE email = %s""",(correo,)) 
            usuario = cursor.fetchone()
            cursor.close()

            if usuario and check_password_hash(usuario['pass_hash'], password):
                session['id_usuario'] = usuario['id_usuario']
                session['nombre'] = usuario['nombre']
                session['id_rol'] = usuario['id_rol']

                flash('Bienvenido a Papelia', 'success')
                return redirect(url_for('perfil'))

            flash('Correo o contraseña incorrectos', 'danger')

        except Exception as error:
            print('Error al iniciar sesión:', error)
            flash('No fue posible iniciar sesión', 'danger')

    return render_template('login.html')


# Registro de usuarios
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip()
        password = request.form.get('password', '')
        confirmar = request.form.get('confirmar_password', '')

        if not nombre or not correo or not password:
            flash('Completa todos los campos', 'warning')
            return redirect(url_for('registro'))

        if password != confirmar:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('registro'))

        if len(password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres', 'warning')
            return redirect(url_for('registro'))

        try:
            cursor = mysql.connection.cursor()

            cursor.execute(
                'SELECT id_usuario FROM usuarios WHERE email = %s',
                (correo,)
            )

            if cursor.fetchone():
                cursor.close()
                flash('Este correo ya está registrado', 'warning')
                return redirect(url_for('registro'))

            cursor.execute("SELECT id_rol FROM roles WHERE nombre_rol = %s", ('Cliente',))
            rol = cursor.fetchone()

            if not rol:
                cursor.close()
                flash('No se encontró el rol Cliente', 'danger')
                return redirect(url_for('registro'))

            password_hash = generate_password_hash(password)

            cursor.execute("""INSERT INTO usuarios (nombre, apellidos, email, pass_hash, id_rol) VALUES (%s, %s, %s, %s, %s)""", 
                           (nombre, '', correo, password_hash, rol['id_rol']))

            mysql.connection.commit()
            cursor.close()

            flash('Registro realizado correctamente', 'success')
            return redirect(url_for('login'))

        except Exception as error:
            mysql.connection.rollback()
            print('Error en el registro:', error)
            flash('Ocurrió un error al registrar el usuario', 'danger')

    return render_template('formulario.html')


# Perfil del usuario
@app.route('/perfil')
def perfil():
    if 'id_usuario' not in session:
        flash('Inicia sesión para acceder al perfil', 'warning')
        return redirect(url_for('login'))

    try:
        cursor = mysql.connection.cursor()
        cursor.execute("""SELECT u.id_usuario, u.nombre, u.apellidos, u.email AS correo, r.nombre_rol AS rol FROM usuarios u 
            INNER JOIN roles r ON u.id_rol = r.id_rol WHERE u.id_usuario = %s""", (session['id_usuario'],))
        usuario = cursor.fetchone()
        cursor.close()

        if not usuario:
            session.clear()
            flash('No se encontró el usuario', 'danger')
            return redirect(url_for('login'))

        return render_template('perfil.html', usuario=usuario)

    except Exception as error:
        print('Error al cargar el perfil:', error)
        flash('No fue posible cargar el perfil', 'danger')
        return redirect(url_for('inicio'))


# Cerrar sesión
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('inicio'))


# Catálogo de productos
@app.route('/catalogo')
def catalogo():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("""SELECT p.id_producto, p.nombre, p.precio, p.stock, c.nombre AS categoria FROM productos p 
            INNER JOIN categorias c ON p.id_categoria = c.id_categoria ORDER BY p.nombre""")
        productos = cursor.fetchall()
        cursor.close()

        return render_template('catalogo.html', productos=productos)

    except Exception as error:
        print('Error al cargar el catálogo:', error)
        flash('No fue posible cargar el catálogo', 'danger')
        return redirect(url_for('inicio'))

# Punto de venta
@app.route('/ventas')
def ventas():
    if not requiere_rol(1, 2):
        return redirect(url_for('inicio'))

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""SELECT id_producto, nombre, precio, stock FROM productos 
            WHERE stock > 0 ORDER BY nombre""")

        productos = cursor.fetchall()
        cursor.close()

        return render_template('ventas.html', productos=productos)

    except Exception as error:
        print('Error al cargar el punto de venta:', error)
        flash('No fue posible cargar el punto de venta', 'danger')
        return redirect(url_for('inicio'))
        

# Inventario: registrar productos
@app.route('/inventario', methods=['GET', 'POST'])
def inventario():
    if not requiere_rol(1, 2):
        return redirect(url_for('inicio'))

    try:
        cursor = mysql.connection.cursor()

        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            precio = request.form.get('precio', '').strip()
            stock = request.form.get('stock', '').strip()
            id_categoria = request.form.get('id_categoria', '').strip()

            if not nombre or not precio or not stock or not id_categoria:
                flash('Completa todos los campos', 'warning')
            else:
                try:
                    precio = float(precio)
                    stock = int(stock)
                    id_categoria = int(id_categoria)

                    if precio <= 0 or stock < 0:
                        raise ValueError('Valores inválidos')

                    if len(nombre) > 100:
                        raise ValueError('Nombre demasiado largo')

                    cursor.execute("SELECT id_categoria FROM categorias WHERE id_categoria = %s", 
                                   (id_categoria,))

                    if not cursor.fetchone():
                        flash('La categoría seleccionada no existe', 'danger')
                    else:
                        cursor.execute("""INSERT INTO productos (nombre, precio, stock, id_categoria)
                            VALUES (%s, %s, %s, %s)""", (nombre, precio, stock, id_categoria))

                        mysql.connection.commit()
                        flash('Producto registrado correctamente', 'success')

                except (ValueError, TypeError):
                    flash('Verifica que el precio, stock y categoría sean válidos', 'danger')

        cursor.execute("""SELECT id_categoria, nombre FROM categorias ORDER BY nombre""")
        categorias = cursor.fetchall()

        cursor.execute("""SELECT p.id_producto, p.nombre, p.precio, p.stock, c.nombre AS categoria 
            FROM productos p INNER JOIN categorias c ON p.id_categoria = c.id_categoria ORDER BY p.nombre""")
        productos = cursor.fetchall()

        cursor.close()

        return render_template('inventario.html', categorias=categorias, productos=productos)

    except Exception as error:
        mysql.connection.rollback()
        print('Error en inventario:', error)
        flash('No fue posible procesar el inventario', 'danger')
        return redirect(url_for('inicio'))

# Editar los productos del inventario
@app.route('/editar_producto/<int:id_producto>', methods=['GET', 'POST'])
def editar_producto(id_producto):

    if not requiere_rol(1, 2):
        return redirect(url_for('inicio'))

    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""SELECT id_producto, nombre, precio, stock, id_categoria
            FROM productos WHERE id_producto = %s""", (id_producto,))

        producto = cursor.fetchone()

        if not producto:
            flash('El producto no existe', 'danger')
            return redirect(url_for('inventario'))
        
        if request.method == 'POST':

            nombre = request.form.get('nombre', '').strip()
            precio = request.form.get('precio', '').strip()
            stock = request.form.get('stock', '').strip()
            id_categoria = request.form.get('id_categoria', '').strip()

            if not nombre or not precio or not stock or not id_categoria:
                flash('Completa todos los campos', 'warning')

            else:
                try:
                    precio = float(precio)
                    stock = int(stock)
                    id_categoria = int(id_categoria)

                    if precio <= 0 or stock < 0 or len(nombre) > 100:
                        raise ValueError

                    cursor.execute("""SELECT id_categoria FROM categorias WHERE id_categoria = %s""", (id_categoria,))

                    if not cursor.fetchone():
                        flash('La categoría seleccionada no existe', 'danger')

                    else:
                        cursor.execute("""UPDATE productos SET nombre = %s, precio = %s, stock = %s, 
                            id_categoria = %s WHERE id_producto = %s""", 
                            (nombre, precio, stock, id_categoria, id_producto))

                        mysql.connection.commit()
                        flash('Producto actualizado correctamente', 'success')
                        return redirect(url_for('inventario'))

                except (ValueError, TypeError):
                    flash('Verifica que los datos sean válidos', 'danger')

        cursor.execute("""SELECT id_categoria, nombre FROM categorias ORDER BY nombre""")

        categorias = cursor.fetchall()

        return render_template('editar_producto.html', producto=producto,categorias=categorias)

    except Exception as error:
        mysql.connection.rollback()
        print('Error al editar producto:', error)
        flash('No fue posible editar el producto', 'danger')
        return redirect(url_for('inventario'))

    finally:
        if cursor:
            cursor.close()

#Eliminar productos del inventario
@app.route('/eliminar_producto/<int:id_producto>', methods={'POST'})
def eliminar_producto(id_producto):

    if not requiere_rol(1):
        return redirect(url_for('inicio'))

    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""SELECT id_producto FROM productos WHERE id_producto = %s""", (id_producto,))

        producto = cursor.fetchone()

        if not producto:
            flash('El producto no existe', 'danger')
            return redirect(url_for('inventario'))

        cursor.execute("""SELECT 1 FROM detalle_venta WHERE id_producto = %s LIMIT 1""", (id_producto,))     

        if cursor.fetchone():
            flash('No se puede eliminar: el producto está relacionado con una venta', 'warning')
            return redirect(url_for('inventario'))

        cursor.execute("DELETE FROM productos WHERE id_producto = %s", (id_producto,))

        mysql.connection.commit()
        flash('Producto eliminado correctamente', 'success')
        return redirect(url_for('inventario'))

    except Exception as error:
        mysql.connection.rollback()
        print('Error al eliminar producto:', error)

        flash('No fue posible eliminar el producto', 'danger')
        return redirect(url_for('inventario'))

    finally:
        if cursor:
            cursor.close()

# Ejecutar el servidor
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
