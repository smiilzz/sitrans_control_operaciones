import streamlit as st
import pandas as pd
import io
import re
import numpy as np
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
)

# ==============================================================================
# 🔧 AUTO-DETECCIÓN DE RUTA (SOLUCIÓN DEFINITIVA)
# ==============================================================================
# En lugar de escribir la ruta, le decimos a Python: 
# "Usa la carpeta donde está guardado este archivo app.py"
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except:
    BASE_DIR = os.getcwd() # Fallback por si corre en un entorno raro

# Rutas derivadas (Busca las carpetas al lado del script)
DIR_REPORTES = os.path.join(BASE_DIR, "1_Reporte")
DIR_MONITOR = os.path.join(BASE_DIR, "2_Monitor")
ARCHIVO_MAESTRO = os.path.join(BASE_DIR, "monitor_maestro_acumulado.xlsx")

# --- FUNCIONES SOPORTE ---
COLS_SENSORES = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']

def get_files_from_folder(folder):
    """Busca archivos ignorando mayúsculas y extensiones"""
    files = []
    if os.path.exists(folder):
        # Busca todo lo que termine en xls o xlsx
        tipos = ["*.xls", "*.xlsx", "*.XLS", "*.XLSX"]
        for tipo in tipos:
            files.extend(glob.glob(os.path.join(folder, tipo)))
    return list(set(files))

@st.cache_data(show_spinner=False)
def formatear_duracion(minutos):
    if pd.isna(minutos): return ""
    if minutos < 0: minutos = 0 
    segundos = int(minutos * 60)
    return f"{segundos//3600}:{(segundos%3600)//60:02d}:{segundos%60:02d}"

@st.cache_data(show_spinner=False)
def extraer_metadatos(file_path):
    metadatos = {"Nave": "---", "Rotación": "Indefinida", "Fecha": "---"}
    try:
        df_head = pd.read_excel(file_path, header=None, nrows=20)
        texto = " ".join(df_head.astype(str).stack().tolist()).upper()
        match_fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}\s+\d{1,2}:\d{2})', texto)
        if match_fecha: metadatos["Fecha"] = match_fecha.group(1)
        else:
            match_solo = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', texto)
            if match_solo: metadatos["Fecha"] = match_solo.group(1)

        for i, row in df_head.iterrows():
            fila = [str(x).strip().upper() for x in row if pd.notna(x)]
            for j, val in enumerate(fila):
                if "NAVE" in val:
                    if ":" in val and len(val.split(":")) > 1: metadatos["Nave"] = val.split(":")[1].strip()
                    elif j+1 < len(fila): metadatos["Nave"] = fila[j+1]
                if any(x in val for x in ["ROTACION", "ROTACIÓN", "VIAJE"]):
                    if ":" in val and len(val.split(":")) > 1: metadatos["Rotación"] = val.split(":")[1].strip()
                    elif j+1 < len(fila): metadatos["Rotación"] = fila[j+1]
        return metadatos
    except: return metadatos

@st.cache_data(show_spinner=False)
def cargar_excel(file_path, palabra_clave):
    try:
        # Intenta leer directo
        df_temp = pd.read_excel(file_path, header=None)
        
        # Busca la palabra clave
        for i, row in df_temp.iterrows():
            vals = [str(v).strip().upper() for v in row]
            if palabra_clave in vals:
                df = pd.read_excel(file_path, header=i)
                # Limpiar columnas duplicadas (.1, .2)
                cols = pd.Series(df.columns)
                for c_idx, col in enumerate(df.columns):
                    col_str = str(col).strip().upper()
                    if (cols.astype(str).str.strip().str.upper() == col_str).sum() > 1:
                        count = (cols[:c_idx].astype(str).str.strip().str.upper() == col_str).sum()
                        if count > 0: col_str = f"{col_str}.{count}"
                    cols[c_idx] = col_str
                df.columns = cols
                return df
        return None
    except: return None

