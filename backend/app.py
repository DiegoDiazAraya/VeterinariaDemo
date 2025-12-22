from flask import Flask, request, jsonify, session
from flask_cors import CORS
import json
import os
import unicodedata
from datetime import datetime
from functools import wraps

# Import del Blueprint bot_api (compatible con local y producción)
try:
    from .bot_api import bot_api  # Cuando se ejecuta como paquete (gunicorn, imports relativos)
except ImportError:
    from bot_api import bot_api  # Cuando se ejecuta directamente (py backend/app.py)

app = Flask(__name__)
app.secret_key = 'betterdoctor_secret_key_2024'
CORS(app, supports_credentials=True)

app.register_blueprint(bot_api)

# ==================== FUNCIONES DE CARGA DE DATOS ====================

def cargar_datos():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'data_simulada.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def cargar_usuarios():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'users.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def cargar_inventario():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'inventario.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_inventario(inventario):
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'inventario.json')
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        json.dump(inventario, f, ensure_ascii=False, indent=2)

def cargar_consultas():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'consultas.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_consultas(consultas):
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'consultas.json')
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        json.dump(consultas, f, ensure_ascii=False, indent=2)

def cargar_pacientes():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'pacientes.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_pacientes(pacientes):
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'pacientes.json')
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        json.dump(pacientes, f, ensure_ascii=False, indent=2)

def cargar_razas():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'razas.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

def cargar_diagnosticos_completos():
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'diagnosticos_veterinarios.json')
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==================== FUNCIONES DE UTILIDAD ====================

def normalizar_texto(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto

def calcular_coincidencia(sintomas_entrada, sintomas_diagnostico):
    """
    Calcula la coincidencia entre síntomas de entrada y síntomas del diagnóstico.
    
    Ponderación:
    - Coincidencia exacta: 1.0 punto
    - Sintoma contenido en el otro: 0.8 puntos
    - Palabras clave coincidentes (mínimo 2): 0.5 puntos
    - Una sola palabra común: 0.2 puntos (para evitar falsos positivos)
    """
    sintomas_entrada_norm = [normalizar_texto(s) for s in sintomas_entrada]
    sintomas_diag_norm = [normalizar_texto(s) for s in sintomas_diagnostico]
    
    coincidencias = 0
    sintomas_coincidentes = []
    
    for sintoma_entrada in sintomas_entrada_norm:
        mejor_match = 0
        mejor_sintoma_idx = -1
        
        for idx, sintoma_diag in enumerate(sintomas_diag_norm):
            puntuacion = 0
            
            # Coincidencia exacta (máxima puntuación)
            if sintoma_entrada == sintoma_diag:
                puntuacion = 1.0
            # El síntoma de entrada está contenido en el del diagnóstico
            elif sintoma_entrada in sintoma_diag:
                puntuacion = 0.9
            # El síntoma del diagnóstico está contenido en el de entrada
            elif sintoma_diag in sintoma_entrada:
                puntuacion = 0.85
            else:
                # Comparar palabras individuales
                palabras_entrada = set(sintoma_entrada.split())
                palabras_diag = set(sintoma_diag.split())
                palabras_comunes = palabras_entrada & palabras_diag
                
                # Excluir palabras muy comunes que generan falsos positivos
                palabras_excluidas = {'de', 'la', 'el', 'en', 'los', 'las', 'un', 'una', 'por', 'con', 'del'}
                palabras_comunes = palabras_comunes - palabras_excluidas
                
                if len(palabras_comunes) >= 2:
                    puntuacion = 0.6
                elif len(palabras_comunes) == 1:
                    # Solo dar puntuación si la palabra es significativa (más de 4 letras)
                    palabra = list(palabras_comunes)[0]
                    if len(palabra) > 4:
                        puntuacion = 0.3
            
            if puntuacion > mejor_match:
                mejor_match = puntuacion
                mejor_sintoma_idx = idx
        
        if mejor_match > 0 and mejor_sintoma_idx >= 0:
            coincidencias += mejor_match
            if sintomas_diagnostico[mejor_sintoma_idx] not in sintomas_coincidentes:
                sintomas_coincidentes.append(sintomas_diagnostico[mejor_sintoma_idx])
    
    # El porcentaje se calcula sobre el total de síntomas de entrada
    porcentaje = (coincidencias / len(sintomas_entrada)) * 100 if len(sintomas_entrada) > 0 else 0
    return porcentaje, sintomas_coincidentes

def generar_ticket():
    data = cargar_consultas()
    data['ultimo_ticket'] = data.get('ultimo_ticket', 0) + 1
    numero = data['ultimo_ticket']
    guardar_consultas(data)
    return f"BD-{datetime.now().year}-{str(numero).zfill(4)}"

def calcular_edad(fecha_nacimiento):
    """Calcula la edad a partir de la fecha de nacimiento."""
    if not fecha_nacimiento:
        return ""
    try:
        if isinstance(fecha_nacimiento, str):
            nacimiento = datetime.strptime(fecha_nacimiento, '%Y-%m-%d')
        else:
            nacimiento = fecha_nacimiento
        
        hoy = datetime.now()
        años = hoy.year - nacimiento.year
        meses = hoy.month - nacimiento.month
        
        if hoy.day < nacimiento.day:
            meses -= 1
        if meses < 0:
            años -= 1
            meses += 12
        
        if años >= 1:
            if meses > 0:
                return f"{años} año{'s' if años > 1 else ''} y {meses} mes{'es' if meses > 1 else ''}"
            return f"{años} año{'s' if años > 1 else ''}"
        elif meses >= 1:
            return f"{meses} mes{'es' if meses > 1 else ''}"
        else:
            dias = (hoy - nacimiento).days
            return f"{dias} día{'s' if dias > 1 else ''}"
    except:
        return ""

# ==================== AUTENTICACIÓN ====================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = data.get('usuario', '')
    password = data.get('password', '')
    
    if not usuario or not password:
        return jsonify({'exito': False, 'mensaje': 'Usuario y contraseña son requeridos'}), 400
    
    usuarios = cargar_usuarios()
    
    for user in usuarios:
        if user['usuario'] == usuario and user['password'] == password:
            if not user.get('activo', True):
                return jsonify({'exito': False, 'mensaje': 'Usuario desactivado'}), 401
            
            session['user_id'] = user['id']
            session['usuario'] = user['usuario']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            
            return jsonify({
                'exito': True,
                'mensaje': 'Inicio de sesión exitoso',
                'usuario': {
                    'id': user['id'],
                    'usuario': user['usuario'],
                    'nombre': user['nombre'],
                    'rol': user['rol'],
                    'email': user.get('email', ''),
                    'especialidad': user.get('especialidad', ''),
                    'departamento': user.get('departamento', '')
                }
            })
    
    return jsonify({'exito': False, 'mensaje': 'Usuario o contraseña incorrectos'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'exito': True, 'mensaje': 'Sesión cerrada correctamente'})

@app.route('/api/session', methods=['GET'])
def check_session():
    if 'user_id' in session:
        return jsonify({
            'autenticado': True,
            'usuario': {
                'id': session.get('user_id'),
                'usuario': session.get('usuario'),
                'nombre': session.get('nombre'),
                'rol': session.get('rol')
            }
        })
    return jsonify({'autenticado': False})

# ==================== GESTIÓN DE CONSULTAS ====================

@app.route('/api/consultas', methods=['GET'])
def obtener_consultas():
    """Obtiene las consultas según filtros."""
    estado = request.args.get('estado', None)
    data = cargar_consultas()
    consultas = data.get('consultas', [])
    
    if estado:
        consultas = [c for c in consultas if c['estado'] == estado]
    
    # Ordenar por fecha más reciente
    consultas.sort(key=lambda x: x.get('fecha_registro', ''), reverse=True)
    
    return jsonify({
        'exito': True,
        'consultas': consultas,
        'total': len(consultas)
    })

@app.route('/api/consultas/todas', methods=['GET'])
def todas_las_consultas():
    """Obtiene todas las consultas."""
    data = cargar_consultas()
    consultas = data.get('consultas', [])
    # Ordenar por fecha más reciente
    consultas_ordenadas = sorted(consultas, key=lambda x: x.get('fecha_registro', ''), reverse=True)
    return jsonify({
        'exito': True,
        'consultas': consultas_ordenadas,
        'total': len(consultas_ordenadas)
    })

@app.route('/api/consultas/pendientes', methods=['GET'])
def consultas_pendientes():
    """Obtiene consultas pendientes para el doctor."""
    data = cargar_consultas()
    consultas = data.get('consultas', [])
    pendientes = [c for c in consultas if c['estado'] in ['en_espera', 'en_atencion']]
    pendientes.sort(key=lambda x: x.get('fecha_registro', ''))
    
    return jsonify({
        'exito': True,
        'consultas': pendientes,
        'total': len(pendientes)
    })

@app.route('/api/consultas/por-cobrar', methods=['GET'])
def consultas_por_cobrar():
    """Obtiene consultas atendidas pendientes de cobro."""
    data = cargar_consultas()
    consultas = data.get('consultas', [])
    # Buscar consultas completadas o atendidas que no estén pagadas
    estados_validos = ['atendida', 'completada']
    por_cobrar = [c for c in consultas 
                  if c['estado'] in estados_validos 
                  and c.get('cobro') is not None 
                  and not c.get('cobro', {}).get('pagado', True)]
    
    return jsonify({
        'exito': True,
        'consultas': por_cobrar,
        'total': len(por_cobrar)
    })


@app.route('/api/dashboard/estadisticas', methods=['GET'])
def obtener_estadisticas_dashboard():
    """Obtiene estadísticas reales para el dashboard."""
    from datetime import datetime, timedelta
    
    data = cargar_consultas()
    consultas = data.get('consultas', [])
    
    # Fecha actual y del mes
    hoy = datetime.now()
    primer_dia_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Calcular ingresos del mes (consultas pagadas)
    cobrado_mes = 0
    consultas_hoy = 0
    consultas_mes = 0
    consultas_pagadas_mes = 0
    total_tickets = []
    
    for c in consultas:
        fecha_str = c.get('fecha_registro', '')
        cobro = c.get('cobro', {})
        if fecha_str:
            try:
                fecha = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
                
                # Consultas del mes
                if fecha >= primer_dia_mes:
                    consultas_mes += 1
                    # Sumar ingresos si está pagada
                    if cobro and cobro.get('pagado', False):
                        monto = cobro.get('total', 0)
                        cobrado_mes += monto
                        consultas_pagadas_mes += 1
                        if monto > 0:
                            total_tickets.append(monto)
                
                # Consultas de hoy
                if fecha.date() == hoy.date():
                    consultas_hoy += 1
            except:
                pass
    
    # Consultas pendientes de pago (todas, no solo del mes)
    estados_validos = ['atendida', 'completada']
    pendientes = [c for c in consultas 
                  if c.get('estado') in estados_validos 
                  and c.get('cobro') is not None 
                  and not c.get('cobro', {}).get('pagado', True)]
    
    total_pendiente = sum(c.get('cobro', {}).get('total', 0) for c in pendientes)
    
    # Promedio ticket
    promedio_ticket = int(sum(total_tickets) / len(total_tickets)) if total_tickets else 0
    
    # Consultas en espera hoy
    en_espera = [c for c in consultas if c.get('estado') == 'en_espera']
    
    # Peluquería (simulado por ahora)
    peluqueria_hoy = 3
    
    return jsonify({
        'exito': True,
        'estadisticas': {
            'cobrado_mes': cobrado_mes,
            'ingresos_mes': cobrado_mes,
            'consultas_mes': consultas_mes,
            'consultas_pagadas_mes': consultas_pagadas_mes,
            'consultas_hoy': consultas_hoy,
            'citas_hoy': len(en_espera) + consultas_hoy,
            'pagos_pendientes': len(pendientes),
            'total_pendiente': total_pendiente,
            'promedio_ticket': promedio_ticket,
            'peluqueria_hoy': peluqueria_hoy
        }
    })

@app.route('/api/consultas/nueva', methods=['POST'])
def nueva_consulta():
    """Registra una nueva consulta (recepcionista)."""
    data = request.get_json()
    
    consultas_data = cargar_consultas()
    
    # Generar nuevo ID y ticket de forma atómica
    nuevo_id = max([c['id'] for c in consultas_data['consultas']], default=0) + 1
    consultas_data['ultimo_ticket'] = consultas_data.get('ultimo_ticket', 0) + 1
    numero_ticket = f"BD-{datetime.now().year}-{str(consultas_data['ultimo_ticket']).zfill(4)}"
    
    nueva = {
        'id': nuevo_id,
        'numero_ticket': numero_ticket,
        'fecha_registro': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'estado': 'en_espera',
        'paciente_id': data.get('paciente_id'),  # ID del paciente si existe
        'paciente': {
            'nombre': data.get('nombre_mascota'),
            'especie': data.get('especie'),
            'raza': data.get('raza', ''),
            'edad': data.get('edad', ''),
            'peso': data.get('peso', ''),
            'propietario': data.get('propietario'),
            'telefono': data.get('telefono', '')
        },
        'sintomas': data.get('sintomas', []),
        'motivo_consulta': data.get('motivo_consulta', ''),
        'tipo_consulta': data.get('tipo_consulta', 'general'),
        'registrado_por': data.get('registrado_por', ''),
        'atendido_por': None,
        'diagnostico': None,
        'tratamiento': None,
        'medicamentos_recetados': [],
        'cobro': None,
        'fecha_atencion': None,
        'fecha_cierre': None
    }
    
    consultas_data['consultas'].append(nueva)
    guardar_consultas(consultas_data)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Consulta registrada exitosamente',
        'consulta': nueva,
        'numero_ticket': numero_ticket
    })

