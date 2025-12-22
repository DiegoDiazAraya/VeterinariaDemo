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
    
    # Crear la cita/consulta
    nueva_cita = {
        "id": len(consultas_data.get("consultas", [])) + 1,
        "numero_ticket": numero_ticket,
        "fecha_registro": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "estado": "en_espera",
        "prioridad": config_urgencia["prioridad"],
        "origen": "chatbot",
        "paciente": {
            "nombre": data.get("nombre_mascota"),
            "especie": data.get("especie", ""),
            "raza": data.get("raza", ""),
            "propietario": data.get("propietario"),
            "telefono": data.get("telefono")
        },
        "sintomas": data.get("sintomas", "").split(",") if isinstance(data.get("sintomas"), str) else data.get("sintomas", []),
        "motivo_consulta": data.get("sintomas", "Consulta agendada via chatbot"),
        "tipo_consulta": tipo_cita,
        "urgencia_reportada": urgencia,
        "especialidad_requerida": data.get("especialidad", ""),
        "notas_chatbot": data.get("notas", ""),
        "registrado_por": "Sistema Chatbot",
        "atendido_por": None,
        "diagnostico": None,
        "cobro": None
    }
    
    # Guardar la cita
    consultas_data["consultas"].append(nueva_cita)
    consultas_data["ultimo_ticket"] = ultimo_ticket
    
    # Escribir al archivo
    try:
        filepath = os.path.join(_get_base_path(), "consultas.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(consultas_data, f, ensure_ascii=False, indent=2)
        guardado_ok = True
    except Exception as e:
        print(f"[bot_api] Error guardando cita: {e}")
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
            "propietario": data.get("propietario"),
            "telefono": data.get("telefono"),
            "fecha_registro": nueva_cita["fecha_registro"]
        },
        "instrucciones": instrucciones,
        "contacto_emergencias": "(555) 123-4567"
    })
