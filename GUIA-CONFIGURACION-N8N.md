# 🔧 Guía de Configuración n8n para BetterDoctor

## ❌ Problemas Detectados en tu Workflow Actual

1. **"Unused Respond to Webhook node"** - El webhook de WhatsApp está configurado para esperar respuesta pero no tiene una
2. **Formato JSON incorrecto** en AGENDAR CITA
3. **Switch mal configurado** - No detecta correctamente el canal

---

## ✅ SOLUCIÓN: Recrear el Workflow Paso a Paso

### Paso 1: Eliminar el Workflow Actual
1. Ve a n8n
2. Abre el workflow "veterinaria"
3. Click en los 3 puntos (⋮) → **Delete workflow**

### Paso 2: Crear Nuevo Workflow
Click en **+ Create Workflow** y nómbralo "Veterinaria BetterDoctor"

---

## 📌 NODOS A CREAR

### 1️⃣ Webhook CHAT WEB
```
Tipo: Webhook
Configuración:
  - HTTP Method: POST
  - Path: chat-web
  - Response Mode: Using 'Respond to Webhook' node ⬅️ IMPORTANTE
```

### 2️⃣ Webhook CHAT WHATSAPP  
```
Tipo: Webhook
Configuración:
  - HTTP Method: POST
  - Path: whatsapp
  - Response Mode: When Last Node Finishes ⬅️ DIFERENTE AL WEB
  - Response Data: First Entry JSON
```

### 3️⃣ Set Node "Preparar Web"
Conectar desde CHAT WEB
```
Campos a establecer:
  - canal: "web" (String)
  - mensaje: {{ $json.body?.chatInput ?? $json.chatInput ?? '' }}
  - sessionId: {{ $json.body?.sessionId ?? $json.sessionId ?? 'web_' + Date.now() }}
```

### 4️⃣ Set Node "Preparar WhatsApp"
Conectar desde CHAT WHATSAPP
```
Campos a establecer:
  - canal: "whatsapp" (String)
  - mensaje: {{ $json.body?.Body ?? $json.Body ?? '' }}
  - sessionId: {{ ($json.body?.From ?? $json.From ?? '').replace('whatsapp:', '') }}
  - telefonoOrigen: {{ ($json.body?.From ?? $json.From ?? '').replace('whatsapp:', '') }}
```

### 5️⃣ AI Agent
Conectar desde "Preparar Web" Y "Preparar WhatsApp"
```
Configuración:
  - Prompt Type: Define below
  - Text: {{ $json.mensaje }}
  - System Message: (ver abajo)
```

**System Message:**
```
Eres el asistente virtual de BetterDoctor, una clínica veterinaria.

REGLAS:
1. Responde en español
2. Sé amable y profesional
3. Respuestas cortas (3-4 oraciones)
4. NO uses markdown ni asteriscos

FLUJO DE CITAS:
Cuando quieran agendar, pregunta en orden:
1. Nombre de mascota y especie
2. Nombre del dueño
3. Teléfono
4. Motivo de consulta
Cuando tengas TODO, usa AGENDAR_CITA

SÍNTOMAS:
1. Usa BUSCAR_DIAGNOSTICO
2. Da recomendación
3. Pregunta si quiere cita

PRODUCTOS:
Usa BUSCAR_PRODUCTO

ALIMENTOS:
Pregunta especie y edad, usa RECOMENDAR_ALIMENTO
```

### 6️⃣ Google Gemini (conectar al AI Agent como Model)
```
Credentials: Tu cuenta de Google Gemini
```

### 7️⃣ Memory Buffer (conectar al AI Agent como Memory)
```
Session ID Type: Custom Key
Session Key: {{ $json.sessionId }}
Context Window Length: 15
```

### 8️⃣ Tool: AGENDAR_CITA (conectar al AI Agent como Tool)
```
Tool Description: Agenda cita veterinaria. Usa cuando tengas todos los datos.
Method: POST
URL: https://veterinariademo-64pl.onrender.com/api/bot/agendar-cita
Body Type: JSON
JSON Body:
{
  "nombre_mascota": "{{ $fromAI('nombre_mascota', 'Nombre de la mascota') }}",
  "especie": "{{ $fromAI('especie', 'perro o gato') }}",
  "propietario": "{{ $fromAI('propietario', 'Nombre del dueño') }}",
  "telefono": "{{ $fromAI('telefono', 'Teléfono') }}",
  "sintomas": "{{ $fromAI('sintomas', 'Motivo de consulta') }}",
  "urgencia": "{{ $fromAI('urgencia', 'normal, urgente o emergencia') }}"
}
```

