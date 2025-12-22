# =============================================================================
# BOT API - Módulo de integración para n8n / IA
# =============================================================================
# Este módulo expone endpoints READ-ONLY para que un bot externo consulte:
#   - Inventario de medicamentos/productos
#   - Diagnósticos sugeridos (NO definitivos, solo orientativos)
#
# IMPORTANTE:
#   - Este módulo NO escribe en los archivos JSON
#   - Solo consulta datos existentes del sistema
#   - Los diagnósticos son SUGERENCIAS, no diagnósticos definitivos
# =============================================================================

from flask import Blueprint, request, jsonify
import json
import os
import re
import unicodedata

# Crear Blueprint
bot_api = Blueprint("bot_api", __name__)

# =============================================================================
# FUNCIONES DE UTILIDAD (propias del módulo, sin dependencias de app.py)
# =============================================================================

def _get_base_path():
    """Obtiene la ruta base del directorio backend."""
    return os.path.dirname(os.path.abspath(__file__))

def _load_json(filename, default=None):
    """Carga un archivo JSON de forma segura."""
    if default is None:
        default = {}
    try:
        filepath = os.path.join(_get_base_path(), filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[bot_api] Error cargando {filename}: {e}")
        return default

def _normalizar_texto(texto):
    """Normaliza texto para búsquedas (quita acentos, minúsculas, espacios extra)."""
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'\s+', ' ', texto)
    return texto


