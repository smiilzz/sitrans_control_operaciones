import plotly.express as px
import plotly.graph_objects as go
import os
import glob
import time

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Sitrans Control Operaciones", 
    layout="wide", 
    page_icon="🚢",
    initial_sidebar_state="expanded"
    initial_sidebar_state="collapsed"
)

# --- CONFIGURACIÓN DE RUTAS ---
# Ruta Base (Raíz)
BASE_DIR = r"C:\Users\reefertpsv\OneDrive - Universidad Técnica Federico Santa María\Control Operaciones"

# Carpetas de Entrada (Donde el robot deja los archivos LISTOS)
DIR_REPORTES = os.path.join(BASE_DIR, "1_Reporte")
DIR_MONITOR = os.path.join(BASE_DIR, "2_Monitor")

# El Archivo Maestro (Historial) se guardará en la RAÍZ para no mezclarlo
ARCHIVO_MAESTRO = os.path.join(BASE_DIR, "monitor_maestro_acumulado.xlsx")

# Crear carpetas si no existen (solo las necesarias para el dashboard)
for d in [DIR_REPORTES, DIR_MONITOR]:
    if not os.path.exists(d):
        os.makedirs(d)

# --- CONFIGURACIÓN DE UMBRALES SEMÁFORO (MINUTOS) ---
# AHORA TODOS SON IGUALES: [Minutos_Verde, Minutos_Amarillo]
UMBRALES_SEMAFORO = {
    "Conexión a Stacking":       [15, 30],  
    "Desconexión para Embarque": [15, 30], # Corregido para igualar a los demás
    "Desconexión para Embarque": [15, 30],
    "Conexión OnBoard":          [15, 30]   
}

@@ -124,10 +141,18 @@
    """, unsafe_allow_html=True)

# --- CONFIGURACIÓN LÓGICA MONITOR ---
ARCHIVO_MAESTRO = "monitor_maestro_acumulado.xlsx"
COLS_SENSORES = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']

# --- FUNCIONES SOPORTE ---
def get_files_from_folder(folder):
    """Busca archivos .xls y .xlsx en la carpeta dada"""
    extensions = ['*.xls', '*.xlsx']
    files = []
    if os.path.exists(folder):
        for ext in extensions:
            files.extend(glob.glob(os.path.join(folder, ext)))
    return files

@st.cache_data(show_spinner=False)
def formatear_duracion(minutos):
    if pd.isna(minutos): return ""
@@ -136,10 +161,10 @@ def formatear_duracion(minutos):
    return f"{segundos//3600}:{(segundos%3600)//60:02d}:{segundos%60:02d}"

@st.cache_data(show_spinner=False)
def extraer_metadatos(file):
def extraer_metadatos(file_path):
    metadatos = {"Nave": "---", "Rotación": "Indefinida", "Fecha": "---"}
    try:
        df_head = pd.read_excel(file, header=None, nrows=20)
        df_head = pd.read_excel(file_path, header=None, nrows=20)
        texto = " ".join(df_head.astype(str).stack().tolist()).upper()
        match_fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}\s+\d{1,2}:\d{2})', texto)
        if match_fecha: metadatos["Fecha"] = match_fecha.group(1)
@@ -160,13 +185,13 @@ def extraer_metadatos(file):
    except: return metadatos

@st.cache_data(show_spinner=False)
def cargar_excel(file, palabra_clave):
def cargar_excel(file_path, palabra_clave):
    try:
        df_temp = pd.read_excel(file, header=None)
        df_temp = pd.read_excel(file_path, header=None)
        for i, row in df_temp.iterrows():
            vals = [str(v).strip().upper() for v in row]
            if palabra_clave in vals:
                df = pd.read_excel(file, header=i)
                df = pd.read_excel(file_path, header=i)
                cols = pd.Series(df.columns)
                for c_idx, col in enumerate(df.columns):
                    col_str = str(col).strip().upper()
@@ -191,7 +216,8 @@ def limpiar_y_unificar_columnas(df):
            df = df.drop(columns=[col_sufijo])
    return df

def procesar_batch_monitores(lista_archivos):
def procesar_batch_monitores(lista_rutas_archivos):
    # Cargar maestro si existe
    if os.path.exists(ARCHIVO_MAESTRO):
        try:
            df_maestro = pd.read_excel(ARCHIVO_MAESTRO)
@@ -201,14 +227,14 @@ def procesar_batch_monitores(lista_archivos):
        except: df_maestro = pd.DataFrame()
    else: df_maestro = pd.DataFrame()

    for archivo in lista_archivos:
    for ruta_archivo in lista_rutas_archivos:
        try:
            archivo.seek(0)
            df_nuevo = pd.read_excel(archivo, header=3)
            # header=3 porque el archivo Monitor original tiene los datos en fila 4
            df_nuevo = pd.read_excel(ruta_archivo, header=3)
            df_nuevo = limpiar_y_unificar_columnas(df_nuevo)

            if 'UNIDAD' not in df_nuevo.columns:
                st.warning(f"Archivo ignorado: No se encontró la columna 'UNIDAD' en fila 4.")
                st.warning(f"Archivo ignorado: No se encontró 'UNIDAD' en {os.path.basename(ruta_archivo)}")
                continue

            df_nuevo = df_nuevo.drop_duplicates(subset=['UNIDAD'])
@@ -218,7 +244,7 @@ def procesar_batch_monitores(lista_archivos):
            else: df_maestro = df_nuevo.combine_first(df_maestro)

        except Exception as e:
            st.error(f"Error procesando archivo {archivo.name}: {e}")
            st.error(f"Error procesando {os.path.basename(ruta_archivo)}: {e}")

    if df_maestro.empty: return None

@@ -276,52 +302,62 @@ def procesar_datos_completos(files_rep_list, files_mon_list):
            df_master[col] = pd.to_datetime(df_master[col], dayfirst=True, errors='coerce')
    return df_master

# --- OBTENCIÓN AUTOMÁTICA DE ARCHIVOS ---
files_rep_list = get_files_from_folder(DIR_REPORTES)
files_mon_list = get_files_from_folder(DIR_MONITOR)

# --- INTERFAZ ---
with st.sidebar:
    c1, c2, c3 = st.columns([1, 4, 1]) 
    with c2:
        try: st.image("Logo.png", use_container_width=True)
        except: st.title("SITRANS")
        
    st.header("Carga de Datos")
    files_rep_list = st.file_uploader("📂 1_Reportes", type=["xls", "xlsx"], accept_multiple_files=True)
    files_mon_list = st.file_uploader("📂 2_Monitor (Múltiples)", type=["xlsx"], accept_multiple_files=True)
    
    st.write("---")
    st.info(f"📂 **Modo Automático**")
    st.caption(f"Reportes encontrados: {len(files_rep_list)}")
    st.caption(f"Monitores encontrados: {len(files_mon_list)}")
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()

    st.write("---")

    if st.button("Borrar Historial Monitor"):
        if os.path.exists(ARCHIVO_MAESTRO):
            os.remove(ARCHIVO_MAESTRO)
            st.success("Historial borrado.")
            try:
                os.remove(ARCHIVO_MAESTRO)
                st.success("Historial borrado.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo borrar: {e}")
        else: st.info("No hay historial.")

if files_rep_list and files_mon_list:
    df_master = procesar_datos_completos(files_rep_list, files_mon_list)

    if df_master is not None:
        # --- NUEVO: CREAR ETIQUETA COMBINADA (ROTACIÓN - NAVE) ---
        # Creamos una columna temporal para el selector
        # --- ETIQUETA COMBINADA ---
        df_master['ROTACION_LABEL'] = df_master['ROTACION_DETECTADA'].astype(str) + " - " + df_master['NAVE_DETECTADA'].astype(str)

        c_head_izq, c_head_der = st.columns([3, 1])

        # Obtenemos las opciones únicas de la etiqueta combinada
        opciones_rot = df_master['ROTACION_LABEL'].unique()

        with c_head_der:
            seleccion_label = st.selectbox("⚓ Rotación:", opciones_rot)

        # Filtramos el DataFrame usando la etiqueta combinada seleccionada
        df = df_master[df_master['ROTACION_LABEL'] == seleccion_label].copy()

        # Obtenemos los valores limpios para mostrarlos en el Header Box
        nave = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
        rotacion_real = df['ROTACION_DETECTADA'].iloc[0] if not df.empty else "---"
        fecha = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

        with c_head_izq:
            st.title("🚢 Control de Operaciones Sitrans")

        # Usamos 'rotacion_real' para que en el recuadro azul solo salga el número (ej: 26-0020)
        # Si prefieres que salga todo junto en el recuadro, cambia 'rotacion_real' por 'seleccion_label'
        st.markdown(f"""
        <div class="header-data-box">
            <div class="header-item"><div class="header-label">Nave</div><div class="header-value">{nave}</div></div>