@app.route('/api/consultas/<int:consulta_id>', methods=['GET'])
def obtener_consulta(consulta_id):
    """Obtiene una consulta específica."""
    data = cargar_consultas()
    consulta = next((c for c in data['consultas'] if c['id'] == consulta_id), None)
    
    if consulta:
        return jsonify({'exito': True, 'consulta': consulta})
    return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404

@app.route('/api/consultas/<int:consulta_id>/atender', methods=['POST'])
def iniciar_atencion(consulta_id):
    """Doctor inicia la atención de una consulta."""
    req_data = request.get_json()
    data = cargar_consultas()
    
    for consulta in data['consultas']:
        if consulta['id'] == consulta_id:
            consulta['estado'] = 'en_atencion'
            consulta['atendido_por'] = req_data.get('doctor', '')
            consulta['fecha_atencion'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            guardar_consultas(data)
            return jsonify({'exito': True, 'mensaje': 'Atención iniciada', 'consulta': consulta})
    
    return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404

@app.route('/api/consultas/<int:consulta_id>/diagnostico', methods=['POST'])
def guardar_diagnostico(consulta_id):
    """Doctor guarda el diagnóstico y tratamiento con medicamentos detallados."""
    req_data = request.get_json()
    data = cargar_consultas()
    
    for consulta in data['consultas']:
        if consulta['id'] == consulta_id:
            consulta['diagnostico'] = req_data.get('diagnostico')
            consulta['tratamiento'] = req_data.get('tratamiento')
            
            # Procesar medicamentos con estructura mejorada
            medicamentos_raw = req_data.get('medicamentos', [])
            inventario = cargar_inventario()
            meds_inventario = inventario.get('medicamentos', [])
            
            medicamentos_procesados = []
            total_meds = 0
            
            for med_rec in medicamentos_raw:
                med_info = next((m for m in meds_inventario if m['id'] == med_rec['id']), None)
                if med_info:
                    # Verificar disponibilidad de stock
                    cantidad_solicitada = med_rec.get('cantidad', 1)
                    stock_disponible = med_info.get('stock', 0)
                    estado_stock = 'disponible'
                    
                    if stock_disponible == 0:
                        estado_stock = 'agotado'
                    elif stock_disponible < cantidad_solicitada:
                        estado_stock = 'stock_insuficiente'
                    elif stock_disponible <= med_info.get('stock_minimo', 5):
                        estado_stock = 'stock_bajo'
                    
                    subtotal = med_info['precio_unitario'] * cantidad_solicitada
                    total_meds += subtotal
                    
                    medicamento_completo = {
                        'id': med_info['id'],
                        'nombre': med_info['nombre'],
                        'categoria': med_info.get('categoria', ''),
                        'presentacion': med_info.get('presentacion', ''),
                        'cantidad': cantidad_solicitada,
                        'dosis': med_rec.get('dosis', ''),
                        'frecuencia': med_rec.get('frecuencia', ''),
                        'duracion': med_rec.get('duracion', ''),
                        'via_administracion': med_rec.get('via_administracion', 'Oral'),
                        'instrucciones': med_rec.get('instrucciones', ''),
                        'precio_unitario': med_info['precio_unitario'],
                        'subtotal': round(subtotal, 2),
                        'stock_al_recetar': stock_disponible,
                        'estado_stock': estado_stock,
                        'recetado_por': req_data.get('doctor', consulta.get('atendido_por', '')),
                        'fecha_receta': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                    }
                    medicamentos_procesados.append(medicamento_completo)
            
            consulta['medicamentos_recetados'] = medicamentos_procesados
            consulta['estado'] = 'atendida'
            
            # Calcular cobro
            precios = data.get('precios', {})
            tipo = consulta.get('tipo_consulta', 'general')
            precio_consulta = precios.get(f'consulta_{tipo}', 35.00)
            
            consulta['cobro'] = {
                'consulta': precio_consulta,
                'medicamentos': round(total_meds, 2),
                'total': round(precio_consulta + total_meds, 2),
                'pagado': False,
                'metodo_pago': None,
                'detalle_medicamentos': [{
                    'nombre': m['nombre'],
                    'cantidad': m['cantidad'],
                    'precio_unitario': m['precio_unitario'],
                    'subtotal': m['subtotal']
                } for m in medicamentos_procesados]
            }
            
            guardar_consultas(data)
            return jsonify({'exito': True, 'mensaje': 'Diagnóstico guardado', 'consulta': consulta})
    
    return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404

@app.route('/api/consultas/<int:consulta_id>/devolver', methods=['POST'])
def devolver_a_cola(consulta_id):
    """Devuelve una consulta en atención a la cola de espera."""
    data = cargar_consultas()
    
    for consulta in data['consultas']:
        if consulta['id'] == consulta_id:
            if consulta['estado'] == 'en_atencion':
                consulta['estado'] = 'en_espera'
                consulta['atendido_por'] = None
                guardar_consultas(data)
                return jsonify({'exito': True, 'mensaje': 'Consulta devuelta a cola de espera'})
            else:
                return jsonify({'exito': False, 'mensaje': f"La consulta está en estado '{consulta['estado']}', no se puede devolver"}), 400
    
    return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404

@app.route('/api/consultas/<int:consulta_id>/cobrar', methods=['POST'])
def cobrar_consulta(consulta_id):
    """Recepcionista cobra la consulta (puede modificar medicamentos)."""
    req_data = request.get_json()
    data = cargar_consultas()
    
    for consulta in data['consultas']:
        if consulta['id'] == consulta_id:
            # Si se enviaron medicamentos actualizados, usarlos
            meds_actualizados = req_data.get('medicamentos_actualizados')
            if meds_actualizados is not None:
                # Actualizar lista de medicamentos recetados
                consulta['medicamentos_recetados'] = meds_actualizados
                
                # Recalcular cobro de medicamentos
                total_meds = req_data.get('total_medicamentos', 0)
                consulta['cobro']['medicamentos'] = total_meds
                consulta['cobro']['total'] = consulta['cobro']['consulta'] + total_meds
            
            consulta['cobro']['pagado'] = True
            consulta['cobro']['metodo_pago'] = req_data.get('metodo_pago', 'Efectivo')
            consulta['estado'] = 'completada'
            consulta['fecha_cierre'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            
            # Descontar medicamentos del inventario (solo los que se vendieron)
            inventario = cargar_inventario()
            for med_rec in consulta.get('medicamentos_recetados', []):
                for med in inventario['medicamentos']:
                    if med['id'] == med_rec['id']:
                        cantidad = med_rec.get('cantidad', 1)
                        med['stock'] = max(0, med['stock'] - cantidad)
                        break
            guardar_inventario(inventario)
            
            guardar_consultas(data)
            return jsonify({'exito': True, 'mensaje': 'Cobro registrado', 'consulta': consulta})
    
    return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404

@app.route('/api/consultas/<int:consulta_id>/boleta', methods=['GET'])
def generar_boleta(consulta_id):
    """Genera la boleta de una consulta."""
    data = cargar_consultas()
    consulta = next((c for c in data['consultas'] if c['id'] == consulta_id), None)
    
    if not consulta:
        return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404
    
    boleta = {
        'numero_boleta': f"BOL-{consulta['numero_ticket']}",
        'fecha': consulta.get('fecha_cierre') or datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'clinica': {
            'nombre': 'BetterDoctor',
            'subtitulo': 'Clínica Veterinaria',
            'direccion': 'Av. Principal #123, Ciudad',
            'telefono': '(555) 123-4567',
            'email': 'contacto@betterdoctor.com'
        },
        'paciente': consulta['paciente'],
        'atencion': {
            'doctor': consulta.get('atendido_por', ''),
            'diagnostico': consulta.get('diagnostico', {}).get('nombre', ''),
            'tipo_consulta': consulta.get('tipo_consulta', 'general')
        },
        'detalle': [],
        'subtotal_consulta': consulta['cobro']['consulta'],
        'subtotal_medicamentos': consulta['cobro']['medicamentos'],
        'total': consulta['cobro']['total'],
        'metodo_pago': consulta['cobro'].get('metodo_pago', '')
    }
    
    # Detalle de medicamentos
    for med in consulta.get('medicamentos_recetados', []):
        inventario = cargar_inventario()
        med_info = next((m for m in inventario['medicamentos'] if m['id'] == med['id']), None)
        if med_info:
            boleta['detalle'].append({
                'descripcion': med_info['nombre'],
                'cantidad': med.get('cantidad', 1),
                'precio_unitario': med_info['precio_unitario'],
                'subtotal': med_info['precio_unitario'] * med.get('cantidad', 1)
            })
    
    return jsonify({'exito': True, 'boleta': boleta})

@app.route('/api/consultas/<int:consulta_id>/receta', methods=['GET'])
def generar_receta(consulta_id):
    """Genera la receta médica detallada de una consulta."""
    data = cargar_consultas()
    consulta = next((c for c in data['consultas'] if c['id'] == consulta_id), None)
    
    if not consulta:
        return jsonify({'exito': False, 'mensaje': 'Consulta no encontrada'}), 404
    
    # Obtener información del doctor
    doctor_nombre = consulta.get('atendido_por', '')
    usuarios = cargar_usuarios()
    doctor_info = next((u for u in usuarios if u['nombre'] == doctor_nombre or u['usuario'] == doctor_nombre), None)
    
    receta = {
        'numero_receta': f"RX-{consulta['numero_ticket']}",
        'fecha': consulta.get('fecha_atencion') or datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'clinica': {
            'nombre': 'BetterDoctor',
            'subtitulo': 'Clínica Veterinaria',
            'direccion': 'Av. Principal #123, Ciudad',
            'telefono': '(555) 123-4567',
            'email': 'contacto@betterdoctor.com'
        },
        'doctor': {
            'nombre': doctor_nombre,
            'registro': doctor_info.get('registro_profesional', 'CMV-12345') if doctor_info else 'CMV-12345',
            'especialidad': doctor_info.get('especialidad', 'Medicina General') if doctor_info else 'Medicina General',
            'email': doctor_info.get('email', '') if doctor_info else ''
        },
        'paciente': consulta['paciente'],
        'diagnostico': consulta.get('diagnostico', {}),
        'tratamiento': consulta.get('tratamiento', {}),
        'medicamentos': [],
        'indicaciones_generales': consulta.get('tratamiento', {}).get('indicaciones', ''),
        'proxima_cita': 'Control en 7 días',
        'advertencias': []
    }
    
    for med in consulta.get('medicamentos_recetados', []):
        # Los medicamentos ya vienen con información completa desde guardar_diagnostico
        med_receta = {
            'nombre': med.get('nombre', ''),
            'categoria': med.get('categoria', ''),
            'presentacion': med.get('presentacion', ''),
            'cantidad': med.get('cantidad', 1),
            'dosis': med.get('dosis', 'Según indicación médica'),
            'frecuencia': med.get('frecuencia', ''),
            'duracion': med.get('duracion', ''),
            'via_administracion': med.get('via_administracion', 'Oral'),
            'instrucciones': med.get('instrucciones', ''),
            'recetado_por': med.get('recetado_por', doctor_nombre)
        }
        receta['medicamentos'].append(med_receta)
        
        # Agregar advertencia si el stock estaba bajo al recetar
        if med.get('estado_stock') == 'stock_bajo':
            receta['advertencias'].append(f"Stock bajo de {med.get('nombre', '')} al momento de recetar")
        elif med.get('estado_stock') == 'agotado':
            receta['advertencias'].append(f"ATENCIÓN: {med.get('nombre', '')} estaba agotado al momento de recetar")
    
    return jsonify({'exito': True, 'receta': receta})

# ==================== DIAGNÓSTICO ====================

def simular_diagnostico_por_sintomas(sintomas_entrada, especie=None, limite=5):
    # Usar diagnosticos_veterinarios.json que tiene los síntomas actualizados
    diagnosticos = cargar_diagnosticos_completos()
    resultados = []
    
    for diagnostico in diagnosticos:
        if especie and especie.lower() not in [e.lower() for e in diagnostico.get('especie', [])]:
            continue
        
        sintomas_diagnostico = diagnostico.get('sintomas', [])
        porcentaje, sintomas_coincidentes = calcular_coincidencia(sintomas_entrada, sintomas_diagnostico)
        
        # Umbral dinámico: menor para pocos síntomas, mayor para muchos
        # Con 1-2 síntomas: umbral 25%, con 3+ síntomas: umbral 30%
        umbral_minimo = 25 if len(sintomas_entrada) <= 2 else 30
        
        # Pero requerir al menos una coincidencia real (no solo parcial)
        if porcentaje >= umbral_minimo and len(sintomas_coincidentes) > 0:
            resultados.append({
                'diagnostico': {
                    'id': diagnostico.get('id'),
                    'nombre': diagnostico.get('nombre'),
                    'descripcion': diagnostico.get('descripcion'),
                    'gravedad': diagnostico.get('gravedad'),
                    'urgencia': diagnostico.get('urgencia'),
                    'tratamiento': diagnostico.get('tratamiento'),
                    'prevencion': diagnostico.get('prevencion'),
                    'especies_afectadas': diagnostico.get('especie', [])
                },
                'coincidencias': len(sintomas_coincidentes),
                'sintomas_coincidentes': sintomas_coincidentes,
                'total_sintomas_diagnostico': len(sintomas_diagnostico),
                'total_sintomas_entrada': len(sintomas_entrada),
                'porcentaje_coincidencia': round(porcentaje, 1)
            })
    
    # Ordenar por porcentaje y número de coincidencias
    resultados.sort(key=lambda x: (x['porcentaje_coincidencia'], x['coincidencias']), reverse=True)
    return resultados[:limite]

@app.route('/diagnosticar', methods=['GET', 'POST'])
def diagnosticar():
    if request.method == 'POST':
        data = request.get_json()
        sintomas_lista = data.get('sintomas', [])
        especie = data.get('especie', None)
    else:
        sintomas_param = request.args.get('sintomas', '')
        especie = request.args.get('especie', None)
        sintomas_lista = [s.strip() for s in sintomas_param.split(',') if s.strip()]
    
    if not sintomas_lista:
        return jsonify({'exito': False, 'error': 'Debe proporcionar al menos un síntoma'}), 400
    
    resultados = simular_diagnostico_por_sintomas(sintomas_lista, especie)
    
    # Agregar medicamentos recomendados (SOLO medicamentos, no insumos ni servicios)
    inventario = cargar_inventario()
    medicamentos_por_diag = inventario.get('medicamentos_por_diagnostico', {})
    medicamentos_lista = inventario.get('medicamentos', [])
    
    # Categorías que son MEDICAMENTOS (excluir insumos, consultas, cirugías, etc.)
    CATEGORIAS_MEDICAMENTOS = ['Antiparasitarios', 'Vacunas', 'Servicios Extra']
    CATEGORIAS_EXCLUIDAS = ['Insumos', 'Consultas', 'Cirugías', 'Exámenes', 'Hospital', 'Procedimientos']
    
    for resultado in resultados:
        nombre_diag = resultado['diagnostico']['nombre']
        meds_recomendados = medicamentos_por_diag.get(nombre_diag, [])
        
        medicamentos_con_stock = []
        ids_agregados = set()  # Evitar duplicados
        
        for med_nombre in meds_recomendados:
            med_nombre_norm = normalizar_texto(med_nombre)
            
            # Buscar medicamentos que coincidan parcialmente con el nombre
            for med_info in medicamentos_lista:
                # FILTRAR: Solo incluir categorías de medicamentos
                categoria = med_info.get('categoria', '')
                if categoria in CATEGORIAS_EXCLUIDAS:
                    continue
                
                med_info_nombre_norm = normalizar_texto(med_info['nombre'])
                
                # Verificar si el nombre del medicamento contiene el término buscado
                if (med_nombre_norm in med_info_nombre_norm or 
                    med_info_nombre_norm in med_nombre_norm or
                    any(palabra in med_info_nombre_norm for palabra in med_nombre_norm.split() if len(palabra) > 3)):
                    
                    # Evitar duplicados
                    if med_info['id'] in ids_agregados:
                        continue
                    ids_agregados.add(med_info['id'])
                    
                    estado_stock = 'disponible'
                    if med_info['stock'] == 0:
                        estado_stock = 'agotado'
                    elif med_info['stock'] <= med_info.get('stock_minimo', 5):
                        estado_stock = 'bajo'
                    
                    medicamentos_con_stock.append({
                        'id': med_info['id'],
                        'nombre': med_info['nombre'],
                        'categoria': med_info.get('categoria', ''),
                        'presentacion': med_info.get('presentacion', ''),
                        'stock': med_info.get('stock', 0),
                        'stock_minimo': med_info.get('stock_minimo', 5),
                        'estado_stock': estado_stock,
                        'precio_unitario': med_info.get('precio_unitario', 0),
                        'unidad': med_info.get('unidad', 'unidades'),
                        'tipo_recomendado': med_nombre  # Indica por qué se recomienda
                    })
        
        # Ordenar: disponibles primero, luego por nombre
        medicamentos_con_stock.sort(key=lambda x: (0 if x['estado_stock'] == 'disponible' else 1, x['nombre']))
        resultado['medicamentos_recomendados'] = medicamentos_con_stock
    
    if resultados:
        return jsonify({
            'exito': True,
            'sintomas_ingresados': sintomas_lista,
            'especie': especie,
            'cantidad_resultados': len(resultados),
            'resultados': resultados
        })
    else:
        return jsonify({
            'exito': False,
            'sintomas_ingresados': sintomas_lista,
            'especie': especie,
            'cantidad_resultados': 0,
            'resultados': [],
            'mensaje': 'No se encontraron diagnósticos.'
        })

# ==================== INVENTARIO ====================

@app.route('/api/inventario', methods=['GET'])
def obtener_inventario():
    inventario = cargar_inventario()
    medicamentos = inventario.get('medicamentos', [])
    
    for med in medicamentos:
        if med['stock'] == 0:
            med['estado_stock'] = 'agotado'
        elif med['stock'] <= med['stock_minimo']:
            med['estado_stock'] = 'bajo'
        else:
            med['estado_stock'] = 'disponible'
    
    total = len(medicamentos)
    agotados = sum(1 for m in medicamentos if m['estado_stock'] == 'agotado')
    bajo_stock = sum(1 for m in medicamentos if m['estado_stock'] == 'bajo')
    disponibles = total - agotados - bajo_stock
    
    return jsonify({
        'exito': True,
        'medicamentos': medicamentos,
        'estadisticas': {'total': total, 'disponibles': disponibles, 'bajo_stock': bajo_stock, 'agotados': agotados}
    })

@app.route('/api/inventario/<int:med_id>/actualizar-stock', methods=['POST'])
def actualizar_stock(med_id):
    data = request.get_json()
    cantidad = data.get('cantidad', 0)
    tipo = data.get('tipo', 'agregar')
    
    inventario = cargar_inventario()
    
    for med in inventario['medicamentos']:
        if med['id'] == med_id:
            if tipo == 'agregar':
                med['stock'] += cantidad
            elif tipo == 'restar':
                if med['stock'] >= cantidad:
                    med['stock'] -= cantidad
                else:
                    return jsonify({'exito': False, 'mensaje': f'Stock insuficiente. Disponible: {med["stock"]}'}), 400
            elif tipo == 'establecer':
                med['stock'] = cantidad
            
            guardar_inventario(inventario)
            return jsonify({'exito': True, 'mensaje': 'Stock actualizado', 'nuevo_stock': med['stock']})
    
    return jsonify({'exito': False, 'mensaje': 'Medicamento no encontrado'}), 404

@app.route('/api/inventario/agregar', methods=['POST'])
def agregar_medicamento():
    data = request.get_json()
    inventario = cargar_inventario()
    
    nuevo_id = max([m['id'] for m in inventario['medicamentos']], default=0) + 1
    
    nuevo_med = {
        'id': nuevo_id,
        'codigo': data.get('codigo', ''),
        'nombre': data.get('nombre'),
        'categoria': data.get('categoria'),
        'presentacion': data.get('presentacion', ''),
        'unidad': data.get('unidad', 'unidades'),
        'stock': data.get('stock', 0),
        'stock_minimo': data.get('stock_minimo', 10),
        'precio_unitario': data.get('precio_unitario', 0),
        'costo': data.get('costo', 0),
        'proveedor': data.get('proveedor', ''),
        'punto_venta': data.get('punto_venta', True)
    }
    
    inventario['medicamentos'].append(nuevo_med)
    guardar_inventario(inventario)
    
    return jsonify({'exito': True, 'mensaje': 'Medicamento agregado', 'medicamento': nuevo_med})

@app.route('/api/inventario/alertas', methods=['GET'])
def obtener_alertas():
    inventario = cargar_inventario()
    medicamentos = inventario.get('medicamentos', [])
    
    alertas = {'stock_bajo': [], 'agotados': [], 'proximos_vencer': []}
    fecha_actual = datetime.now()
    
    for med in medicamentos:
        if med['stock'] == 0:
            alertas['agotados'].append({'id': med['id'], 'nombre': med['nombre'], 'categoria': med['categoria']})
        elif med['stock'] <= med['stock_minimo']:
            alertas['stock_bajo'].append({'id': med['id'], 'nombre': med['nombre'], 'stock_actual': med['stock'], 'stock_minimo': med['stock_minimo']})
        
        try:
            fecha_venc = datetime.strptime(med['vencimiento'], '%Y-%m-%d')
            dias = (fecha_venc - fecha_actual).days
            if 0 < dias <= 30:
                alertas['proximos_vencer'].append({'id': med['id'], 'nombre': med['nombre'], 'vencimiento': med['vencimiento'], 'dias_restantes': dias})
        except:
            pass
    
    return jsonify({
        'exito': True,
        'alertas': alertas,
        'resumen': {
            'total_alertas': len(alertas['stock_bajo']) + len(alertas['agotados']) + len(alertas['proximos_vencer']),
            'stock_bajo': len(alertas['stock_bajo']),
            'agotados': len(alertas['agotados']),
            'proximos_vencer': len(alertas['proximos_vencer'])
        }
    })

# ==================== RAZAS ====================

@app.route('/api/razas', methods=['GET'])
def obtener_razas():
    """Obtiene todas las razas de perros y gatos."""
    razas = cargar_razas()
    return jsonify({
        'exito': True,
        'perros': razas.get('perros', []),
        'gatos': razas.get('gatos', []),
        'total_perros': len(razas.get('perros', [])),
        'total_gatos': len(razas.get('gatos', []))
    })

@app.route('/api/razas/<especie>', methods=['GET'])
def obtener_razas_por_especie(especie):
    """Obtiene razas filtradas por especie (perro/gato)."""
    razas = cargar_razas()
    especie_lower = especie.lower()
    
    if especie_lower in ['perro', 'perros', 'canino']:
        lista_razas = razas.get('perros', [])
    elif especie_lower in ['gato', 'gatos', 'felino']:
        lista_razas = razas.get('gatos', [])
    else:
        return jsonify({'exito': False, 'mensaje': 'Especie no válida. Use: perro o gato'}), 400
    
    return jsonify({
        'exito': True,
        'especie': especie_lower,
        'razas': lista_razas,
        'total': len(lista_razas)
    })

@app.route('/api/razas/buscar', methods=['GET'])
def buscar_razas():
    """Busca razas por nombre."""
    query = request.args.get('q', '').strip()
    especie = request.args.get('especie', '').strip().lower()
    
    if len(query) < 2:
        return jsonify({'exito': True, 'razas': [], 'mensaje': 'Ingrese al menos 2 caracteres'})
    
    razas = cargar_razas()
    query_norm = normalizar_texto(query)
    resultados = []
    
    # Buscar en perros
    if not especie or especie in ['perro', 'perros', 'canino']:
        for raza in razas.get('perros', []):
            if query_norm in normalizar_texto(raza['nombre']):
                resultados.append({**raza, 'especie': 'Perro'})
    
    # Buscar en gatos
    if not especie or especie in ['gato', 'gatos', 'felino']:
        for raza in razas.get('gatos', []):
            if query_norm in normalizar_texto(raza['nombre']):
                resultados.append({**raza, 'especie': 'Gato'})
    
    return jsonify({
        'exito': True,
        'query': query,
        'razas': resultados,
        'total': len(resultados)
    })

@app.route('/api/razas/<especie>/<int:raza_id>', methods=['GET'])
def obtener_detalle_raza(especie, raza_id):
    """Obtiene información detallada de una raza específica."""
    razas = cargar_razas()
    especie_lower = especie.lower()
    
    if especie_lower in ['perro', 'perros', 'canino']:
        lista_razas = razas.get('perros', [])
    elif especie_lower in ['gato', 'gatos', 'felino']:
        lista_razas = razas.get('gatos', [])
    else:
        return jsonify({'exito': False, 'mensaje': 'Especie no válida'}), 400
    
    raza = next((r for r in lista_razas if r['id'] == raza_id), None)
    
    if raza:
        return jsonify({'exito': True, 'raza': raza})
    return jsonify({'exito': False, 'mensaje': 'Raza no encontrada'}), 404

# ==================== MEDICAMENTOS POR DIAGNÓSTICO ====================

@app.route('/api/medicamentos/por-diagnostico/<diagnostico_nombre>', methods=['GET'])
def obtener_medicamentos_por_diagnostico(diagnostico_nombre):
    """Obtiene medicamentos recomendados para un diagnóstico específico."""
    diagnosticos = cargar_diagnosticos_completos()
    inventario = cargar_inventario()
    meds_inventario = inventario.get('medicamentos', [])
    
    # Buscar el diagnóstico
    diagnostico_norm = normalizar_texto(diagnostico_nombre)
    diagnostico = next((d for d in diagnosticos if normalizar_texto(d['nombre']) == diagnostico_norm), None)
    
    if not diagnostico:
        # Búsqueda parcial
        diagnostico = next((d for d in diagnosticos if diagnostico_norm in normalizar_texto(d['nombre'])), None)
    
    if not diagnostico:
        return jsonify({'exito': False, 'mensaje': 'Diagnóstico no encontrado'}), 404
    
    # Obtener medicamentos asociados
    meds_asociados = diagnostico.get('medicamentos_asociados', [])
    medicamentos_con_stock = []
    
    for med_nombre in meds_asociados:
        med_norm = normalizar_texto(med_nombre)
        # Buscar coincidencia en inventario
        for med in meds_inventario:
            if med_norm in normalizar_texto(med['nombre']) or normalizar_texto(med['nombre']) in med_norm:
                estado_stock = 'disponible'
                if med['stock'] == 0:
                    estado_stock = 'agotado'
                elif med['stock'] <= med.get('stock_minimo', 5):
                    estado_stock = 'bajo'
                
                if not any(m['id'] == med['id'] for m in medicamentos_con_stock):
                    medicamentos_con_stock.append({
                        'id': med['id'],
                        'nombre': med['nombre'],
                        'categoria': med.get('categoria', ''),
                        'presentacion': med.get('presentacion', ''),
                        'stock': med['stock'],
                        'stock_minimo': med.get('stock_minimo', 5),
                        'estado_stock': estado_stock,
                        'precio_unitario': med.get('precio_unitario', 0),
                        'recomendado_para': diagnostico['nombre']
                    })
    
    return jsonify({
        'exito': True,
        'diagnostico': {
            'id': diagnostico['id'],
            'nombre': diagnostico['nombre'],
            'tratamiento': diagnostico.get('tratamiento', '')
        },
        'medicamentos_recomendados': medicamentos_con_stock,
        'total': len(medicamentos_con_stock)
    })

@app.route('/api/medicamentos/buscar-disponibles', methods=['GET'])
def buscar_medicamentos_disponibles():
    """Busca medicamentos disponibles en inventario."""
    query = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '').strip()
    solo_disponibles = request.args.get('solo_disponibles', 'false').lower() == 'true'
    
    inventario = cargar_inventario()
    medicamentos = inventario.get('medicamentos', [])
    
    resultados = []
    query_norm = normalizar_texto(query) if query else ''
    
    for med in medicamentos:
        # Filtrar por query
        if query_norm and query_norm not in normalizar_texto(med['nombre']):
            continue
        
        # Filtrar por categoría
        if categoria and normalizar_texto(categoria) not in normalizar_texto(med.get('categoria', '')):
            continue
        
        # Filtrar solo disponibles
        if solo_disponibles and med['stock'] == 0:
            continue
        
        estado_stock = 'disponible'
        if med['stock'] == 0:
            estado_stock = 'agotado'
        elif med['stock'] <= med.get('stock_minimo', 5):
            estado_stock = 'bajo'
        
        resultados.append({
            'id': med['id'],
            'nombre': med['nombre'],
            'categoria': med.get('categoria', ''),
            'presentacion': med.get('presentacion', ''),
            'stock': med['stock'],
            'estado_stock': estado_stock,
            'precio_unitario': med.get('precio_unitario', 0)
        })
    
    # Ordenar: disponibles primero, luego bajo stock, luego agotados
    orden_estado = {'disponible': 0, 'bajo': 1, 'agotado': 2}
    resultados.sort(key=lambda x: (orden_estado.get(x['estado_stock'], 3), x['nombre']))
    
    return jsonify({
        'exito': True,
        'medicamentos': resultados[:50],  # Limitar a 50 resultados
        'total': len(resultados)
    })

# ==================== ENDPOINTS GENERALES ====================

@app.route('/diagnosticos', methods=['GET'])
def listar_diagnosticos():
    diagnosticos = cargar_datos()
    return jsonify({
        'total': len(diagnosticos),
        'diagnosticos': [{'id': d.get('id'), 'nombre': d.get('nombre'), 'gravedad': d.get('gravedad')} for d in diagnosticos]
    })

@app.route('/api/sintomas', methods=['GET'])
def obtener_sintomas():
    """Obtiene la lista de todos los síntomas disponibles en la base de datos."""
    diagnosticos = cargar_diagnosticos_completos()
    
    # Recopilar todos los síntomas únicos
    sintomas_set = set()
    for diag in diagnosticos:
        for sintoma in diag.get('sintomas', []):
            sintomas_set.add(sintoma)
    
    # Ordenar alfabéticamente
    sintomas_lista = sorted(list(sintomas_set))
    
    return jsonify({
        'exito': True,
        'sintomas': sintomas_lista,
        'total': len(sintomas_lista)
    })

@app.route('/api/servicios', methods=['GET'])
def obtener_servicios():
    """Obtiene la lista de servicios adicionales (exámenes, hospitalización, cirugías, etc.)."""
    inventario = cargar_inventario()
    medicamentos = inventario.get('medicamentos', [])
    
    # Categorías que son servicios (no productos físicos)
    CATEGORIAS_SERVICIOS = ['Consultas', 'Exámenes', 'Hospital', 'Cirugías', 'Procedimientos']
    
    servicios = []
    for med in medicamentos:
        if med.get('categoria') in CATEGORIAS_SERVICIOS:
            servicios.append({
                'id': med.get('id'),
                'nombre': med.get('nombre'),
                'categoria': med.get('categoria'),
                'precio': med.get('precio_unitario', 0)
            })
    
    # Agrupar por categoría
    servicios_agrupados = {}
    for serv in servicios:
        cat = serv['categoria']
        if cat not in servicios_agrupados:
            servicios_agrupados[cat] = []
        servicios_agrupados[cat].append(serv)
    
    return jsonify({
        'exito': True,
        'servicios': servicios,
        'servicios_agrupados': servicios_agrupados,
        'total': len(servicios)
    })

@app.route('/api/examenes-sugeridos/<diagnostico_nombre>', methods=['GET'])
def obtener_examenes_sugeridos(diagnostico_nombre):
    """Obtiene exámenes sugeridos basados en el diagnóstico."""
    inventario = cargar_inventario()
    medicamentos = inventario.get('medicamentos', [])
    
    # Mapeo de diagnósticos a exámenes recomendados
    EXAMENES_POR_DIAGNOSTICO = {
        # Enfermedades virales felinas
        'leucemia felina': ['FIV/FELV', 'HEMOGRAMA', 'PERFIL BIOQUIMICO'],
        'inmunodeficiencia felina': ['FIV/FELV', 'HEMOGRAMA', 'PERFIL BIOQUIMICO'],
        'panleucopenia': ['HEMOGRAMA', 'PARVO', 'PCR'],
        'rinotraqueitis': ['PCR', 'HEMOGRAMA'],
        'calicivirus': ['PCR', 'HEMOGRAMA'],
        'peritonitis infecciosa': ['CORONAVIRUS', 'PERFIL BIOQUIMICO', 'HEMOGRAMA'],
        
        # Enfermedades virales caninas
        'parvovirus': ['PARVO', 'HEMOGRAMA', 'PERFIL BIOQUIMICO'],
        'moquillo': ['DISTEMPER', 'HEMOGRAMA', 'PCR'],
        'coronavirus canino': ['CORONAVIRUS', 'HEMOGRAMA'],
        'hepatitis': ['PERFIL HEPATICO', 'HEMOGRAMA', 'ECOGRAFIA'],
        
        # Enfermedades parasitarias
        'ehrlichiosis': ['EHRLICHIA', 'HEMOGRAMA', 'FROTIS'],
        'anaplasmosis': ['ANAPLASMA', 'HEMOGRAMA'],
        'babesiosis': ['BABESIA', 'HEMOGRAMA', 'FROTIS'],
        'leishmaniasis': ['LEISHMANIA', 'HEMOGRAMA', 'PERFIL BIOQUIMICO'],
        'dirofilariasis': ['DIROFILARIA', 'HEMOGRAMA', 'RADIOGRAFIA'],
        'giardiasis': ['COPROPARASITARIO', 'GIARDIA'],
        'sarna': ['RASPADO', 'CITOLOGIA'],
        
        # Enfermedades renales
        'insuficiencia renal': ['PERFIL RENAL', 'ORINA', 'ECOGRAFIA', 'HEMOGRAMA'],
        'enfermedad renal': ['PERFIL RENAL', 'ORINA', 'ECOGRAFIA'],
        'cistitis': ['ORINA', 'UROCULTIVO', 'ECOGRAFIA'],
        'urolitiasis': ['ORINA', 'RADIOGRAFIA', 'ECOGRAFIA'],
        
        # Enfermedades hepáticas
        'hepatopatia': ['PERFIL HEPATICO', 'ECOGRAFIA', 'HEMOGRAMA'],
        'insuficiencia hepatica': ['PERFIL HEPATICO', 'ECOGRAFIA', 'COAGULACION'],
        
        # Enfermedades endocrinas
        'diabetes': ['GLICEMIA', 'FRUCTOSAMINA', 'ORINA', 'PERFIL BIOQUIMICO'],
        'hipotiroidismo': ['T4', 'TSH', 'HEMOGRAMA'],
        'hipertiroidismo': ['T4', 'TSH', 'HEMOGRAMA', 'PERFIL BIOQUIMICO'],
        'cushing': ['CORTISOL', 'PERFIL BIOQUIMICO', 'ORINA'],
        'addison': ['CORTISOL', 'ELECTROLITOS', 'HEMOGRAMA'],
        
        # Enfermedades gastrointestinales
        'gastroenteritis': ['HEMOGRAMA', 'COPROPARASITARIO', 'PERFIL BIOQUIMICO'],
        'pancreatitis': ['LIPASA', 'AMILASA', 'ECOGRAFIA', 'HEMOGRAMA'],
        'obstruccion intestinal': ['RADIOGRAFIA', 'ECOGRAFIA', 'HEMOGRAMA'],
        'ibd': ['HEMOGRAMA', 'PERFIL BIOQUIMICO', 'ECOGRAFIA'],
        
        # Enfermedades cardíacas
        'cardiomiopatia': ['ECOCARDIOGRAMA', 'RADIOGRAFIA', 'ELECTROCARDIOGRAMA'],
        'insuficiencia cardiaca': ['ECOCARDIOGRAMA', 'RADIOGRAFIA', 'PROANP'],
        'arritmia': ['ELECTROCARDIOGRAMA', 'HOLTER'],
        
        # Enfermedades respiratorias
        'neumonia': ['RADIOGRAFIA', 'HEMOGRAMA', 'CITOLOGIA'],
        'bronquitis': ['RADIOGRAFIA', 'HEMOGRAMA'],
        'asma felino': ['RADIOGRAFIA', 'HEMOGRAMA'],
        'colapso traqueal': ['RADIOGRAFIA', 'FLUOROSCOPIA'],
        
        # Enfermedades dermatológicas
        'dermatitis': ['RASPADO', 'CITOLOGIA', 'CULTIVO'],
        'pioderma': ['CITOLOGIA', 'CULTIVO', 'ANTIBIOGRAMA'],
        'otitis': ['CITOLOGIA OTICA', 'CULTIVO'],
        'alergia': ['HEMOGRAMA', 'IGE', 'PANEL ALERGENOS'],
        
        # Enfermedades oncológicas
        'tumor': ['CITOLOGIA', 'BIOPSIA', 'RADIOGRAFIA', 'ECOGRAFIA'],
        'linfoma': ['CITOLOGIA', 'HEMOGRAMA', 'ECOGRAFIA', 'BIOPSIA'],
        'mastocitoma': ['CITOLOGIA', 'HEMOGRAMA', 'ECOGRAFIA'],
        
        # Traumatismos
        'fractura': ['RADIOGRAFIA'],
        'luxacion': ['RADIOGRAFIA'],
        'trauma': ['RADIOGRAFIA', 'ECOGRAFIA', 'HEMOGRAMA'],
        'displasia': ['RADIOGRAFIA'],
        
        # Otros
        'anemia': ['HEMOGRAMA', 'FROTIS', 'RETICULOCITOS', 'PERFIL BIOQUIMICO'],
        'trombocitopenia': ['HEMOGRAMA', 'FROTIS', 'COAGULACION'],
        'intoxicacion': ['PERFIL BIOQUIMICO', 'HEMOGRAMA', 'COAGULACION'],
        'convulsiones': ['HEMOGRAMA', 'PERFIL BIOQUIMICO', 'GLICEMIA'],
        'epilepsia': ['HEMOGRAMA', 'PERFIL BIOQUIMICO'],
    }
    
    # Normalizar nombre del diagnóstico
    diag_norm = diagnostico_nombre.lower().strip()
    diag_norm = ''.join(c for c in diag_norm if c.isalnum() or c.isspace())
    
    # Buscar exámenes recomendados
    examenes_recomendados = []
    for key, examenes in EXAMENES_POR_DIAGNOSTICO.items():
        if key in diag_norm or diag_norm in key:
            examenes_recomendados = examenes
            break
    
    # Si no hay match exacto, buscar palabras clave
    if not examenes_recomendados:
        palabras_diag = set(diag_norm.split())
        for key, examenes in EXAMENES_POR_DIAGNOSTICO.items():
            palabras_key = set(key.split())
            if palabras_diag & palabras_key:
                examenes_recomendados = examenes
                break
    
    # Buscar los servicios de exámenes que coincidan
    examenes_disponibles = []
    for med in medicamentos:
        if med.get('categoria') == 'Exámenes':
            nombre_norm = med.get('nombre', '').upper()
            for exam in examenes_recomendados:
                if exam.upper() in nombre_norm or nombre_norm in exam.upper():
                    examenes_disponibles.append({
                        'id': med.get('id'),
                        'nombre': med.get('nombre'),
                        'precio': med.get('precio_unitario', 0),
                        'tipo': exam
                    })
                    break
    
    # Agregar exámenes básicos comunes si no hay específicos
    if not examenes_disponibles:
        for med in medicamentos:
            if med.get('categoria') == 'Exámenes':
                nombre = med.get('nombre', '').upper()
                if any(x in nombre for x in ['HEMOGRAMA', 'PERFIL', 'ORINA', 'COPROPARASITARIO']):
                    examenes_disponibles.append({
                        'id': med.get('id'),
                        'nombre': med.get('nombre'),
                        'precio': med.get('precio_unitario', 0),
                        'tipo': 'Básico'
                    })
    
    return jsonify({
        'exito': True,
        'diagnostico': diagnostico_nombre,
        'examenes': examenes_disponibles[:10],
        'total': len(examenes_disponibles)
    })

@app.route('/api/diagnosticos/buscar', methods=['GET'])
def buscar_diagnosticos():
    """Busca diagnósticos por nombre y devuelve medicamentos recomendados."""
    query = request.args.get('q', '').strip()
    especie = request.args.get('especie', '').strip()
    
    if len(query) < 2:
        return jsonify({'exito': True, 'diagnosticos': [], 'mensaje': 'Ingrese al menos 2 caracteres'})
    
    diagnosticos = cargar_datos()
    inventario = cargar_inventario()
    medicamentos_por_diag = inventario.get('medicamentos_por_diagnostico', {})
    medicamentos_lista = inventario.get('medicamentos', [])
    
    # Categorías excluidas (no son medicamentos)
    CATEGORIAS_EXCLUIDAS = ['Insumos', 'Consultas', 'Cirugías', 'Exámenes', 'Hospital', 'Procedimientos']
    
    query_norm = normalizar_texto(query)
    resultados = []
    
    for diag in diagnosticos:
        nombre_norm = normalizar_texto(diag.get('nombre', ''))
        
        # Filtrar por especie si se especifica
        if especie:
            especies_diag = [e.lower() for e in diag.get('especie', [])]
            if especie.lower() not in especies_diag and especie.lower() + 's' not in especies_diag:
                continue
        
        # Buscar coincidencia en nombre
        if query_norm in nombre_norm:
            # Obtener medicamentos recomendados para este diagnóstico
            meds_recomendados_nombres = medicamentos_por_diag.get(diag.get('nombre', ''), [])
            medicamentos_con_stock = []
            ids_agregados = set()
            
            for med_nombre in meds_recomendados_nombres:
                med_nombre_norm = normalizar_texto(med_nombre)
                
                for med_info in medicamentos_lista:
                    # Filtrar insumos y servicios no-medicamentos
                    if med_info.get('categoria', '') in CATEGORIAS_EXCLUIDAS:
                        continue
                    
                    med_info_nombre_norm = normalizar_texto(med_info['nombre'])
                    
                    if (med_nombre_norm in med_info_nombre_norm or 
                        any(palabra in med_info_nombre_norm for palabra in med_nombre_norm.split() if len(palabra) > 3)):
                        
                        if med_info['id'] in ids_agregados:
                            continue
                        ids_agregados.add(med_info['id'])
                        
                        estado_stock = 'disponible'
                        if med_info['stock'] == 0:
                            estado_stock = 'agotado'
                        elif med_info['stock'] <= med_info.get('stock_minimo', 5):
                            estado_stock = 'bajo'
                        
                        medicamentos_con_stock.append({
                            'id': med_info['id'],
                            'nombre': med_info['nombre'],
                            'categoria': med_info.get('categoria', ''),
                            'stock': med_info.get('stock', 0),
                            'estado_stock': estado_stock,
                            'precio_unitario': med_info.get('precio_unitario', 0),
                            'tipo_recomendado': med_nombre
                        })
            
            # Ordenar medicamentos
            medicamentos_con_stock.sort(key=lambda x: (0 if x['estado_stock'] == 'disponible' else 1, x['nombre']))
            
            resultados.append({
                'id': diag.get('id'),
                'nombre': diag.get('nombre'),
                'descripcion': diag.get('descripcion', ''),
                'gravedad': diag.get('gravedad', ''),
                'urgencia': diag.get('urgencia', ''),
                'tratamiento': diag.get('tratamiento', ''),
                'prevencion': diag.get('prevencion', ''),
                'sintomas': diag.get('sintomas', []),
                'especies': diag.get('especie', []),
                'medicamentos_recomendados': medicamentos_con_stock
            })
    
    return jsonify({
        'exito': True,
        'query': query,
        'diagnosticos': resultados,
        'total': len(resultados)
    })

@app.route('/api/diagnosticos/<int:diag_id>', methods=['GET'])
def obtener_diagnostico(diag_id):
    """Obtiene un diagnóstico específico con sus medicamentos recomendados."""
    diagnosticos = cargar_datos()
    inventario = cargar_inventario()
    medicamentos_por_diag = inventario.get('medicamentos_por_diagnostico', {})
    medicamentos_lista = inventario.get('medicamentos', [])
    
    CATEGORIAS_EXCLUIDAS = ['Insumos', 'Consultas', 'Cirugías', 'Exámenes', 'Hospital', 'Procedimientos']
    
    diag = next((d for d in diagnosticos if d.get('id') == diag_id), None)
    
    if not diag:
        return jsonify({'exito': False, 'mensaje': 'Diagnóstico no encontrado'}), 404
    
    # Obtener medicamentos recomendados
    meds_recomendados_nombres = medicamentos_por_diag.get(diag.get('nombre', ''), [])
    medicamentos_con_stock = []
    ids_agregados = set()
    
    for med_nombre in meds_recomendados_nombres:
        med_nombre_norm = normalizar_texto(med_nombre)
        
        for med_info in medicamentos_lista:
            if med_info.get('categoria', '') in CATEGORIAS_EXCLUIDAS:
                continue
            
            med_info_nombre_norm = normalizar_texto(med_info['nombre'])
            
            if (med_nombre_norm in med_info_nombre_norm or 
                any(palabra in med_info_nombre_norm for palabra in med_nombre_norm.split() if len(palabra) > 3)):
                
                if med_info['id'] in ids_agregados:
                    continue
                ids_agregados.add(med_info['id'])
                
                estado_stock = 'disponible'
                if med_info['stock'] == 0:
                    estado_stock = 'agotado'
                elif med_info['stock'] <= med_info.get('stock_minimo', 5):
                    estado_stock = 'bajo'
                
                medicamentos_con_stock.append({
                    'id': med_info['id'],
                    'nombre': med_info['nombre'],
                    'categoria': med_info.get('categoria', ''),
                    'presentacion': med_info.get('presentacion', ''),
                    'stock': med_info.get('stock', 0),
                    'stock_minimo': med_info.get('stock_minimo', 5),
                    'estado_stock': estado_stock,
                    'precio_unitario': med_info.get('precio_unitario', 0),
                    'unidad': med_info.get('unidad', 'unidades'),
                    'tipo_recomendado': med_nombre
                })
    
    medicamentos_con_stock.sort(key=lambda x: (0 if x['estado_stock'] == 'disponible' else 1, x['nombre']))
    
    return jsonify({
        'exito': True,
        'diagnostico': {
            'id': diag.get('id'),
            'nombre': diag.get('nombre'),
            'descripcion': diag.get('descripcion', ''),
            'gravedad': diag.get('gravedad', ''),
            'urgencia': diag.get('urgencia', ''),
            'tratamiento': diag.get('tratamiento', ''),
            'prevencion': diag.get('prevencion', ''),
            'sintomas': diag.get('sintomas', []),
            'especies': diag.get('especie', [])
        },
        'medicamentos_recomendados': medicamentos_con_stock,
        'total_medicamentos': len(medicamentos_con_stock)
    })

@app.route('/sintomas', methods=['GET'])
def listar_sintomas():
    diagnosticos = cargar_datos()
    sintomas_unicos = set()
    for d in diagnosticos:
        for s in d.get('sintomas', []):
            sintomas_unicos.add(s)
    return jsonify({'total': len(sintomas_unicos), 'sintomas': sorted(list(sintomas_unicos))})

@app.route('/api/sintomas/buscar', methods=['GET'])
def buscar_sintomas():
    """Busca síntomas que coincidan con el texto ingresado."""
    query = request.args.get('q', '').strip()
    limite = int(request.args.get('limite', 10))
    
    if len(query) < 2:
        return jsonify({'exito': True, 'sintomas': [], 'mensaje': 'Ingrese al menos 2 caracteres'})
    
    # Cargar todos los síntomas de la base de datos
    diagnosticos = cargar_datos()
    sintomas_unicos = set()
    for d in diagnosticos:
        for s in d.get('sintomas', []):
            sintomas_unicos.add(s)
    
    # Normalizar query para búsqueda
    query_norm = normalizar_texto(query)
    
    # Buscar coincidencias
    coincidencias = []
    for sintoma in sintomas_unicos:
        sintoma_norm = normalizar_texto(sintoma)
        if query_norm in sintoma_norm:
            # Calcular relevancia (priorizar los que empiezan con el texto)
            relevancia = 0
            if sintoma_norm.startswith(query_norm):
                relevancia = 2
            elif any(palabra.startswith(query_norm) for palabra in sintoma_norm.split()):
                relevancia = 1
            coincidencias.append({'sintoma': sintoma, 'relevancia': relevancia})
    
    # Ordenar por relevancia y alfabéticamente
    coincidencias.sort(key=lambda x: (-x['relevancia'], x['sintoma'].lower()))
    
    # Limitar resultados
    resultado = [c['sintoma'] for c in coincidencias[:limite]]
    
    return jsonify({
        'exito': True,
        'query': query,
        'sintomas': resultado,
        'total': len(resultado)
    })

# ==================== GESTIÓN DE PACIENTES (FICHAS) ====================

@app.route('/api/pacientes', methods=['GET', 'POST'])
def pacientes_endpoint():
    """Lista todos los pacientes (GET) o crea uno nuevo (POST)."""
    if request.method == 'POST':
        return crear_paciente_rapido()
    
    data = cargar_pacientes()
    pacientes = data.get('pacientes', [])
    return jsonify({
        'exito': True,
        'pacientes': pacientes,
        'total': len(pacientes)
    })

def crear_paciente_rapido():
    """Crea una nueva ficha de paciente (método rápido)."""
    req_data = request.get_json()
    data = cargar_pacientes()
    
    # Generar nuevo ID
    nuevo_id = data.get('ultimo_id', 0) + 1
    
    # Calcular edad desde fecha de nacimiento
    fecha_nac = req_data.get('fecha_nacimiento', '')
    edad_calc = calcular_edad(fecha_nac) if fecha_nac else ''
    
    nuevo_paciente = {
        'id': nuevo_id,
        'nombre': req_data.get('nombre', ''),
        'especie': req_data.get('especie', ''),
        'raza': req_data.get('raza', ''),
        'color': req_data.get('color', ''),
        'sexo': req_data.get('sexo', ''),
        'fecha_nacimiento': fecha_nac,
        'edad': edad_calc,
        'peso': req_data.get('peso', ''),
        'microchip': req_data.get('microchip', ''),
        'alergias': req_data.get('alergias', ''),
        'esterilizado': req_data.get('esterilizado', False),
        'tutor': req_data.get('tutor', {}),
        'historial_consultas': [],
        'vacunas': [],
        'fecha_registro': datetime.now().isoformat()
    }
    
    data['pacientes'].append(nuevo_paciente)
    data['ultimo_id'] = nuevo_id
    guardar_pacientes(data)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Paciente registrado exitosamente',
        'paciente': nuevo_paciente
    })

