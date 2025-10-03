import streamlit as st
import odoolib
import base64
from PIL import Image
import io
import requests
import re # Importar la librería de expresiones regulares

# --- CONFIGURACIÓN ---
# Estos valores se deben configurar de forma segura en Streamlit Community Cloud
# usando el gestor de "Secrets".
ODOO_HOSTNAME = st.secrets.get("ODOO_HOSTNAME", "tu_dominio.odoo.com")
ODOO_DATABASE = st.secrets.get("ODOO_DATABASE", "tu_base_de_datos")
ODOO_LOGIN = st.secrets.get("ODOO_LOGIN", "tu_usuario_api")
ODOO_PASSWORD = st.secrets.get("ODOO_PASSWORD", "tu_contraseña_api")
OCR_API_KEY = st.secrets.get("OCR_API_KEY", "K85022997188957")

# --- FUNCIONES AUXILIARES ---

def resize_image(image_bytes, max_width=1280, quality=85):
    """Redimensiona una imagen y la devuelve como bytes."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convertir a RGB si es necesario (ej. PNG con transparencia)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(float(img.height) * float(ratio))
            img = img.resize((max_width, new_height), Image.LANCZOS)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=quality)
        return img_byte_arr.getvalue()
    except Exception as e:
        st.error(f"Error al procesar la imagen: {e}")
        return None

def parse_ocr_data(text):
    """Intenta extraer información estructurada del texto del OCR."""
    lines = text.split('\n')
    data = {'nombre': '', 'empresa': '', 'puesto': '', 'email': '', 'telefono': ''}
    
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_regex = r'\+?[\d\s-()]{8,20}'
    
    # Usar re.search para encontrar patrones
    for line in lines:
        email_match = re.search(email_regex, line)
        if not data['email'] and email_match:
            data['email'] = email_match.group(0)
            continue

        phone_match = re.search(phone_regex, line)
        if not data['telefono'] and phone_match:
            # Validar que es un número de teléfono plausible
            if len(re.sub(r'\D', '', phone_match.group(0))) > 6:
                data['telefono'] = phone_match.group(0).strip()
                continue
    
    # Lógica simplificada para el resto de los campos
    remaining_lines = [line for line in lines if line not in data.values()]
    for line in remaining_lines:
        if not data['nombre']:
            data['nombre'] = line
        elif not data['empresa']:
            data['empresa'] = line
        elif not data['puesto']:
            data['puesto'] = line

    return data

# --- INTERFAZ DE LA APLICACIÓN ---

st.set_page_config(page_title="Captura de Leads", layout="centered")

# Logo y Título
# CORRECCIÓN: Se pasa la URL directamente, sin formato Markdown.
st.image("https://refricomp.com/wp-content/uploads/2025/09/Logo_Refri_cuadrado.png", width=100)
st.title("Herramienta de Captura de Leads")

# Obtener el nombre de usuario de la URL (ej: ?usuario=Aitor)
# Usar la nueva API st.query_params
usuario = st.query_params.get("usuario", "No identificado")
st.subheader(f"Usuario: {usuario}")

if usuario == "No identificado":
    st.error("Error: Usuario no identificado. Por favor, accede desde tu enlace personal.")
    st.stop()

# Lista de etiquetas del CRM
etiquetas_crm = [
    'Güntner', 'Reparación / Intervención', 'Garantía', 'Evikon', 'Laukalt', 
    'Thermowave', 'Howden', 'SES', 'Witt', 'HAP', 'Parker', 'HB Products', 
    'HS Cooler', 'Omega', 'AWP', 'SES comisión', 'Pekos', 'Nuaire', 
    'Güntner (Repuestos)', 'HERL', 'Energy Recovery', 'Venta Service', 
    'Gestión', 'Nexson', 'Heliex', 'Zudek'
]

# Usamos un formulario para agrupar todos los campos y tener un único botón de envío
with st.form(key="lead_form"):
    st.header("1. Datos de la Tarjeta")
    
    # Campo para subir la foto de la tarjeta
    uploaded_card = st.file_uploader(
        "Sube una foto de la tarjeta de visita", 
        type=['png', 'jpg', 'jpeg'], 
        help="La app intentará leer los datos automáticamente."
    )

    # Campos de texto (se pueden rellenar o corregir manualmente)
    nombre = st.text_input("Nombre Completo*", key="nombre")
    empresa = st.text_input("Empresa*", key="empresa")
    puesto = st.text_input("Puesto", key="puesto")
    email = st.text_input("Email", key="email")
    telefono = st.text_input("Teléfono", key="telefono")

    st.header("2. Detalles Adicionales")
    
    # Selector de etiquetas múltiple
    etiquetas = st.multiselect("Etiquetas CRM", options=etiquetas_crm)
    
    # Área de texto para notas
    notas = st.text_area("Notas de la Reunión", height=150)
    
    # Campo para subir la foto del boceto
    uploaded_boceto = st.file_uploader("Sube una foto de un boceto o notas adicionales", type=['png', 'jpg', 'jpeg'])

    # Botón de envío del formulario
    submit_button = st.form_submit_button(label="Crear Lead en Odoo")

# --- LÓGICA DE PROCESAMIENTO ---

# Lógica del OCR (se ejecuta fuera del formulario para poder actualizar los campos)
if uploaded_card is not None and 'ocr_run' not in st.session_state:
    with st.spinner("Procesando OCR..."):
        image_bytes = uploaded_card.getvalue()
        resized_image = resize_image(image_bytes, max_width=1500, quality=90)
        
        if resized_image:
            files = {'file': ('card.jpg', resized_image, 'image/jpeg')}
            payload = {
                'apikey': OCR_API_KEY,
                'language': 'spa',
                'isOverlayRequired': 'false',
                'OCREngine': '2'
            }
            try:
                # CORRECCIÓN: Se pasa la URL directamente, sin formato Markdown.
                response = requests.post('https://api.ocr.space/parse/image', files=files, data=payload, timeout=20)
                response.raise_for_status()
                result = response.json()
                
                if not result.get('IsErroredOnProcessing') and result.get('ParsedResults'):
                    parsed_text = result['ParsedResults'][0]['ParsedText']
                    ocr_data = parse_ocr_data(parsed_text)
                    
                    # Rellenar los campos con los datos del OCR
                    st.session_state.nombre = ocr_data.get('nombre', '')
                    st.session_state.empresa = ocr_data.get('empresa', '')
                    st.session_state.puesto = ocr_data.get('puesto', '')
                    st.session_state.email = ocr_data.get('email', '')
                    st.session_state.telefono = ocr_data.get('telefono', '')
                    st.session_state.ocr_run = True # Marcar que el OCR ya se ejecutó
                    st.rerun() # Volver a ejecutar el script para mostrar los datos
                else:
                    st.warning(f"El OCR no pudo extraer texto. Error: {result.get('ErrorMessage', ['Desconocido'])[0]}")
            except requests.RequestException as e:
                st.error(f"Error de conexión con el servicio de OCR: {e}")

# Lógica del envío del formulario
if submit_button:
    if not nombre or not empresa:
        st.error("Los campos 'Nombre Completo' y 'Empresa' son obligatorios.")
    else:
        with st.spinner("Conectando con Odoo y creando el lead..."):
            try:
                # 1. Conectar a Odoo
                odoo = odoolib.get_connection(
                    hostname=ODOO_HOSTNAME, database=ODOO_DATABASE,
                    login=ODOO_LOGIN, password=ODOO_PASSWORD,
                    protocol='jsonrpcs', port=443
                )
                
                # 2. Preparar datos del lead
                lead_data = {
                    'name': f'Lead de {empresa} (Capturado por: {usuario})',
                    'partner_name': empresa,
                    'contact_name': nombre,
                    'function': puesto,
                    'email_from': email,
                    'phone': telefono,
                    'description': notas,
                }

                # 3. Buscar y asignar etiquetas
                if etiquetas:
                    tag_model = odoo.get_model('crm.tag')
                    tag_ids = []
                    for tag_name in etiquetas:
                        tag_id = tag_model.search([('name', '=', tag_name)])
                        if tag_id:
                            tag_ids.extend(tag_id)
                        else:
                            new_tag_id = tag_model.create({'name': tag_name})
                            tag_ids.append(new_tag_id)
                    if tag_ids:
                        lead_data['tag_ids'] = [(6, 0, tag_ids)]

                # 4. Crear el lead
                lead_model = odoo.get_model('crm.lead')
                lead_id = lead_model.create(lead_data)

                # 5. Subir adjuntos
                attachment_model = odoo.get_model('ir.attachment')
                
                # Adjuntar tarjeta de visita
                if uploaded_card:
                    card_bytes = resize_image(uploaded_card.getvalue())
                    if card_bytes:
                        attachment_model.create({
                            'name': f"tarjeta_{empresa.replace(' ', '_')}.jpg",
                            'datas': base64.b64encode(card_bytes).decode('utf-8'),
                            'res_model': 'crm.lead',
                            'res_id': lead_id,
                        })

                # Adjuntar boceto
                if uploaded_boceto:
                    boceto_bytes = resize_image(uploaded_boceto.getvalue())
                    if boceto_bytes:
                        attachment_model.create({
                            'name': f"boceto_{empresa.replace(' ', '_')}.jpg",
                            'datas': base64.b64encode(boceto_bytes).decode('utf-8'),
                            'res_model': 'crm.lead',
                            'res_id': lead_id,
                        })

                st.success(f"¡Éxito! Lead '{lead_data['name']}' creado correctamente en Odoo con ID: {lead_id}")
                st.balloons()
                # Limpiar el estado para permitir un nuevo OCR
                if 'ocr_run' in st.session_state:
                    del st.session_state['ocr_run']

            except Exception as e:
                st.error(f"Ha ocurrido un error al crear el lead en Odoo: {e}")
                st.error("Verifica las credenciales en los 'Secrets' y que Odoo sea accesible.")