@@ -354,7 +390,7 @@ def procesar_datos_completos(files_rep_list, files_mon_list):
                cond = [
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].notna()), 
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].isna()),  
                    (df[cols["Ini"]].isna())                            
                    (df[cols["Ini"]].isna())                             
                ]
                df[f"Estado_{proceso}"] = np.select(cond, [label_fin, "Pendiente", "Sin Solicitud"], default="Sin Solicitud")

@@ -396,7 +432,6 @@ def render_tab(tab, proceso):

                conteos = pd.DataFrame()
                if not df_activo.empty:
                    # --- CONFIGURACIÓN DE LEYENDA ORDENADA ---
                    conteos = df_activo[col_sem].value_counts().reset_index()
                    conteos.columns = ['Color', 'Cantidad']

@@ -411,7 +446,6 @@ def render_tab(tab, proceso):
                    }
                    conteos['Color'] = conteos['Color'].map(legend_map)

                    # Forzar orden de categorías para que la leyenda siempre sea V-A-R
                    orden_fijo = [label_verde, label_amarillo, label_rojo]
                    conteos['Color'] = pd.Categorical(conteos['Color'], categories=orden_fijo, ordered=True)
                    conteos = conteos.sort_values('Color')
@@ -438,7 +472,6 @@ def render_tab(tab, proceso):

                    with k1: 
                        st.subheader("🚦 Distribución Contenedores")
                        # Gráfico con leyenda ordenada
                        fig = px.pie(conteos, values='Cantidad', names='Color', 
                                     color='Color', color_discrete_map=new_color_map, hole=0.6)
                        fig.update_layout(showlegend=True, margin=dict(t=20,b=20,l=20,r=20), height=230, legend=dict(orientation="h", y=-0.2))
@@ -549,11 +582,12 @@ def pintar(row):
        st.download_button(
            label="📥 Descargar Excel Completo",
            data=buffer.getvalue(),
            file_name=f"Reporte_{rotacion_real}.xlsx",  # <--- CAMBIO AQUÍ
            file_name=f"Reporte_{rotacion_real}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.error("Error al procesar archivos. Revisa el formato del Monitor.")
        st.error("Error al procesar archivos. Revisa las carpetas locales.")
else:
    st.info("Sube los reportes y los archivos Monitor para comenzar.")
    st.info("Esperando que el robot descargue archivos en las carpetas...")
    st.caption(f"Ruta monitoreada: {BASE_DIR}")