@app.route('/api/pacientes/buscar', methods=['GET'])
def buscar_pacientes():
    """Busca pacientes por nombre del animal o del propietario."""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify({'exito': True, 'pacientes': [], 'mensaje': 'Ingrese al menos 2 caracteres'})
    
    data = cargar_pacientes()
    pacientes = data.get('pacientes', [])
    query_norm = normalizar_texto(query)
    
    resultados = []
    for p in pacientes:
        nombre_mascota_norm = normalizar_texto(p.get('nombre', ''))
        nombre_propietario_norm = normalizar_texto(p.get('propietario', {}).get('nombre', ''))
        rut_norm = normalizar_texto(p.get('propietario', {}).get('rut', '').replace('.', '').replace('-', ''))
        
        # Buscar en nombre de mascota, propietario o RUT
        if (query_norm in nombre_mascota_norm or 
            query_norm in nombre_propietario_norm or 
            query_norm in rut_norm):
            resultados.append({
                'id': p['id'],
                'nombre': p['nombre'],
                'especie': p['especie'],
                'raza': p.get('raza', ''),
                'propietario': p.get('propietario', {}).get('nombre', ''),
                'telefono': p.get('propietario', {}).get('telefono', ''),
                'ultima_visita': p.get('historial_consultas', [])[-1] if p.get('historial_consultas') else None
            })
    
    return jsonify({
        'exito': True,
        'query': query,
        'pacientes': resultados,
        'total': len(resultados)
    })