def _generar_diagnostico_preliminar(sintomas, especie=""):
    """
    Genera un diagnóstico preliminar basado en los síntomas reportados.
    Este es solo orientativo para que el doctor tenga información previa.
    """
    if not sintomas:
        return {
            "posibles_condiciones": [],
            "nivel_urgencia": "por_evaluar",
            "recomendaciones": ["Evaluación general requerida"],
            "nota": "Sin síntomas reportados - requiere evaluación presencial"
        }
    
    # Normalizar síntomas para búsqueda
    sintomas_norm = [_normalizar_texto(s) for s in sintomas]
    sintomas_texto = " ".join(sintomas_norm)
    
    # Base de conocimiento de síntomas -> condiciones
    SINTOMAS_CONDICIONES = {
        # Urgencias críticas
        "convulsion": {"condicion": "Posible epilepsia/intoxicación", "urgencia": "critica", "accion": "Atención INMEDIATA"},
        "envenenamiento": {"condicion": "Intoxicación", "urgencia": "critica", "accion": "Lavado gástrico urgente"},
        "veneno": {"condicion": "Intoxicación", "urgencia": "critica", "accion": "Lavado gástrico urgente"},
        "atropello": {"condicion": "Trauma múltiple", "urgencia": "critica", "accion": "Evaluación traumatológica"},
        "accidente": {"condicion": "Trauma", "urgencia": "critica", "accion": "Evaluación de urgencia"},
        "sangre": {"condicion": "Hemorragia", "urgencia": "alta", "accion": "Control de sangrado"},
        "no respira": {"condicion": "Insuficiencia respiratoria", "urgencia": "critica", "accion": "Oxigenoterapia urgente"},
        "desmayo": {"condicion": "Síncope", "urgencia": "critica", "accion": "Evaluación cardíaca"},
        "paralisis": {"condicion": "Lesión neurológica", "urgencia": "critica", "accion": "Evaluación neurológica"},
        
        # Urgencias altas
        "vomito con sangre": {"condicion": "Hemorragia digestiva", "urgencia": "alta", "accion": "Endoscopia/Ecografía"},
        "diarrea con sangre": {"condicion": "Enteritis hemorrágica", "urgencia": "alta", "accion": "Hidratación IV"},
        "fiebre alta": {"condicion": "Infección sistémica", "urgencia": "alta", "accion": "Antibioterapia"},
        "no come hace dias": {"condicion": "Anorexia prolongada", "urgencia": "alta", "accion": "Estudios sanguíneos"},
        "abdomen hinchado": {"condicion": "Posible torsión/obstrucción", "urgencia": "alta", "accion": "Radiografía urgente"},
        "dificultad respirar": {"condicion": "Distrés respiratorio", "urgencia": "alta", "accion": "Oxigenoterapia"},
        
        # Gastrointestinales
        "vomito": {"condicion": "Gastritis/Gastroenteritis", "urgencia": "media", "accion": "Antiemético + dieta blanda"},
        "vomitos": {"condicion": "Gastritis/Gastroenteritis", "urgencia": "media", "accion": "Antiemético + dieta blanda"},
        "diarrea": {"condicion": "Enteritis", "urgencia": "media", "accion": "Probióticos + hidratación"},
        "no come": {"condicion": "Inapetencia", "urgencia": "media", "accion": "Evaluación general"},
        "come pasto": {"condicion": "Malestar gástrico", "urgencia": "baja", "accion": "Observación"},
        
        # Dermatológicos
        "picazon": {"condicion": "Dermatitis/Alergia", "urgencia": "baja", "accion": "Antihistamínico"},
        "rascado": {"condicion": "Dermatitis/Parásitos", "urgencia": "baja", "accion": "Revisión de piel"},
        "caida pelo": {"condicion": "Alopecia", "urgencia": "baja", "accion": "Raspado cutáneo"},
        "sarna": {"condicion": "Sarna", "urgencia": "media", "accion": "Antiparasitario"},
        "pulgas": {"condicion": "Pulicosis", "urgencia": "baja", "accion": "Desparasitación externa"},
        "garrapatas": {"condicion": "Infestación por garrapatas", "urgencia": "media", "accion": "Remoción + antiparasitario"},
        
        # Oftalmológicos
        "ojo rojo": {"condicion": "Conjuntivitis", "urgencia": "media", "accion": "Colirio antibiótico"},
        "lagrimeo": {"condicion": "Irritación ocular", "urgencia": "baja", "accion": "Evaluación oftálmica"},
        "legana": {"condicion": "Infección ocular", "urgencia": "media", "accion": "Colirio + limpieza"},
        
        # Otológicos
        "oido": {"condicion": "Otitis", "urgencia": "media", "accion": "Otoscopía + gotas óticas"},
        "sacude cabeza": {"condicion": "Otitis/Cuerpo extraño", "urgencia": "media", "accion": "Revisión de oídos"},
        "mal olor oreja": {"condicion": "Otitis", "urgencia": "media", "accion": "Limpieza + tratamiento"},
        
        # Musculoesqueléticos
        "cojea": {"condicion": "Claudicación", "urgencia": "media", "accion": "Evaluación traumatológica"},
        "cojera": {"condicion": "Claudicación", "urgencia": "media", "accion": "Radiografía"},
        "no camina": {"condicion": "Paresia/Dolor severo", "urgencia": "alta", "accion": "Evaluación neurológica"},
        "dolor pata": {"condicion": "Trauma/Artritis", "urgencia": "media", "accion": "Analgésico + radiografía"},
        
        # Urinarios
        "orina sangre": {"condicion": "Hematuria - Cistitis/Cálculos", "urgencia": "alta", "accion": "Urianálisis + ecografía"},
        "no orina": {"condicion": "Obstrucción urinaria", "urgencia": "critica", "accion": "Sondaje urgente"},
        "orina mucho": {"condicion": "Poliuria", "urgencia": "media", "accion": "Perfil renal"},
        
        # Respiratorios
        "tos": {"condicion": "Traqueobronquitis", "urgencia": "media", "accion": "Antitusígeno + radiografía"},
        "estornudo": {"condicion": "Rinitis", "urgencia": "baja", "accion": "Observación"},
        "mocos": {"condicion": "Infección respiratoria", "urgencia": "media", "accion": "Antibiótico"},
        
        # Comportamentales
        "decaido": {"condicion": "Letargia - múltiples causas", "urgencia": "media", "accion": "Hemograma + perfil"},
        "triste": {"condicion": "Depresión/Dolor", "urgencia": "media", "accion": "Evaluación general"},
        "agresivo": {"condicion": "Dolor/Estrés", "urgencia": "media", "accion": "Evaluación comportamental"},
        
        # Preventivos
        "vacuna": {"condicion": "Control preventivo", "urgencia": "baja", "accion": "Esquema de vacunación"},
        "desparasitar": {"condicion": "Control preventivo", "urgencia": "baja", "accion": "Antiparasitario"},
        "control": {"condicion": "Chequeo general", "urgencia": "baja", "accion": "Examen físico completo"},
        "certificado": {"condicion": "Trámite administrativo", "urgencia": "baja", "accion": "Documentación"}
    }
    
    # Analizar síntomas
    condiciones_encontradas = []
    urgencia_maxima = "baja"
    acciones = []
    
    PRIORIDAD_URGENCIA = {"critica": 4, "alta": 3, "media": 2, "baja": 1, "por_evaluar": 0}
    
    for sintoma_clave, info in SINTOMAS_CONDICIONES.items():
        if sintoma_clave in sintomas_texto:
            condiciones_encontradas.append(info["condicion"])
            acciones.append(info["accion"])
            if PRIORIDAD_URGENCIA.get(info["urgencia"], 0) > PRIORIDAD_URGENCIA.get(urgencia_maxima, 0):
                urgencia_maxima = info["urgencia"]
    
    # Eliminar duplicados
    condiciones_encontradas = list(set(condiciones_encontradas))
    acciones = list(set(acciones))
    
    return {
        "posibles_condiciones": condiciones_encontradas[:5],
        "nivel_urgencia": urgencia_maxima,
        "recomendaciones": acciones[:5],
        "sintomas_analizados": sintomas,
        "nota": "Diagnóstico preliminar automático - Requiere confirmación veterinaria"
    }
    return texto

# =============================================================================
# ENDPOINTS DEL BOT
# =============================================================================