### 9️⃣ Tool: BUSCAR_DIAGNOSTICO (conectar al AI Agent como Tool)
```
Tool Description: Evalúa síntomas veterinarios
Method: POST
URL: https://veterinariademo-64pl.onrender.com/api/bot/diagnostico
Body Type: JSON
JSON Body:
{
  "sintomas": "{{ $fromAI('sintomas', 'Síntomas separados por coma') }}",
  "especie": "{{ $fromAI('especie', 'perro o gato') }}"
}
```

### 🔟 Tool: BUSCAR_PRODUCTO (conectar al AI Agent como Tool)
```
Tool Description: Busca productos en inventario
Method: GET
URL: https://veterinariademo-64pl.onrender.com/api/bot/inventario?q={{ $fromAI('query', 'Producto a buscar') }}
```

### 1️⃣1️⃣ Tool: RECOMENDAR_ALIMENTO (conectar al AI Agent como Tool)
```
Tool Description: Recomienda alimentos para mascotas
Method: POST
URL: https://veterinariademo-64pl.onrender.com/api/bot/recomendar-alimento
Body Type: JSON
JSON Body:
{
  "especie": "{{ $fromAI('especie', 'perro o gato') }}",
  "edad": "{{ $fromAI('edad', 'cachorro, adulto o senior') }}",
  "condicion_medica": "{{ $fromAI('condicion', 'Condición médica si tiene') }}"
}
```

### 1️⃣2️⃣ Switch "Router Canal"
Conectar desde AI Agent
```
Modo: Rules
Rule 1 (Web):
  - Condition: {{ $('Preparar Web').item.json.canal }} equals "web"
  - Output: Web
  
Rule 2 (WhatsApp):
  - Condition: {{ $('Preparar WhatsApp').item.json.canal }} equals "whatsapp"
  - Output: WhatsApp
```

### 1️⃣3️⃣ Respond to Webhook "Responder Web"
Conectar desde Switch salida "Web"
```
Respond With: JSON
Response Body: { "output": {{ $json.output }} }
```

### 1️⃣4️⃣ Twilio "Enviar WhatsApp"
Conectar desde Switch salida "WhatsApp"
```
Credentials: Tu cuenta Twilio
From: Tu número de Twilio (+14155238886)
To: {{ $('Preparar WhatsApp').item.json.telefonoOrigen }}
Send to WhatsApp: ✓
Message: {{ $json.output }}
```

### 1️⃣5️⃣ Set "Respuesta WA" (OPCIONAL)
Conectar desde Twilio
```
response: "ok"
```

---

## 🔗 CONEXIONES FINALES

```
CHAT WEB ──────────────┐
                       ▼
                 Preparar Web ────┐
                                  │
                                  ▼
                            AI Agent ──▶ Switch ──┬──▶ Responder Web
                                  ▲              │
                                  │              └──▶ Enviar WhatsApp ──▶ Respuesta WA
                 Preparar WhatsApp ───┘
                       ▲
CHAT WHATSAPP ─────────┘

HERRAMIENTAS (conectadas al AI Agent):
  ├── Google Gemini (Model)
  ├── Memory Buffer (Memory)
  ├── AGENDAR_CITA (Tool)
  ├── BUSCAR_DIAGNOSTICO (Tool)
  ├── BUSCAR_PRODUCTO (Tool)
  └── RECOMENDAR_ALIMENTO (Tool)
```

---

## ⚠️ PUNTOS CRÍTICOS

1. **Response Mode diferente para cada webhook:**
   - Web: "Using Respond to Webhook node"
   - WhatsApp: "When Last Node Finishes"

2. **El Switch debe verificar el campo `canal`** que viene de los nodos "Preparar"

3. **Twilio debe tener las credenciales configuradas correctamente**

4. **El webhook de WhatsApp NO necesita Respond to Webhook** porque Twilio envía la respuesta

---

## 📱 Configuración Twilio (si no lo tienes)

1. Ve a https://console.twilio.com
2. Copia tu Account SID y Auth Token
3. En n8n, crea credencial Twilio con esos datos
4. Tu número WhatsApp Sandbox: `+14155238886`
5. En Twilio, configura el webhook de mensajes entrantes apuntando a tu URL de n8n:
   `https://n8n-production-607c.up.railway.app/webhook/whatsapp`

---

## 🧪 Probar

1. **Chat Web:** Abre https://veterinariademo-64pl.onrender.com/login.html y usa el chat
2. **WhatsApp:** Envía mensaje al número de Twilio Sandbox