@app.route('/api/pacientes/<int:paciente_id>', methods=['GET'])
def obtener_paciente(paciente_id):
    """Obtiene la ficha completa de un paciente."""
    data = cargar_pacientes()
    paciente = next((p for p in data['pacientes'] if p['id'] == paciente_id), None)
    
    if paciente:
        # Calcular edad automáticamente desde fecha de nacimiento
        if paciente.get('fecha_nacimiento'):
            paciente['edad_calculada'] = calcular_edad(paciente['fecha_nacimiento'])
        else:
            paciente['edad_calculada'] = paciente.get('edad', 'N/A')
        
        # Obtener historial de consultas
        consultas_data = cargar_consultas()
        historial = []
        for consulta_id in paciente.get('historial_consultas', []):
            consulta = next((c for c in consultas_data['consultas'] if c['id'] == consulta_id), None)
            if consulta:
                historial.append({
                    'id': consulta['id'],
                    'fecha': consulta.get('fecha_registro'),
                    'motivo': consulta.get('motivo_consulta', ''),
                    'diagnostico': consulta.get('diagnostico', {}).get('nombre', ''),
                    'doctor': consulta.get('atendido_por', ''),
                    'peso_registrado': consulta.get('peso_paciente', '')
                })
        
        return jsonify({
            'exito': True,
            'paciente': paciente,
            'historial_detallado': historial
        })
    
    return jsonify({'exito': False, 'mensaje': 'Paciente no encontrado'}), 404