@bot_api.route("/api/bot/inventario", methods=["GET"])
def buscar_inventario():
    """
    Busca productos/medicamentos en el inventario.
    
    Query params:
        q (str): Término de búsqueda (nombre del producto)
        categoria (str, opcional): Filtrar por categoría
        solo_disponibles (bool, opcional): Solo productos con stock > 0
    
    Returns:
        JSON con lista de productos que coinciden
    """
    q = _normalizar_texto(request.args.get("q", ""))
    categoria = _normalizar_texto(request.args.get("categoria", ""))
    solo_disponibles = request.args.get("solo_disponibles", "false").lower() == "true"
    
    # Cargar inventario (estructura: {"medicamentos": [...], ...})
    inventario = _load_json("inventario.json", default={"medicamentos": []})
    medicamentos = inventario.get("medicamentos", [])
    
    resultados = []
    
    for med in medicamentos:
        nombre_norm = _normalizar_texto(med.get("nombre", ""))
        cat_norm = _normalizar_texto(med.get("categoria", ""))
        
        # Filtrar por término de búsqueda
        if q and q not in nombre_norm:
            continue
        
        # Filtrar por categoría
        if categoria and categoria not in cat_norm:
            continue
        
        # Filtrar por disponibilidad
        stock = med.get("stock", 0)
        if solo_disponibles and stock <= 0:
            continue
        
        # Determinar estado de stock
        stock_minimo = med.get("stock_minimo", 5)
        if stock == 0:
            estado_stock = "agotado"
        elif stock <= stock_minimo:
            estado_stock = "bajo"
        else:
            estado_stock = "disponible"
        
        resultados.append({
            "id": med.get("id"),
            "nombre": med.get("nombre"),
            "categoria": med.get("categoria", ""),
            "presentacion": med.get("presentacion", ""),
            "stock": stock,
            "stock_minimo": stock_minimo,
            "estado_stock": estado_stock,
            "precio_unitario": med.get("precio_unitario", 0),
            "unidad": med.get("unidad", "unidades")
        })
    
    # Ordenar: disponibles primero, luego por nombre
    resultados.sort(key=lambda x: (
        0 if x["estado_stock"] == "disponible" else (1 if x["estado_stock"] == "bajo" else 2),
        x["nombre"]
    ))
    
    return jsonify({
        "exito": True,
        "query": request.args.get("q", ""),
        "resultados": resultados[:50],
        "total": len(resultados),
        "mensaje": "Resultados de búsqueda en inventario"
    })


@bot_api.route("/api/bot/diagnostico", methods=["POST"])
def sugerir_diagnostico():
    """
    Sugiere diagnósticos basados en síntomas (SOLO ORIENTATIVO).
    
    Body JSON:
        sintomas (str o list): Síntomas separados por coma o lista
        especie (str, opcional): "perro", "gato", etc.
    
    Returns:
        JSON con lista de diagnósticos sugeridos (máximo 5)
    
    ADVERTENCIA:
        Los resultados son SUGERENCIAS para orientar al veterinario.
        NO son diagnósticos definitivos. El diagnóstico final lo hace el profesional.
    """
    data = request.get_json() or {}
    
    # Procesar síntomas (puede venir como string o lista)
    sintomas_raw = data.get("sintomas", "")
    if isinstance(sintomas_raw, list):
        sintomas_lista = [_normalizar_texto(s) for s in sintomas_raw if s]
    else:
        sintomas_lista = [_normalizar_texto(s.strip()) for s in str(sintomas_raw).split(",") if s.strip()]
    
    especie = _normalizar_texto(data.get("especie", ""))
    
    if not sintomas_lista:
        return jsonify({
            "exito": False,
            "error": "Debe proporcionar al menos un síntoma",
            "sugerencias": []
        }), 400
    
    # Cargar diagnósticos
    diagnosticos = _load_json("diagnosticos_veterinarios.json", default=[])
    
    sugerencias = []
    
    for dx in diagnosticos:
        # Filtrar por especie si se especifica
        if especie:
            especies_dx = [_normalizar_texto(e) for e in dx.get("especie", [])]
            if especie not in especies_dx and not any(especie in e for e in especies_dx):
                continue
        
        # Obtener síntomas del diagnóstico
        sintomas_dx = [_normalizar_texto(s) for s in dx.get("sintomas", [])]
        
        # Calcular coincidencias
        coincidencias = 0
        sintomas_coincidentes = []
        
        for sintoma_entrada in sintomas_lista:
            for sintoma_dx in sintomas_dx:
                # Coincidencia exacta o parcial
                if sintoma_entrada == sintoma_dx:
                    coincidencias += 1
                    if dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)] not in sintomas_coincidentes:
                        sintomas_coincidentes.append(dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)])
                    break
                elif sintoma_entrada in sintoma_dx or sintoma_dx in sintoma_entrada:
                    coincidencias += 0.7
                    if dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)] not in sintomas_coincidentes:
                        sintomas_coincidentes.append(dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)])
                    break
                else:
                    # Buscar palabras en común
                    palabras_entrada = set(sintoma_entrada.split())
                    palabras_dx = set(sintoma_dx.split())
                    comunes = palabras_entrada & palabras_dx
                    # Excluir palabras muy cortas o comunes
                    comunes = {p for p in comunes if len(p) > 3 and p not in {'de', 'la', 'el', 'en', 'los', 'las'}}
                    if len(comunes) >= 1:
                        coincidencias += 0.3
                        if dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)] not in sintomas_coincidentes:
                            sintomas_coincidentes.append(dx.get("sintomas", [])[sintomas_dx.index(sintoma_dx)])
                        break
        
        # Solo incluir si hay al menos una coincidencia significativa
        if coincidencias >= 0.5:
            porcentaje = min(100, (coincidencias / len(sintomas_lista)) * 100)
            
            sugerencias.append({
                "id": dx.get("id"),
                "nombre": dx.get("nombre"),
                "descripcion": dx.get("descripcion", ""),
                "gravedad": dx.get("gravedad", ""),
                "urgencia": dx.get("urgencia", ""),
                "sintomas_coincidentes": sintomas_coincidentes,
                "porcentaje_coincidencia": round(porcentaje, 1),
                "tratamiento_sugerido": dx.get("tratamiento", ""),
                "especies_afectadas": dx.get("especie", [])
            })
    
    # Ordenar por porcentaje de coincidencia (mayor a menor)
    sugerencias.sort(key=lambda x: x["porcentaje_coincidencia"], reverse=True)
    
    return jsonify({
        "exito": True,
        "sintomas_recibidos": sintomas_lista,
        "especie": data.get("especie", "no especificada"),
        "sugerencias": sugerencias[:5],
        "total_encontrados": len(sugerencias),
        "advertencia": "IMPORTANTE: Estas son SUGERENCIAS orientativas. El diagnóstico definitivo debe ser realizado por un médico veterinario."
    })