def limpiar_y_unificar_columnas(df):
    df.columns = df.columns.str.strip().str.upper()
    df = df.loc[:, ~df.columns.duplicated()]
    for col_base in COLS_SENSORES:
        col_sufijo = f"{col_base}.1"
        if col_base in df.columns and col_sufijo in df.columns:
            df[col_base] = df[col_base].fillna(df[col_sufijo])
            df = df.drop(columns=[col_sufijo])
    return df

def procesar_batch_monitores(lista_rutas_archivos):
    if os.path.exists(ARCHIVO_MAESTRO):
        try:
            df_maestro = pd.read_excel(ARCHIVO_MAESTRO)
            if 'UNIDAD' in df_maestro.columns:
                df_maestro = df_maestro.set_index('UNIDAD')
            else: df_maestro = pd.DataFrame()
        except: df_maestro = pd.DataFrame()
    else: df_maestro = pd.DataFrame()

    for ruta_archivo in lista_rutas_archivos:
        try:
            df_nuevo = pd.read_excel(ruta_archivo, header=3)
            df_nuevo = limpiar_y_unificar_columnas(df_nuevo)
            
            if 'UNIDAD' not in df_nuevo.columns: continue

            df_nuevo = df_nuevo.drop_duplicates(subset=['UNIDAD'])
            df_nuevo = df_nuevo.set_index('UNIDAD')
            
            if df_maestro.empty: df_maestro = df_nuevo
            else: df_maestro = df_nuevo.combine_first(df_maestro)
                
        except: pass

    if df_maestro.empty: return None

    def es_reefer_ct(row):
        es_ct = False
        for col in COLS_SENSORES:
            if col in row and pd.notna(row[col]) and str(row[col]).strip() != "":
                es_ct = True
                break
        return "CT" if es_ct else "General"

    df_maestro['TIPO_CONTENEDOR'] = df_maestro.apply(es_reefer_ct, axis=1)

    try:
        df_guardar = df_maestro.reset_index()
        df_guardar.to_excel(ARCHIVO_MAESTRO, index=False)
        return df_guardar
    except: return df_maestro.reset_index()