@app.route('/api/pacientes/nuevo', methods=['POST'])
def crear_paciente():
    """Crea una nueva ficha de paciente."""
    req_data = request.get_json()
    data = cargar_pacientes()
    
    # Generar nuevo ID
    nuevo_id = data.get('ultimo_id', 0) + 1
    
    # Calcular edad desde fecha de nacimiento
    fecha_nac = req_data.get('fecha_nacimiento', '')
    edad_calc = calcular_edad(fecha_nac) if fecha_nac else req_data.get('edad', '')
    
    # Crear historial de peso inicial
    peso_inicial = req_data.get('peso', '')
    historial_peso = []
    if peso_inicial:
        historial_peso.append({
            'peso': peso_inicial,
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'registrado_por': 'Registro inicial'
        })
    
    nuevo_paciente = {
        'id': nuevo_id,
        'nombre': req_data.get('nombre'),
        'especie': req_data.get('especie'),
        'raza': req_data.get('raza', ''),
        'color': req_data.get('color', ''),
        'sexo': req_data.get('sexo', ''),
        'fecha_nacimiento': fecha_nac,
        'edad': edad_calc,
        'peso': peso_inicial,
        'historial_peso': historial_peso,
        'microchip': req_data.get('microchip', ''),
        'esterilizado': req_data.get('esterilizado', False),
        'alergias': req_data.get('alergias', []),
        'condiciones_cronicas': req_data.get('condiciones_cronicas', []),
        'vacunas': req_data.get('vacunas', []),
        'propietario': {
            'nombre': req_data.get('propietario_nombre', ''),
            'rut': req_data.get('propietario_rut', ''),
            'telefono': req_data.get('propietario_telefono', ''),
            'telefono_alternativo': req_data.get('propietario_telefono_alt', ''),
            'email': req_data.get('propietario_email', ''),
            'direccion': req_data.get('propietario_direccion', '')
        },
        'fecha_registro': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'notas': req_data.get('notas', ''),
        'historial_consultas': []
    }
    
    data['pacientes'].append(nuevo_paciente)
    data['ultimo_id'] = nuevo_id
    guardar_pacientes(data)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Paciente registrado exitosamente',
        'paciente': nuevo_paciente
    })