@bot_api.route("/api/bot/estado", methods=["GET"])
def estado_bot():
    """
    Endpoint de verificación de estado del módulo bot.
    Útil para que n8n verifique que el servicio está activo.
    """
    archivos_ok = {
        "inventario": os.path.exists(os.path.join(_get_base_path(), "inventario.json")),
        "diagnosticos": os.path.exists(os.path.join(_get_base_path(), "diagnosticos_veterinarios.json")),
        "consultas": os.path.exists(os.path.join(_get_base_path(), "consultas.json"))
    }
    
    return jsonify({
        "exito": True,
        "modulo": "bot_api",
        "version": "1.1",
        "estado": "activo",
        "archivos": archivos_ok,
        "endpoints": [
            {"ruta": "/api/bot/inventario", "metodo": "GET", "descripcion": "Buscar productos en inventario"},
            {"ruta": "/api/bot/diagnostico", "metodo": "POST", "descripcion": "Triage: sugerir diagnósticos por síntomas"},
            {"ruta": "/api/bot/agendar-cita", "metodo": "POST", "descripcion": "Agendar cita (emergencia o especialidad)"},
            {"ruta": "/api/bot/estado", "metodo": "GET", "descripcion": "Verificar estado del módulo"}
        ]
    })


# =============================================================================
# ENDPOINT DE AGENDAMIENTO DE CITAS
# =============================================================================