@st.cache_data(show_spinner="Procesando datos...")
def procesar_datos_completos(files_rep_list, files_mon_list):
    lista_dfs = []
    for archivo_rep in files_rep_list:
        meta = extraer_metadatos(archivo_rep)
        df_ind = cargar_excel(archivo_rep, "CONTENEDOR")
        if df_ind is not None:
            df_ind = df_ind[df_ind['CONTENEDOR'].notna()]
            df_ind = df_ind[df_ind['CONTENEDOR'].astype(str).str.strip() != ""]
            df_ind = df_ind[~df_ind['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]
            df_ind['ROTACION_DETECTADA'] = meta['Rotación']
            df_ind['NAVE_DETECTADA'] = meta['Nave']
            df_ind['FECHA_CONSULTA'] = meta['Fecha']
            lista_dfs.append(df_ind)
            
    if not lista_dfs: return None
    df_rep = pd.concat(lista_dfs, ignore_index=True)
    
    df_mon_data = procesar_batch_monitores(files_mon_list)
    if df_mon_data is None: 
        # Si no hay monitores, usamos solo reportes (evita error crítico)
        st.toast("⚠️ No hay datos de monitores, mostrando solo reportes.")
        return df_rep
    
    df_master = pd.merge(df_rep, df_mon_data, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
    
    if 'TIPO_CONTENEDOR' in df_master.columns:
        df_master['TIPO'] = df_master['TIPO_CONTENEDOR'].fillna('General')
    else:
        df_master['TIPO'] = 'General'
        
    cols_fecha_posibles = ["TIME_IN", "CONEXIÓN", "SOLICITUD DESCONEXIÓN", "DESCONECCIÓN", "TIME_LOAD", "CONEXIÓN ONBOARD"]
    for col in cols_fecha_posibles:
        if col in df_master.columns:
            df_master[col] = pd.to_datetime(df_master[col], dayfirst=True, errors='coerce')
    return df_master

# --- OBTENCIÓN AUTOMÁTICA DE ARCHIVOS ---
files_rep_list = get_files_from_folder(DIR_REPORTES)
files_mon_list = get_files_from_folder(DIR_MONITOR)

# --- PANEL LATERAL DIAGNÓSTICO ---
with st.sidebar:
    c1, c2, c3 = st.columns([1, 4, 1]) 
    with c2:
        try: st.image("Logo.png", use_container_width=True)
        except: st.title("SITRANS")
    
    st.write("---")
    st.info(f"📂 **Ubicación del Script**")
    # Mostramos dónde cree Python que está
    st.caption(f"{BASE_DIR}")
    
    if len(files_rep_list) > 0:
        st.success(f"✅ Reportes: {len(files_rep_list)} archivos")
    else:
        st.error(f"❌ No se ven archivos en: 1_Reporte")
        
    if len(files_mon_list) > 0:
        st.success(f"✅ Monitores: {len(files_mon_list)} archivos")
    else:
        st.warning(f"⚠️ No se ven archivos en: 2_Monitor")
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()
    
    st.write("---")
    if st.button("🗑️ Borrar Historial"):
        if os.path.exists(ARCHIVO_MAESTRO):
            try: os.remove(ARCHIVO_MAESTRO); st.success("Borrado!"); st.rerun()
            except: st.error("Error al borrar")

# --- LÓGICA PRINCIPAL ---
if len(files_rep_list) > 0:
    df_master = procesar_datos_completos(files_rep_list, files_mon_list)

    if df_master is not None:
        # Etiqueta combinada
        df_master['ROTACION_LABEL'] = df_master['ROTACION_DETECTADA'].astype(str) + " - " + df_master['NAVE_DETECTADA'].astype(str)

        c_head_izq, c_head_der = st.columns([3, 1])
        opciones_rot = df_master['ROTACION_LABEL'].unique()
        
        with c_head_der:
            seleccion_label = st.selectbox("⚓ Rotación:", opciones_rot)

        df = df_master[df_master['ROTACION_LABEL'] == seleccion_label].copy()
        
        nave = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
        rotacion_real = df['ROTACION_DETECTADA'].iloc[0] if not df.empty else "---"
        fecha = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

        with c_head_izq:
            st.title("🚢 Control de Operaciones Sitrans")
            
        st.markdown(f"""
        <div class="header-data-box">
            <div class="header-item"><div class="header-label">Nave</div><div class="header-value">{nave}</div></div>
            <div class="header-item"><div class="header-label">Fecha Consulta</div><div class="header-value">{fecha}</div></div>
            <div class="header-item"><div class="header-label">Rotación</div><div class="header-value">{rotacion_real}</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        parejas = {
            "Conexión a Stacking": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
            "Desconexión para Embarque": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
            "Conexión OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
        }

        mapa_estados = {
            "Conexión a Stacking": "Conectado",
            "Desconexión para Embarque": "Desconectado",
            "Conexión OnBoard": "Conectado a Bordo"
        }

        ahora = pd.Timestamp.now() 

        # --- UMBRALES ---
        UMBRALES_SEMAFORO = {
            "Conexión a Stacking":       [15, 30],  
            "Desconexión para Embarque": [15, 30],
            "Conexión OnBoard":          [15, 30]   
        }

        # --- CÁLCULO DE ESTADOS ---
        for proceso, cols in parejas.items():
            label_fin = mapa_estados[proceso]
            df[f"Estado_{proceso}"] = "Sin Solicitud"
            df[f"Min_{proceso}"] = 0.0
            
            if cols["Ini"] in df.columns and cols["Fin"] in df.columns:
                cond = [
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].notna()), 
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].isna()),  
                    (df[cols["Ini"]].isna())                             
                ]
                df[f"Estado_{proceso}"] = np.select(cond, [label_fin, "Pendiente", "Sin Solicitud"], default="Sin Solicitud")
                
                col_min = f"Min_{proceso}"
                mask_fin = df[f"Estado_{proceso}"] == label_fin
                
                diff_minutos = (df.loc[mask_fin, cols["Fin"]] - df.loc[mask_fin, cols["Ini"]]).dt.total_seconds() / 60
                df.loc[mask_fin, col_min] = diff_minutos.clip(lower=0) 

                mask_pen = df[f"Estado_{proceso}"] == "Pendiente"
                diff_pendiente = (ahora - df.loc[mask_pen, cols["Ini"]]).dt.total_seconds() / 60
                df.loc[mask_pen, col_min] = diff_pendiente.clip(lower=0)
                
                df[f"Ver_Tiempo_{proceso}"] = np.where(mask_fin, df[col_min].apply(formatear_duracion), "")
                df[f"Ver_Trans_{proceso}"] = np.where(mask_pen, df[col_min], 0)

            col_min_p = f"Min_{proceso}"
            limite_verde, limite_amarillo = UMBRALES_SEMAFORO[proceso]
            cond_sem = [
                df[col_min_p] <= limite_verde,
                (df[col_min_p] > limite_verde) & (df[col_min_p] <= limite_amarillo),
                df[col_min_p] > limite_amarillo
            ]
            df[f"Semaforo_{proceso}"] = np.select(cond_sem, ['Verde', 'Amarillo', 'Rojo'], default='Rojo')

        # --- TABS ---
        tab1, tab2, tab3 = st.tabs(["🔌 CONEXIÓN A STACKING", "🔋 DESCONEXIÓN EMBARQUE", "🚢 CONEXIÓN ONBOARD"])

        def render_tab(tab, proceso):
            with tab:
                st.write("") 
                col_stat = f"Estado_{proceso}"
                col_min = f"Min_{proceso}"
                col_sem = f"Semaforo_{proceso}"
                label_fin = mapa_estados[proceso]
                lim_verde, lim_amarillo = UMBRALES_SEMAFORO[proceso]

                df_activo = df[df[col_stat].isin([label_fin, "Pendiente"])].copy()
                
                conteos = pd.DataFrame()
                if not df_activo.empty:
                    conteos = df_activo[col_sem].value_counts().reset_index()
                    conteos.columns = ['Color', 'Cantidad']
                    
                    label_verde = f"Verde: ≤{lim_verde}m"
                    label_amarillo = f"Amarillo: {lim_verde}-{lim_amarillo}m"
                    label_rojo = f"Rojo: >{lim_amarillo}m"

                    legend_map = {'Verde': label_verde, 'Amarillo': label_amarillo, 'Rojo': label_rojo}
                    conteos['Color'] = conteos['Color'].map(legend_map)
                    
                    orden_fijo = [label_verde, label_amarillo, label_rojo]
                    conteos['Color'] = pd.Categorical(conteos['Color'], categories=orden_fijo, ordered=True)
                    conteos = conteos.sort_values('Color')

                    new_color_map = {label_verde: '#2ecc71', label_amarillo: '#ffc107', label_rojo: '#dc3545'}

                if not df_activo.empty:
                    if proceso == "Conexión OnBoard": 
                        df_activo['Cumple'] = df_activo[col_min] <= 30
                    else:
                        cond_cumple = [
                            (df_activo['TIPO'] == 'CT') & (df_activo[col_min] <= 30),
                            (df_activo['TIPO'] == 'General') & (df_activo[col_min] <= 60)
                        ]
                        df_activo['Cumple'] = np.select(cond_cumple, [True, True], default=False)
                    
                    pct = (df_activo['Cumple'].sum() / len(df_activo)) * 100

                    k1, k2, k3 = st.columns([1, 1, 1], gap="medium")

                    with k1: 
                        st.subheader("🚦 Distribución")
                        fig = px.pie(conteos, values='Cantidad', names='Color', 
                                     color='Color', color_discrete_map=new_color_map, hole=0.6)
                        fig.update_layout(showlegend=True, margin=dict(t=20,b=20,l=20,r=20), height=230, legend=dict(orientation="h", y=-0.2))
                        st.plotly_chart(fig, use_container_width=True, key=f"pie_{proceso}")

                    with k2:
                        st.subheader("🕜 Cumplimiento")
                        color_texto = "#28a745" if pct >= 66.6 else "#ffc107" if pct >= 33.3 else "#dc3545"
                        fig_gauge = go.Figure(go.Indicator(
                            mode = "gauge+number", value = pct,
                            number = {'suffix': "%", 'valueformat': ".1f", 'font': {'size': 38, 'weight': 'bold', 'color': color_texto}},
                            gauge = {
                                'axis': {'range': [0, 100]}, 'bar': {'color': "rgba(0,0,0,0)"},
                                'steps': [{'range': [0, 33], 'color': "#dc3545"}, {'range': [33, 66], 'color': "#ffc107"}, {'range': [66, 100], 'color': "#28a745"}],
                            }
                        ))
                        fig_gauge.update_layout(height=230, margin=dict(t=20, b=20, l=45, r=45))
                        st.plotly_chart(fig_gauge, use_container_width=True, key=f"gauge_{proceso}")

                    with k3:
                        st.subheader("📊 Métricas")
                        prom_global = df_activo[col_min].mean()
                        rojos_total = len(df_activo[~df_activo['Cumple']])
                        
                        if rojos_total > 0: st.markdown(f"""<div class="alert-box alert-red">🚨 {rojos_total} Atrasados</div>""", unsafe_allow_html=True)
                        else: st.markdown(f"""<div class="alert-box alert-green">✅ Todo al día</div>""", unsafe_allow_html=True)
                        st.markdown(f"""<div class="metric-card"><div class="metric-val">{prom_global:.1f} min</div><div class="metric-lbl">Promedio Total</div></div>""", unsafe_allow_html=True)
                else:
                    st.info(f"ℹ️ No hay actividad activa para {proceso}.")

                st.divider()

                c_filt, c_tot, c_norm, c_ct = st.columns([2, 1, 1, 1], gap="small")
                with c_filt:
                    filtro_estado = st.radio(f"f_{proceso}", ["Todos", label_fin, "Pendiente", "Sin Solicitud"], horizontal=True, label_visibility="collapsed", key=proceso)
                
                if filtro_estado == "Todos": df_show = df.copy()
                else: df_show = df[df[col_stat] == filtro_estado].copy()
                
                busqueda = st.text_input(f"🔍 Buscar Contenedor:", placeholder="Ej: TRHU o 123...", key=f"search_{proceso}", label_visibility="collapsed")
                if busqueda:
                    termino = busqueda.strip()
                    df_show = df_show[df_show['CONTENEDOR'].astype(str).str.contains(termino, case=False, na=False)]

                c_tot.metric("Total", len(df_show))
                c_norm.metric("❄️ Gen", len(df_show[df_show['TIPO'] == 'General']))
                c_ct.metric("⚡ CT", len(df_show[df_show['TIPO'] == 'CT']))
                st.write("")

                def pintar(row):
                    val = df.loc[row.name, col_min]
                    stt = df.loc[row.name, col_stat]
                    est = [''] * len(row)
                    if stt in [label_fin, "Pendiente"] and pd.notna(val) and val >= 0:
                        c = "#d4edda" if val <= lim_verde else "#fff3cd" if val <= lim_amarillo else "#f8d7da"
                        est[4] = f"background-color: {c}; font-weight: bold; color: #333;"
                        if stt == label_fin: est[2] = f"background-color: {c}; font-weight: bold; color: #333;"
                    return est

                cols_ver = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", col_stat, f"Ver_Trans_{proceso}"]
                df_dsp = df_show[cols_ver].copy()
                df_dsp.columns = ['Contenedor', 'Tipo', 'Tiempo', 'Estado', 'Minutos']
                st.dataframe(df_dsp.style.apply(pintar, axis=1).format({"Minutos": "{:.1f}"}), use_container_width=True, height=400)

        render_tab(tab1, "Conexión a Stacking")
        render_tab(tab2, "Desconexión para Embarque")
        render_tab(tab3, "Conexión OnBoard")

        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button(
            label="📥 Descargar Excel Completo",
            data=buffer.getvalue(),
            file_name=f"Reporte_{rotacion_real}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.error("Error crítico: No se pudieron procesar los datos.")
else:
    st.info("Esperando archivos... Revisa el panel de la izquierda.")