@app.route('/api/pacientes/<int:paciente_id>', methods=['PUT'])
def actualizar_paciente(paciente_id):
    """Actualiza la ficha de un paciente."""
    req_data = request.get_json()
    data = cargar_pacientes()
    
    for i, p in enumerate(data['pacientes']):
        if p['id'] == paciente_id:
            # Actualizar campos
            if 'nombre' in req_data: p['nombre'] = req_data['nombre']
            if 'especie' in req_data: p['especie'] = req_data['especie']
            if 'raza' in req_data: p['raza'] = req_data['raza']
            if 'color' in req_data: p['color'] = req_data['color']
            if 'sexo' in req_data: p['sexo'] = req_data['sexo']
            if 'fecha_nacimiento' in req_data: p['fecha_nacimiento'] = req_data['fecha_nacimiento']
            if 'edad' in req_data: p['edad'] = req_data['edad']
            if 'peso' in req_data: p['peso'] = req_data['peso']
            if 'microchip' in req_data: p['microchip'] = req_data['microchip']
            if 'esterilizado' in req_data: p['esterilizado'] = req_data['esterilizado']
            if 'alergias' in req_data: p['alergias'] = req_data['alergias']
            if 'condiciones_cronicas' in req_data: p['condiciones_cronicas'] = req_data['condiciones_cronicas']
            if 'notas' in req_data: p['notas'] = req_data['notas']
            
            # Actualizar propietario
            if any(k.startswith('propietario_') for k in req_data):
                if 'propietario_nombre' in req_data: p['propietario']['nombre'] = req_data['propietario_nombre']
                if 'propietario_rut' in req_data: p['propietario']['rut'] = req_data['propietario_rut']
                if 'propietario_telefono' in req_data: p['propietario']['telefono'] = req_data['propietario_telefono']
                if 'propietario_telefono_alt' in req_data: p['propietario']['telefono_alternativo'] = req_data['propietario_telefono_alt']
                if 'propietario_email' in req_data: p['propietario']['email'] = req_data['propietario_email']
                if 'propietario_direccion' in req_data: p['propietario']['direccion'] = req_data['propietario_direccion']
            
            guardar_pacientes(data)
            return jsonify({'exito': True, 'mensaje': 'Paciente actualizado', 'paciente': p})
    
    return jsonify({'exito': False, 'mensaje': 'Paciente no encontrado'}), 404