@bot_api.route("/api/bot/agendar-cita", methods=["POST"])
def agendar_cita():
    """
    Agenda una cita veterinaria basada en el triage previo.
    
    Body JSON:
        nombre_mascota (str): Nombre del paciente
        especie (str): "perro", "gato", etc.
        propietario (str): Nombre del dueño
        telefono (str): Teléfono de contacto
        sintomas (str): Síntomas reportados
        urgencia (str): "emergencia", "urgente", "normal", "especialidad"
        tipo_cita (str, opcional): "consulta_general", "emergencia", "especialidad"
        especialidad (str, opcional): Si es cita de especialidad, cuál
        notas (str, opcional): Notas adicionales
    
    Returns:
        JSON con confirmación de cita y número de ticket
    
    Lógica de Triage:
        - urgencia="emergencia" → Cita inmediata, prioridad máxima
        - urgencia="urgente" → Cita en el día
        - urgencia="normal" → Cita programable
        - urgencia="especialidad" → Derivación a especialista
    """
    from datetime import datetime
    
    data = request.get_json() or {}
    
    # Validar campos requeridos
    campos_requeridos = ["nombre_mascota", "propietario", "telefono"]
    campos_faltantes = [c for c in campos_requeridos if not data.get(c)]
    
    if campos_faltantes:
        return jsonify({
            "exito": False,
            "error": f"Campos requeridos faltantes: {', '.join(campos_faltantes)}",
            "campos_requeridos": campos_requeridos
        }), 400
    
    # Determinar tipo de cita según urgencia
    urgencia = data.get("urgencia", "normal").lower()
    tipo_cita = data.get("tipo_cita", "")
    
    # Mapeo de urgencia a tipo de consulta y prioridad
    MAPEO_URGENCIA = {
        "emergencia": {"tipo": "emergencia", "prioridad": 1, "tiempo_espera": "Inmediato"},
        "critica": {"tipo": "emergencia", "prioridad": 1, "tiempo_espera": "Inmediato"},
        "urgente": {"tipo": "urgente", "prioridad": 2, "tiempo_espera": "Hoy"},
        "alta": {"tipo": "urgente", "prioridad": 2, "tiempo_espera": "Hoy"},
        "especialidad": {"tipo": "especialidad", "prioridad": 3, "tiempo_espera": "Programar"},
        "normal": {"tipo": "general", "prioridad": 4, "tiempo_espera": "Programar"},
        "baja": {"tipo": "general", "prioridad": 5, "tiempo_espera": "Programar"}
    }
    
    config_urgencia = MAPEO_URGENCIA.get(urgencia, MAPEO_URGENCIA["normal"])
    
    if not tipo_cita:
        tipo_cita = config_urgencia["tipo"]
    
    # Cargar consultas para generar ticket
    consultas_data = _load_json("consultas.json", default={"consultas": [], "ultimo_ticket": 0})
    
    # Cargar pacientes existentes
    pacientes_data = _load_json("pacientes.json", default={"pacientes": []})
    
    # Generar número de ticket
    ultimo_ticket = consultas_data.get("ultimo_ticket", 0) + 1
    año_actual = datetime.now().year
    
    # Prefijo según urgencia
    if config_urgencia["prioridad"] <= 2:
        prefijo = "EMG"  # Emergencia
    elif tipo_cita == "especialidad":
        prefijo = "ESP"  # Especialidad
    else:
        prefijo = "BD"   # Normal
    
    numero_ticket = f"{prefijo}-{año_actual}-{str(ultimo_ticket).zfill(4)}"
    
    # =========================================================================
    # CREAR O ACTUALIZAR FICHA DEL PACIENTE
    # =========================================================================
    
    nombre_mascota = data.get("nombre_mascota", "").strip()
    especie = data.get("especie", "").strip()
    raza = data.get("raza", "").strip()
    propietario = data.get("propietario", "").strip()
    telefono = data.get("telefono", "").strip()
    email = data.get("email", "").strip()
    edad = data.get("edad", "").strip()
    peso = data.get("peso", "").strip()
    sexo = data.get("sexo", "").strip()
    
    # Procesar síntomas
    sintomas_raw = data.get("sintomas", "")
    if isinstance(sintomas_raw, str):
        sintomas_lista = [s.strip() for s in sintomas_raw.split(",") if s.strip()]
    else:
        sintomas_lista = sintomas_raw if sintomas_raw else []
    
    # Buscar si el paciente ya existe (por nombre + teléfono del tutor)
    paciente_existente = None
    paciente_id = None
    
    for p in pacientes_data.get("pacientes", []):
        tutor = p.get("tutor", {})
        if (p.get("nombre", "").lower() == nombre_mascota.lower() and 
            tutor.get("telefono", "").replace(" ", "") == telefono.replace(" ", "")):
            paciente_existente = p
            paciente_id = p.get("id")
            break
    
    if paciente_existente:
        # Actualizar paciente existente con nueva información
        if especie and not paciente_existente.get("especie"):
            paciente_existente["especie"] = especie.capitalize()
        if raza and not paciente_existente.get("raza"):
            paciente_existente["raza"] = raza.capitalize()
        if edad:
            paciente_existente["edad"] = edad
        if peso:
            paciente_existente["peso"] = peso
            # Agregar al historial de peso
            if "historial_peso" not in paciente_existente:
                paciente_existente["historial_peso"] = []
            paciente_existente["historial_peso"].append({
                "peso": peso,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "registrado_por": "Chatbot"
            })
        if sexo:
            paciente_existente["sexo"] = sexo.capitalize()
        if email and not paciente_existente.get("tutor", {}).get("email"):
            paciente_existente["tutor"]["email"] = email
        
        paciente_existente["ultima_visita"] = datetime.now().strftime("%Y-%m-%d")
        
        print(f"[bot_api] Paciente existente actualizado: {nombre_mascota} (ID: {paciente_id})")
    else:
        # Crear nuevo paciente
        nuevo_id = max([p.get("id", 0) for p in pacientes_data.get("pacientes", [])] + [0]) + 1
        paciente_id = nuevo_id
        
        nuevo_paciente = {
            "id": nuevo_id,
            "nombre": nombre_mascota.capitalize() if nombre_mascota else "Sin nombre",
            "especie": especie.capitalize() if especie else "No especificada",
            "raza": raza.capitalize() if raza else "Mestizo",
            "color": data.get("color", ""),
            "sexo": sexo.capitalize() if sexo else "No especificado",
            "fecha_nacimiento": "",
            "edad": edad if edad else "No especificada",
            "peso": peso if peso else "No especificado",
            "microchip": "",
            "esterilizado": None,
            "historial_peso": [{
                "peso": peso,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "registrado_por": "Chatbot"
            }] if peso else [],
            "tutor": {
                "nombre": propietario.title() if propietario else "No especificado",
                "rut": "",
                "telefono": telefono,
                "email": email,
                "direccion": "",
                "comuna": ""
            },
            "alergias": [],
            "condiciones_cronicas": [],
            "vacunas": [],
            "fecha_registro": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "ultima_visita": datetime.now().strftime("%Y-%m-%d"),
            "fallecido": False,
            "historial_consultas": [],
            "origen_registro": "chatbot"
        }
        
        pacientes_data["pacientes"].append(nuevo_paciente)
        paciente_existente = nuevo_paciente
        print(f"[bot_api] Nuevo paciente creado: {nombre_mascota} (ID: {nuevo_id})")
    
    # =========================================================================
    # CREAR LA CONSULTA/CITA
    # =========================================================================
    
    nueva_cita = {
        "id": len(consultas_data.get("consultas", [])) + 1,
        "numero_ticket": numero_ticket,
        "fecha_registro": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "estado": "en_espera",
        "prioridad": config_urgencia["prioridad"],
        "origen": "chatbot",
        "paciente_id": paciente_id,  # Referencia al paciente
        "paciente": {
            "id": paciente_id,
            "nombre": nombre_mascota,
            "especie": especie.capitalize() if especie else paciente_existente.get("especie", ""),
            "raza": raza.capitalize() if raza else paciente_existente.get("raza", ""),
            "edad": edad if edad else paciente_existente.get("edad", ""),
            "peso": peso if peso else paciente_existente.get("peso", ""),
            "sexo": sexo.capitalize() if sexo else paciente_existente.get("sexo", ""),
            "propietario": propietario,
            "telefono": telefono,
            "email": email
        },
        "sintomas_reportados": sintomas_lista,
        "sintomas_texto": sintomas_raw if isinstance(sintomas_raw, str) else ", ".join(sintomas_lista),
        "motivo_consulta": sintomas_raw if sintomas_raw else "Consulta agendada via chatbot",
        "tipo_consulta": tipo_cita,
        "urgencia_reportada": urgencia,
        "especialidad_requerida": data.get("especialidad", ""),
        "notas_chatbot": data.get("notas", ""),
        "registrado_por": "Sistema Chatbot",
        "atendido_por": None,
        "diagnostico_preliminar": _generar_diagnostico_preliminar(sintomas_lista, especie),
        "tratamiento_sugerido": None,
        "cobro": None
    }
    
    # Agregar consulta al historial del paciente
    if "historial_consultas" not in paciente_existente:
        paciente_existente["historial_consultas"] = []
    paciente_existente["historial_consultas"].append(nueva_cita["id"])
    
    # Guardar la cita
    consultas_data["consultas"].append(nueva_cita)
    consultas_data["ultimo_ticket"] = ultimo_ticket
    
    # Escribir archivos
    guardado_ok = True
    try:
        # Guardar consultas
        filepath_consultas = os.path.join(_get_base_path(), "consultas.json")
        with open(filepath_consultas, 'w', encoding='utf-8') as f:
            json.dump(consultas_data, f, ensure_ascii=False, indent=2)
        
        # Guardar pacientes
        filepath_pacientes = os.path.join(_get_base_path(), "pacientes.json")
        with open(filepath_pacientes, 'w', encoding='utf-8') as f:
            json.dump(pacientes_data, f, ensure_ascii=False, indent=2)
            
        print(f"[bot_api] Cita guardada: {numero_ticket}, Paciente ID: {paciente_id}")
    except Exception as e:
        print(f"[bot_api] Error guardando cita/paciente: {e}")
        guardado_ok = False
    
    # Generar mensaje según urgencia
    if config_urgencia["prioridad"] == 1:
        mensaje = f"🚨 EMERGENCIA REGISTRADA. Ticket: {numero_ticket}. Acuda INMEDIATAMENTE a la clínica."
        instrucciones = "Por favor diríjase a urgencias de inmediato. Su caso tiene prioridad máxima."
    elif config_urgencia["prioridad"] == 2:
        mensaje = f"⚠️ Cita URGENTE registrada. Ticket: {numero_ticket}. Será atendido hoy."
        instrucciones = "Por favor acuda a la clínica lo antes posible. Será atendido en el transcurso del día."
    elif tipo_cita == "especialidad":
        mensaje = f"📋 Cita de ESPECIALIDAD registrada. Ticket: {numero_ticket}."
        instrucciones = f"Se ha agendado una cita con el especialista en {data.get('especialidad', 'la especialidad requerida')}. Le contactaremos para confirmar horario."
    else:
        mensaje = f"✅ Cita registrada exitosamente. Ticket: {numero_ticket}."
        instrucciones = "Su cita ha sido registrada. Puede acudir a la clínica en horario de atención o esperar confirmación."
    
    return jsonify({
        "exito": guardado_ok,
        "mensaje": mensaje,
        "cita": {
            "numero_ticket": numero_ticket,
            "tipo": tipo_cita,
            "urgencia": urgencia,
            "prioridad": config_urgencia["prioridad"],
            "tiempo_espera_estimado": config_urgencia["tiempo_espera"],
            "paciente": data.get("nombre_mascota"),
            "especie": data.get("especie", ""),
            "propietario": data.get("propietario"),
            "telefono": data.get("telefono"),
            "email": data.get("email", ""),
            "sintomas": data.get("sintomas", ""),
            "fecha_registro": nueva_cita["fecha_registro"]
        },
        "instrucciones": instrucciones,
        "contacto_emergencias": "(555) 123-4567",
        # Datos para notificaciones (email/WhatsApp)
        "notificacion": {
            "destinatario": data.get("propietario"),
            "telefono": data.get("telefono"),
            "email": data.get("email", ""),
            "asunto": f"🐾 Confirmación de cita #{numero_ticket} - BetterDoctor",
            "mensaje_whatsapp": f"🐾 *BetterDoctor* - Confirmación de Cita\n\n¡Hola {data.get('propietario')}!\n\nTu cita ha sido registrada:\n\n🎫 *Ticket:* {numero_ticket}\n🐾 *Paciente:* {data.get('nombre_mascota')}\n📋 *Motivo:* {data.get('sintomas', 'Consulta general')}\n⏰ *Atención:* {config_urgencia['tiempo_espera']}\n\n{instrucciones}\n\n📍 Clínica Veterinaria BetterDoctor",
            "mensaje_email_html": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #0891b2, #059669); padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="color: white; margin: 0;">🐾 BetterDoctor</h1>
                        <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Clínica Veterinaria</p>
                    </div>
                    <div style="background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0;">
                        <h2 style="color: #0891b2; margin-top: 0;">¡Cita Confirmada! ✅</h2>
                        <p>Estimado/a <strong>{data.get('propietario')}</strong>,</p>
                        <p>Tu cita ha sido registrada exitosamente.</p>
                        <div style="background: white; border-radius: 10px; padding: 20px; margin: 20px 0; border-left: 4px solid #0891b2;">
                            <h3 style="margin-top: 0; color: #334155;">📋 Detalles de la cita</h3>
                            <p><strong>🎫 Ticket:</strong> {numero_ticket}</p>
                            <p><strong>🐾 Paciente:</strong> {data.get('nombre_mascota')} ({data.get('especie', 'Mascota')})</p>
                            <p><strong>📝 Motivo:</strong> {data.get('sintomas', 'Consulta general')}</p>
                            <p><strong>⏰ Atención:</strong> {config_urgencia['tiempo_espera']}</p>
                        </div>
                        <p style="background: #ecfeff; padding: 15px; border-radius: 8px;">{instrucciones}</p>
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                        <p style="color: #64748b; font-size: 14px;">El equipo médico de BetterDoctor estará esperando a {data.get('nombre_mascota')}.</p>
                    </div>
                    <div style="background: #334155; color: white; padding: 20px; border-radius: 0 0 10px 10px; text-align: center;">
                        <p style="margin: 0;">📞 Emergencias: (555) 123-4567</p>
                    </div>
                </div>
            """
        }
    })


# =============================================================================
# ENDPOINT DE RECOMENDACIÓN DE ALIMENTOS
# =============================================================================

@bot_api.route("/api/bot/recomendar-alimento", methods=["POST"])
def recomendar_alimento():
    """
    Recomienda alimentos según la ficha del animal.
    
    Body JSON:
        especie (str): "perro" o "gato"
        edad (str): "cachorro", "adulto", "senior"
        peso (float, opcional): Peso en kg
        condicion_medica (str, opcional): Condición médica del animal
        raza (str, opcional): Raza del animal
        
    Returns:
        JSON con recomendaciones de alimentos
    """
    data = request.get_json() or {}
    
    especie = data.get("especie", "").lower()
    edad = data.get("edad", "adulto").lower()
    peso = data.get("peso", 0)
    condicion = data.get("condicion_medica", "").lower()
    raza = data.get("raza", "").lower()
    
    if not especie:
        return jsonify({
            "exito": False,
            "error": "Debes indicar la especie (perro o gato)"
        }), 400
    
    # Base de datos de alimentos recomendados
    ALIMENTOS_REGULARES = {
        "perro": {
            "cachorro": [
                {"nombre": "Royal Canin Puppy", "descripcion": "Alimento premium para cachorros, favorece desarrollo óseo y muscular", "peso_recomendado": "Todos"},
                {"nombre": "Hills Science Diet Puppy", "descripcion": "Nutrición balanceada para cachorros en crecimiento", "peso_recomendado": "Todos"},
                {"nombre": "ProPlan Puppy", "descripcion": "Con DHA para desarrollo cerebral", "peso_recomendado": "Todos"},
                {"nombre": "Eukanuba Puppy", "descripcion": "Alto contenido proteico para desarrollo muscular", "peso_recomendado": "Todos"}
            ],
            "adulto": [
                {"nombre": "Royal Canin Adult", "descripcion": "Nutrición completa para perros adultos", "peso_recomendado": "Según tamaño"},
                {"nombre": "Hills Science Diet Adult", "descripcion": "Mantención de peso ideal y salud digestiva", "peso_recomendado": "Todos"},
                {"nombre": "ProPlan Adult", "descripcion": "Con probióticos para salud intestinal", "peso_recomendado": "Todos"},
                {"nombre": "Brit Care Adult", "descripcion": "Hipoalergénico, sin granos", "peso_recomendado": "Todos"}
            ],
            "senior": [
                {"nombre": "Royal Canin Senior", "descripcion": "Fórmula para perros mayores de 7 años", "peso_recomendado": "Según tamaño"},
                {"nombre": "Hills Science Diet Senior 7+", "descripcion": "Apoyo articular y control de peso", "peso_recomendado": "Todos"},
                {"nombre": "ProPlan Bright Mind", "descripcion": "Con aceites MCT para función cognitiva", "peso_recomendado": "Todos"}
            ]
        },
        "gato": {
            "cachorro": [
                {"nombre": "Royal Canin Kitten", "descripcion": "Para gatitos hasta 12 meses", "peso_recomendado": "Todos"},
                {"nombre": "Hills Science Diet Kitten", "descripcion": "Desarrollo óptimo y sistema inmune", "peso_recomendado": "Todos"},
                {"nombre": "ProPlan Kitten", "descripcion": "Con calostro para defensas", "peso_recomendado": "Todos"}
            ],
            "adulto": [
                {"nombre": "Royal Canin Adult Indoor", "descripcion": "Para gatos de interior, control de peso", "peso_recomendado": "Todos"},
                {"nombre": "Hills Science Diet Adult", "descripcion": "Salud urinaria y digestiva", "peso_recomendado": "Todos"},
                {"nombre": "ProPlan Adult", "descripcion": "Con omega 3 y 6 para pelaje brillante", "peso_recomendado": "Todos"}
            ],
            "senior": [
                {"nombre": "Royal Canin Senior 12+", "descripcion": "Apoyo renal y articular", "peso_recomendado": "Todos"},
                {"nombre": "Hills Science Diet Senior 11+", "descripcion": "Función cerebral y vitalidad", "peso_recomendado": "Todos"}
            ]
        }
    }
    
    # Alimentos terapéuticos según condición
    ALIMENTOS_TERAPEUTICOS = {
        "gastrointestinal": {
            "perro": ["Royal Canin Gastrointestinal", "Hills I/D Digestive", "ProPlan Gastroenteric"],
            "gato": ["Royal Canin Gastrointestinal Feline", "Hills I/D Feline"]
        },
        "renal": {
            "perro": ["Royal Canin Renal", "Hills K/D Kidney"],
            "gato": ["Royal Canin Renal Feline", "Hills K/D Feline"]
        },
        "hepatico": {
            "perro": ["Royal Canin Hepatic", "Hills L/D Liver"],
            "gato": ["Royal Canin Hepatic Feline"]
        },
        "urinario": {
            "perro": ["Royal Canin Urinary S/O"],
            "gato": ["Royal Canin Urinary S/O Feline", "Hills C/D Urinary"]
        },
        "alergia": {
            "perro": ["Hills Z/D Alergias", "ProPlan HA", "Royal Canin Hypoallergenic"],
            "gato": ["Hills Z/D Feline", "Royal Canin Hypoallergenic Feline"]
        },
        "obesidad": {
            "perro": ["Royal Canin Satiety", "Hills R/D Weight", "Hills Metabolic"],
            "gato": ["Royal Canin Satiety Feline", "Hills Metabolic Feline"]
        },
        "diabetes": {
            "perro": ["Royal Canin Diabetic", "Hills W/D"],
            "gato": ["Royal Canin Diabetic Feline", "Hills M/D Feline"]
        },
        "cardiaco": {
            "perro": ["Royal Canin Cardiac", "Hills H/D Heart"],
            "gato": ["Royal Canin Cardiac Feline"]
        },
        "articular": {
            "perro": ["Royal Canin Mobility", "Hills J/D Joint"],
            "gato": ["Hills J/D Feline"]
        },
        "piel": {
            "perro": ["Royal Canin Dermacomfort", "Hills Derm Defense"],
            "gato": ["Royal Canin Skin Care Feline"]
        }
    }
    
    # Mapeo de condiciones comunes a categorías
    MAPEO_CONDICIONES = {
        "vomito": "gastrointestinal",
        "vomitos": "gastrointestinal",
        "diarrea": "gastrointestinal",
        "gastritis": "gastrointestinal",
        "gastroenteritis": "gastrointestinal",
        "riñon": "renal",
        "renal": "renal",
        "insuficiencia renal": "renal",
        "higado": "hepatico",
        "hepatico": "hepatico",
        "hepatitis": "hepatico",
        "cistitis": "urinario",
        "urinario": "urinario",
        "cristales": "urinario",
        "calculo": "urinario",
        "alergia": "alergia",
        "alergico": "alergia",
        "dermatitis": "piel",
        "picazon": "piel",
        "sobrepeso": "obesidad",
        "obeso": "obesidad",
        "gordo": "obesidad",
        "diabetes": "diabetes",
        "diabetico": "diabetes",
        "corazon": "cardiaco",
        "cardiaco": "cardiaco",
        "artritis": "articular",
        "displasia": "articular",
        "cojera": "articular"
    }
    
    recomendaciones = []
    tipo_recomendacion = "regular"
    
    # Si hay condición médica, buscar alimento terapéutico
    if condicion:
        categoria_condicion = None
        for palabra, categoria in MAPEO_CONDICIONES.items():
            if palabra in condicion:
                categoria_condicion = categoria
                break
        
        if categoria_condicion and categoria_condicion in ALIMENTOS_TERAPEUTICOS:
            alimentos_terapeuticos = ALIMENTOS_TERAPEUTICOS[categoria_condicion].get(especie, [])
            if alimentos_terapeuticos:
                tipo_recomendacion = "terapeutico"
                for alimento in alimentos_terapeuticos:
                    recomendaciones.append({
                        "nombre": alimento,
                        "tipo": "Alimento Terapéutico",
                        "indicacion": f"Recomendado para {categoria_condicion}",
                        "requiere_prescripcion": True
                    })
    
    # Si no hay condición o no se encontró terapéutico, recomendar regular
    if not recomendaciones:
        especie_key = "perro" if "perro" in especie or "can" in especie else "gato"
        edad_key = "cachorro" if edad in ["cachorro", "cria", "bebe", "puppy", "kitten"] else "senior" if edad in ["senior", "viejo", "mayor", "anciano"] else "adulto"
        
        alimentos_regulares = ALIMENTOS_REGULARES.get(especie_key, {}).get(edad_key, [])
        for alimento in alimentos_regulares:
            recomendaciones.append({
                "nombre": alimento["nombre"],
                "tipo": "Alimento Regular",
                "descripcion": alimento["descripcion"],
                "requiere_prescripcion": False
            })
    
    # Buscar disponibilidad en inventario
    inventario = _load_json("inventario.json", default={"medicamentos": []})
    disponibilidad = []
    
    for rec in recomendaciones:
        nombre_buscar = _normalizar_texto(rec["nombre"])
        for producto in inventario.get("medicamentos", []):
            if nombre_buscar in _normalizar_texto(producto.get("nombre", "")):
                disponibilidad.append({
                    "nombre": producto["nombre"],
                    "disponible": producto.get("stock", 0) > 0,
                    "precio": producto.get("precio_unitario", 0)
                })
                break
    
    return jsonify({
        "exito": True,
        "especie": especie,
        "edad": edad,
        "condicion_medica": condicion if condicion else "Ninguna",
        "tipo_recomendacion": tipo_recomendacion,
        "recomendaciones": recomendaciones[:5],
        "disponibilidad_tienda": disponibilidad,
        "nota": "⚠️ Los alimentos terapéuticos requieren prescripción veterinaria. Consulte con el médico antes de cambiar la dieta de su mascota."
    })