@app.route('/api/pacientes/<int:paciente_id>/agregar-consulta', methods=['POST'])
def agregar_consulta_paciente(paciente_id):
    """Agrega una consulta al historial del paciente."""
    req_data = request.get_json()
    consulta_id = req_data.get('consulta_id')
    
    data = cargar_pacientes()
    
    for p in data['pacientes']:
        if p['id'] == paciente_id:
            if consulta_id not in p.get('historial_consultas', []):
                if 'historial_consultas' not in p:
                    p['historial_consultas'] = []
                p['historial_consultas'].append(consulta_id)
                guardar_pacientes(data)
            return jsonify({'exito': True, 'mensaje': 'Consulta agregada al historial'})
    
    return jsonify({'exito': False, 'mensaje': 'Paciente no encontrado'}), 404

@app.route('/api/pacientes/<int:paciente_id>/actualizar-peso', methods=['POST'])
def actualizar_peso_paciente(paciente_id):
    """Actualiza el peso del paciente y lo guarda en el historial."""
    req_data = request.get_json()
    nuevo_peso = req_data.get('peso', '')
    registrado_por = req_data.get('registrado_por', 'Sistema')
    
    if not nuevo_peso:
        return jsonify({'exito': False, 'mensaje': 'Debe proporcionar el peso'}), 400
    
    data = cargar_pacientes()
    
    for p in data['pacientes']:
        if p['id'] == paciente_id:
            # Actualizar peso actual
            p['peso'] = nuevo_peso
            
            # Agregar al historial de peso
            if 'historial_peso' not in p:
                p['historial_peso'] = []
            
            p['historial_peso'].append({
                'peso': nuevo_peso,
                'fecha': datetime.now().strftime('%Y-%m-%d'),
                'registrado_por': registrado_por
            })
            
            guardar_pacientes(data)
            
            return jsonify({
                'exito': True,
                'mensaje': 'Peso actualizado',
                'peso_actual': nuevo_peso,
                'historial_peso': p['historial_peso']
            })
    
    return jsonify({'exito': False, 'mensaje': 'Paciente no encontrado'}), 404

@app.route('/api/pacientes/<int:paciente_id>/historial-peso', methods=['GET'])
def obtener_historial_peso(paciente_id):
    """Obtiene el historial de peso de un paciente."""
    data = cargar_pacientes()
    paciente = next((p for p in data['pacientes'] if p['id'] == paciente_id), None)
    
    if paciente:
        return jsonify({
            'exito': True,
            'paciente': paciente['nombre'],
            'peso_actual': paciente.get('peso', 'N/A'),
            'historial': paciente.get('historial_peso', [])
        })
    
    return jsonify({'exito': False, 'mensaje': 'Paciente no encontrado'}), 404

# ============================================
# ENDPOINTS DE ADMINISTRACION DE INVENTARIO
# ============================================

@app.route('/api/admin/alertas-stock', methods=['GET'])
def obtener_alertas_stock():
    """Obtiene alertas de stock bajo, agotado y por vencer."""
    from datetime import datetime, timedelta
    
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    hoy = datetime.now()
    
    alertas = {
        'agotados': [],
        'stock_bajo': [],
        'por_vencer': [],
        'vencidos': [],
        'resumen': {
            'total_productos': len(productos),
            'agotados': 0,
            'stock_bajo': 0,
            'por_vencer': 0,
            'vencidos': 0
        }
    }
    
    # Categorias que son SERVICIOS (no tienen stock fisico)
    CATEGORIAS_SERVICIOS = ['Consultas', 'Examenes', 'Exámenes', 'Procedimientos', 'Cirugias', 'Cirugías', 'Hospital', 'Servicios Extra']
    
    # Contar solo productos fisicos
    productos_fisicos = [p for p in productos if p.get('categoria', '') not in CATEGORIAS_SERVICIOS]
    alertas['resumen']['total_productos'] = len(productos_fisicos)
    
    for prod in productos:
        categoria = prod.get('categoria', '')
        
        # Saltar servicios - no tienen stock fisico
        if categoria in CATEGORIAS_SERVICIOS:
            continue
            
        stock = prod.get('stock', 0)
        stock_minimo = prod.get('stock_minimo', 10)
        
        # Verificar stock
        if stock == 0:
            alertas['agotados'].append({
                'id': prod['id'],
                'nombre': prod['nombre'],
                'categoria': categoria,
                'stock': 0,
                'stock_minimo': stock_minimo,
                'proveedor': prod.get('proveedor', 'N/A')
            })
            alertas['resumen']['agotados'] += 1
        elif stock <= stock_minimo:
            alertas['stock_bajo'].append({
                'id': prod['id'],
                'nombre': prod['nombre'],
                'categoria': categoria,
                'stock': stock,
                'stock_minimo': stock_minimo,
                'proveedor': prod.get('proveedor', 'N/A')
            })
            alertas['resumen']['stock_bajo'] += 1
        
        # Verificar vencimiento (solo productos fisicos)
        if categoria not in CATEGORIAS_SERVICIOS:
            fecha_venc_str = prod.get('fecha_vencimiento')
            if fecha_venc_str:
                try:
                    fecha_venc = datetime.strptime(fecha_venc_str, '%Y-%m-%d')
                    dias_para_vencer = (fecha_venc - hoy).days
                    
                    if dias_para_vencer < 0:
                        alertas['vencidos'].append({
                            'id': prod['id'],
                            'nombre': prod['nombre'],
                            'categoria': categoria,
                            'fecha_vencimiento': fecha_venc_str,
                            'dias_vencido': abs(dias_para_vencer),
                            'stock': stock,
                            'lote': prod.get('lote', 'N/A')
                        })
                        alertas['resumen']['vencidos'] += 1
                    elif dias_para_vencer <= 60:
                        alertas['por_vencer'].append({
                            'id': prod['id'],
                            'nombre': prod['nombre'],
                            'categoria': categoria,
                            'fecha_vencimiento': fecha_venc_str,
                            'dias_para_vencer': dias_para_vencer,
                            'stock': stock,
                            'lote': prod.get('lote', 'N/A')
                        })
                        alertas['resumen']['por_vencer'] += 1
                except:
                    pass
    
    # Ordenar
    alertas['por_vencer'].sort(key=lambda x: x['dias_para_vencer'])
    alertas['vencidos'].sort(key=lambda x: x['dias_vencido'], reverse=True)
    alertas['stock_bajo'].sort(key=lambda x: x['stock'])
    
    return jsonify({
        'exito': True,
        'alertas': alertas
    })

@app.route('/api/admin/productos', methods=['GET'])
def listar_productos_admin():
    """Lista todos los productos con filtros para administracion."""
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    # Filtros
    categoria = request.args.get('categoria', '')
    busqueda = request.args.get('q', '')
    solo_agotados = request.args.get('agotados', 'false').lower() == 'true'
    solo_stock_bajo = request.args.get('stock_bajo', 'false').lower() == 'true'
    
    resultados = []
    for prod in productos:
        # Filtrar por categoria
        if categoria and prod.get('categoria', '') != categoria:
            continue
        
        # Filtrar por busqueda
        if busqueda:
            busqueda_norm = normalizar_texto(busqueda)
            nombre_norm = normalizar_texto(prod.get('nombre', ''))
            if busqueda_norm not in nombre_norm:
                continue
        
        # Filtrar por stock
        stock = prod.get('stock', 0)
        stock_minimo = prod.get('stock_minimo', 10)
        
        if solo_agotados and stock != 0:
            continue
        if solo_stock_bajo and stock > stock_minimo:
            continue
        
        resultados.append(prod)
    
    return jsonify({
        'exito': True,
        'productos': resultados,
        'total': len(resultados)
    })

@app.route('/api/admin/categorias', methods=['GET'])
def listar_categorias():
    """Lista todas las categorias de productos."""
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    categorias = {}
    for prod in productos:
        cat = prod.get('categoria', 'Sin categoria')
        if cat not in categorias:
            categorias[cat] = {'total': 0, 'agotados': 0, 'stock_bajo': 0}
        categorias[cat]['total'] += 1
        if prod.get('stock', 0) == 0:
            categorias[cat]['agotados'] += 1
        elif prod.get('stock', 0) <= prod.get('stock_minimo', 10):
            categorias[cat]['stock_bajo'] += 1
    
    return jsonify({
        'exito': True,
        'categorias': [{'nombre': k, **v} for k, v in sorted(categorias.items())]
    })

@app.route('/api/admin/producto/<int:producto_id>', methods=['GET', 'PUT'])
def gestionar_producto(producto_id):
    """Obtiene o actualiza un producto."""
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    producto_idx = next((i for i, p in enumerate(productos) if p['id'] == producto_id), None)
    
    if producto_idx is None:
        return jsonify({'exito': False, 'mensaje': 'Producto no encontrado'}), 404
    
    if request.method == 'GET':
        return jsonify({'exito': True, 'producto': productos[producto_idx]})
    
    # PUT - Actualizar producto
    datos = request.get_json()
    producto = productos[producto_idx]
    
    # Campos actualizables
    campos_permitidos = ['nombre', 'precio_unitario', 'stock', 'stock_minimo', 
                         'proveedor', 'categoria', 'lote', 'fecha_vencimiento',
                         'codigo_barras', 'presentacion', 'unidad']
    
    for campo in campos_permitidos:
        if campo in datos:
            producto[campo] = datos[campo]
    
    # Guardar
    guardar_inventario(inventario)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Producto actualizado',
        'producto': producto
    })

@app.route('/api/admin/producto/nuevo', methods=['POST'])
def crear_producto():
    """Crea un nuevo producto en el inventario."""
    datos = request.get_json()
    
    campos_requeridos = ['nombre', 'categoria', 'precio_unitario']
    for campo in campos_requeridos:
        if campo not in datos:
            return jsonify({'exito': False, 'mensaje': f'Campo requerido: {campo}'}), 400
    
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    # Generar nuevo ID
    nuevo_id = max((p['id'] for p in productos), default=0) + 1
    
    nuevo_producto = {
        'id': nuevo_id,
        'nombre': datos['nombre'],
        'categoria': datos['categoria'],
        'precio_unitario': datos['precio_unitario'],
        'stock': datos.get('stock', 0),
        'stock_minimo': datos.get('stock_minimo', 10),
        'punto_venta': datos.get('punto_venta', True),
        'es_servicio': datos.get('es_servicio', False),
        'proveedor': datos.get('proveedor', ''),
        'unidad': datos.get('unidad', 'unidades'),
        'presentacion': datos.get('presentacion', ''),
        'codigo_barras': datos.get('codigo_barras', ''),
        'lote': datos.get('lote', ''),
        'fecha_vencimiento': datos.get('fecha_vencimiento', '')
    }
    
    productos.append(nuevo_producto)
    guardar_inventario(inventario)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Producto creado',
        'producto': nuevo_producto
    })

@app.route('/api/admin/producto/buscar-codigo', methods=['GET'])
def buscar_por_codigo_barras():
    """Busca un producto por codigo de barras."""
    codigo = request.args.get('codigo', '')
    
    if not codigo:
        return jsonify({'exito': False, 'mensaje': 'Codigo de barras requerido'}), 400
    
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    producto = next((p for p in productos if p.get('codigo_barras') == codigo), None)
    
    if producto:
        return jsonify({'exito': True, 'encontrado': True, 'producto': producto})
    else:
        return jsonify({'exito': True, 'encontrado': False, 'mensaje': 'Producto no encontrado'})

@app.route('/api/admin/ingreso-stock', methods=['POST'])
def ingresar_stock():
    """Registra ingreso de stock con lote y vencimiento."""
    datos = request.get_json()
    
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad', 0)
    lote = datos.get('lote', '')
    fecha_vencimiento = datos.get('fecha_vencimiento', '')
    
    if not producto_id or cantidad <= 0:
        return jsonify({'exito': False, 'mensaje': 'ID de producto y cantidad requeridos'}), 400
    
    inventario = cargar_inventario()
    productos = inventario.get('medicamentos', [])
    
    producto_idx = next((i for i, p in enumerate(productos) if p['id'] == producto_id), None)
    
    if producto_idx is None:
        return jsonify({'exito': False, 'mensaje': 'Producto no encontrado'}), 404
    
    producto = productos[producto_idx]
    stock_anterior = producto.get('stock', 0)
    
    # Actualizar stock
    producto['stock'] = stock_anterior + cantidad
    
    # Actualizar lote y vencimiento si se proporcionan
    if lote:
        producto['lote'] = lote
    if fecha_vencimiento:
        producto['fecha_vencimiento'] = fecha_vencimiento
    
    guardar_inventario(inventario)
    
    return jsonify({
        'exito': True,
        'mensaje': f'Stock actualizado: {stock_anterior} -> {producto["stock"]}',
        'producto': producto
    })

def guardar_inventario(inventario):
    """Guarda el inventario en el archivo JSON."""
    ruta_archivo = os.path.join(os.path.dirname(__file__), 'inventario.json')
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        json.dump(inventario, f, ensure_ascii=False, indent=2)

# ============================================
# RUTA PRINCIPAL
# ============================================

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'mensaje': 'BetterDoctor API - Sistema Veterinario',
        'version': '7.0',
        'descripcion': 'Sistema de Gestión Veterinaria con diagnóstico asistido',
        'endpoints': {
            'autenticacion': ['/api/login', '/api/logout', '/api/session'],
            'pacientes': ['/api/pacientes', '/api/pacientes/buscar', '/api/pacientes/nuevo', '/api/pacientes/<id>'],
            'consultas': ['/api/consultas', '/api/consultas/pendientes', '/api/consultas/por-cobrar', '/api/consultas/nueva', '/api/consultas/<id>/diagnostico', '/api/consultas/<id>/receta', '/api/consultas/<id>/boleta'],
            'diagnostico': ['/diagnosticar', '/diagnosticos', '/sintomas', '/api/sintomas/buscar'],
            'inventario': ['/api/inventario', '/api/inventario/alertas', '/api/inventario/agregar', '/api/inventario/<id>/actualizar-stock'],
            'medicamentos': ['/api/medicamentos/por-diagnostico/<nombre>', '/api/medicamentos/buscar-disponibles'],
            'razas': ['/api/razas', '/api/razas/<especie>', '/api/razas/buscar', '/api/razas/<especie>/<id>']
        },
        'estadisticas': {
            'diagnosticos_disponibles': len(cargar_datos()),
            'sintomas_unicos': len(set(s for d in cargar_datos() for s in d.get('sintomas', []))),
            'razas_perros': len(cargar_razas().get('perros', [])),
            'razas_gatos': len(cargar_razas().get('gatos', []))
        }
    })


# ================== MOVIMIENTOS DE STOCK ==================

def cargar_movimientos():
    """Carga los movimientos de stock."""
    ruta = os.path.join(os.path.dirname(__file__), 'movimientos_stock.json')
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'movimientos': [], 'ultimo_id': 0}

def guardar_movimientos(data):
    """Guarda los movimientos de stock."""
    ruta = os.path.join(os.path.dirname(__file__), 'movimientos_stock.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/api/admin/movimientos', methods=['GET'])
def obtener_movimientos():
    """Obtiene el historial de movimientos de stock."""
    movimientos_data = cargar_movimientos()
    movimientos = movimientos_data.get('movimientos', [])
    
    # Filtros opcionales
    tipo = request.args.get('tipo', '')
    fecha_desde = request.args.get('desde', '')
    fecha_hasta = request.args.get('hasta', '')
    producto = request.args.get('producto', '')
    limite = request.args.get('limite', 50, type=int)
    
    # Aplicar filtros
    if tipo:
        movimientos = [m for m in movimientos if m.get('tipo') == tipo]
    
    if fecha_desde:
        movimientos = [m for m in movimientos if m.get('fecha', '') >= fecha_desde]
    
    if fecha_hasta:
        movimientos = [m for m in movimientos if m.get('fecha', '')[:10] <= fecha_hasta]
    
    if producto:
        producto_lower = producto.lower()
        movimientos = [m for m in movimientos if producto_lower in m.get('producto_nombre', '').lower()]
    
    # Ordenar por fecha descendente
    movimientos = sorted(movimientos, key=lambda x: x.get('fecha', ''), reverse=True)
    
    # Limitar resultados
    movimientos = movimientos[:limite]
    
    # Calcular resumen
    resumen = {
        'total_ingresos': sum(1 for m in movimientos if m.get('tipo') == 'ingreso'),
        'total_salidas': sum(1 for m in movimientos if m.get('tipo') == 'salida'),
        'total_ajustes': sum(1 for m in movimientos if m.get('tipo') == 'ajuste'),
        'total_devoluciones': sum(1 for m in movimientos if m.get('tipo') == 'devolucion')
    }
    
    return jsonify({
        'exito': True,
        'movimientos': movimientos,
        'total': len(movimientos),
        'resumen': resumen
    })


@app.route('/api/admin/movimiento', methods=['POST'])
def registrar_movimiento():
    """Registra un nuevo movimiento de stock."""
    from datetime import datetime
    
    datos = request.get_json()
    movimientos_data = cargar_movimientos()
    
    nuevo_id = movimientos_data.get('ultimo_id', 0) + 1
    
    movimiento = {
        'id': nuevo_id,
        'fecha': datetime.now().isoformat(),
        'tipo': datos.get('tipo', 'ingreso'),
        'producto_id': datos.get('producto_id'),
        'producto_nombre': datos.get('producto_nombre', ''),
        'categoria': datos.get('categoria', ''),
        'cantidad': datos.get('cantidad', 0),
        'stock_anterior': datos.get('stock_anterior', 0),
        'stock_nuevo': datos.get('stock_nuevo', 0),
        'lote': datos.get('lote', ''),
        'fecha_vencimiento': datos.get('fecha_vencimiento', ''),
        'proveedor': datos.get('proveedor', ''),
        'documento': datos.get('documento', ''),
        'usuario': datos.get('usuario', 'sistema'),
        'observacion': datos.get('observacion', '')
    }
    
    # Agregar campos opcionales según tipo
    if datos.get('tipo') == 'salida':
        movimiento['consulta_id'] = datos.get('consulta_id')
        movimiento['paciente'] = datos.get('paciente', '')
        movimiento['veterinario'] = datos.get('veterinario', '')
    
    movimientos_data['movimientos'].append(movimiento)
    movimientos_data['ultimo_id'] = nuevo_id
    
    guardar_movimientos(movimientos_data)
    
    return jsonify({
        'exito': True,
        'mensaje': 'Movimiento registrado correctamente',
        'movimiento': movimiento
    })


if __name__ == '__main__':
    print("=" * 50)
    print("[+] BetterDoctor API v6.0")
    print("=" * 50)
    print("[*] http://localhost:5000")
    print("\n[*] Usuarios de prueba:")
    print("    - Veterinario: dr.martinez / vet2024")
    print("    - Admin: admin / admin2024")
    print("    - Recepcion: recepcion / recep2024")
    print("=" * 50)
    app.run(debug=True, port=5000, host='0.0.0.0')
