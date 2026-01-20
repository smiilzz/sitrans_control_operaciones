import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Sitrans Dashboard Pro", layout="wide", page_icon="🚢")

st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Control de Operaciones - Sitrans (Optimizado)")

# --- 1. FUNCIONES CACHEADAS (La clave para que no se reinicie) ---

@st.cache_data(show_spinner=False)
def formatear_duracion(minutos):
    if pd.isna(minutos) or minutos == 0: return ""
    segundos = int(minutos * 60)
    return f"{segundos//3600}:{(segundos%3600)//60:02d}:{segundos%60:02d}"

@st.cache_data(show_spinner=False)
def extraer_metadatos(file):
    metadatos = {"Nave": "---", "Rotación": "Indefinida", "Fecha": "---"}
    try:
        df_head = pd.read_excel(file, header=None, nrows=20)
        # Importante: No hacemos seek(0) aquí porque pandas lee bytes, 
        # lo haremos en la función de carga principal.
        
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
    except:
        return metadatos

@st.cache_data(show_spinner=False)
def cargar_excel(file, palabra_clave):
    try:
        df_temp = pd.read_excel(file, header=None)
        for i, row in df_temp.iterrows():
            vals = [str(v).strip().upper() for v in row]
            if palabra_clave in vals:
                df = pd.read_excel(file, header=i)
                # Limpieza de columnas duplicadas
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

# --- 2. PROCESADOR MAESTRO (Aquí ocurre la magia de velocidad) ---
@st.cache_data(show_spinner="Procesando Base de Datos...")
def procesar_datos_completos(files_rep_list, file_mon):
    """
    Esta función hace TODO el trabajo pesado y guarda el resultado en memoria.
    Si cambias un filtro, Streamlit usará el resultado guardado aquí en vez de recalcular.
    """
    lista_dfs_reportes = []
    
    # Procesar Reportes
    for archivo_rep in files_rep_list:
        meta = extraer_metadatos(archivo_rep)
        df_individual = cargar_excel(archivo_rep, "CONTENEDOR")
        
        if df_individual is not None:
            # Limpieza
            df_individual = df_individual[df_individual['CONTENEDOR'].notna()]
            df_individual = df_individual[df_individual['CONTENEDOR'].astype(str).str.strip() != ""]
            df_individual = df_individual[~df_individual['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]
            
            # Etiquetas
            df_individual['ROTACION_DETECTADA'] = meta['Rotación']
            df_individual['NAVE_DETECTADA'] = meta['Nave']
            df_individual['FECHA_CONSULTA'] = meta['Fecha']
            
            lista_dfs_reportes.append(df_individual)
            
    if not lista_dfs_reportes:
        return None

    # Unir y cruzar con Monitor
    df_rep_total = pd.concat(lista_dfs_reportes, ignore_index=True)
    df_mon_data = cargar_excel(file_mon, "UNIDAD")
    
    if df_mon_data is None:
        return None
        
    df_master = pd.merge(df_rep_total, df_mon_data, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
    
    # Lógica de Negocio (Tipos y Fechas) se procesa AQUÍ una sola vez
    cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
    presentes = [c for c in df_master.columns if c in cols_ct]
    if presentes:
        df_master['TIPO'] = df_master[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
    else:
        df_master['TIPO'] = 'General'

    # Convertir fechas de una vez para todo el dataset
    parejas = {
        "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
        "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
        "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
    }
    
    for proceso, cols in parejas.items():
        if cols["Ini"] in df_master.columns:
            df_master[cols["Ini"]] = pd.to_datetime(df_master[cols["Ini"]], dayfirst=True, errors='coerce')
        if cols["Fin"] in df_master.columns:
            df_master[cols["Fin"]] = pd.to_datetime(df_master[cols["Fin"]], dayfirst=True, errors='coerce')

    return df_master

# --- 3. INTERFAZ PRINCIPAL ---

st.sidebar.header("Carga de Datos")
files_rep_list = st.sidebar.file_uploader("📂 1_Reportes (Varios Archivos)", type=["xls", "xlsx"], accept_multiple_files=True)
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

if files_rep_list and file_mon:
    
    # LLAMADA CACHEADA (Esto es lo que evita el reseteo)
    df_master = procesar_datos_completos(files_rep_list, file_mon)

    if df_master is not None:
        # --- LÓGICA DE FILTRADO VISUAL (Esto es rápido y no recarga la página) ---
        
        st.sidebar.divider()
        opciones_rotacion = df_master['ROTACION_DETECTADA'].unique()
        seleccion_rotacion = st.sidebar.selectbox("Selecciona Rotación:", opciones_rotacion)
        
        # Filtramos el DF que ya está en memoria
        df = df_master[df_master['ROTACION_DETECTADA'] == seleccion_rotacion].copy()
        
        nave_actual = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
        fecha_actual = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

        with st.container():
            c1, c2, c3 = st.columns(3)
            c1.metric("📅 Fecha Consulta", fecha_actual)
            c2.metric("🚢 Nave", nave_actual)
            c3.metric("🔄 Rotación", seleccion_rotacion)
        st.divider()

        # Recálculo de Tiempos "En Vivo" (Esto sí debe hacerse en cada interacción para ser exacto)
        parejas_calculo = {
            "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
            "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
            "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
        }
        ahora_chile = pd.Timestamp.now(tz='America/Santiago').tz_localize(None)

        for proceso, cols in parejas_calculo.items():
            col_ini, col_fin = cols["Ini"], cols["Fin"]
            if col_ini in df.columns and col_fin in df.columns:
                condiciones = [
                    (df[col_ini].notna()) & (df[col_fin].notna()), 
                    (df[col_ini].notna()) & (df[col_fin].isna()),  
                    (df[col_ini].isna())                           
                ]
                df[f"Estado_{proceso}"] = np.select(condiciones, ["Finalizado", "Pendiente", "Sin Solicitud"], default="Sin Solicitud")

                col_min = f"Min_{proceso}"
                df.loc[df[f"Estado_{proceso}"] == "Finalizado", col_min] = (df[col_fin] - df[col_ini]).dt.total_seconds() / 60
                df.loc[df[f"Estado_{proceso}"] == "Pendiente", col_min] = (ahora_chile - df[col_ini]).dt.total_seconds() / 60
                df.loc[df[f"Estado_{proceso}"] == "Sin Solicitud", col_min] = 0

                df[f"Ver_Tiempo_{proceso}"] = np.where(df[f"Estado_{proceso}"] == "Finalizado", df[col_min].apply(formatear_duracion), "")
                df[f"Ver_Trans_{proceso}"] = np.where(df[f"Estado_{proceso}"] == "Pendiente", df[col_min], 0)

        # RENDERIZADO DE TABS
        tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

        def render_tab(tab, proceso):
            col_min = f"Min_{proceso}"
            col_stat = f"Estado_{proceso}"
            with tab:
                if col_stat in df.columns:
                    # DASHBOARD SUPERIOR
                    df_activo = df[df[col_stat].isin(["Finalizado", "Pendiente"])].copy()
                    
                    if not df_activo.empty:
                        cond_semaforo = [
                            df_activo[col_min] <= 15,
                            (df_activo[col_min] > 15) & (df_activo[col_min] <= 30),
                            df_activo[col_min] > 30
                        ]
                        df_activo['Semaforo'] = np.select(cond_semaforo, ['Verde', 'Amarillo', 'Rojo'], default='Rojo')
                        
                        if proceso == "OnBoard": df_activo['Cumple'] = df_activo[col_min] <= 30
                        else:
                            cond_cumple = [
                                (df_activo['TIPO'] == 'CT') & (df_activo[col_min] <= 30),
                                (df_activo['TIPO'] == 'General') & (df_activo[col_min] <= 60)
                            ]
                            df_activo['Cumple'] = np.select(cond_cumple, [True, True], default=False)

                        c_izq, c_der = st.columns([1, 2])
                        with c_izq:
                            conteos = df_activo['Semaforo'].value_counts().reset_index()
                            conteos.columns = ['Color', 'Cantidad']
                            fig = px.pie(conteos, values='Cantidad', names='Color', 
                                         color='Color', color_discrete_map={'Verde':'#2ecc71', 'Amarillo':'#f1c40f', 'Rojo':'#e74c3c'}, hole=0.5)
                            fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=180)
                            st.plotly_chart(fig, use_container_width=True)

                        with c_der:
                            pct = (df_activo['Cumple'].sum() / len(df_activo)) * 100
                            rojos_ct = len(df_activo[(df_activo['TIPO']=='CT') & (~df_activo['Cumple'])])
                            k1, k2 = st.columns(2)
                            k1.metric("KPI Cumplimiento", f"{pct:.1f}%")
                            if rojos_ct > 0: k2.error(f"🚨 {rojos_ct} CT Fuera de Plazo")
                            else: k2.success("✅ CTs al día")

                    st.divider()

                    # FILTROS Y TABLA
                    filtro = st.radio(f"Estado en {proceso}:", ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], horizontal=True, key=proceso)
                    
                    if filtro == "Todos": df_show = df
                    else: df_show = df[df[f"Estado_{proceso}"] == filtro]

                    # KPIs DINÁMICOS DEL FILTRO
                    st.markdown(f"**📊 Detalle: {filtro}**")
                    kd1, kd2, kd3 = st.columns(3)
                    kd1.metric("📦 Total", len(df_show))
                    kd2.metric("❄️ Normales", len(df_show[df_show['TIPO'] == 'General']))
                    kd3.metric("⚡ CT (Reefers)", len(df_show[df_show['TIPO'] == 'CT']))

                    # TABLA
                    def color_celdas(row):
                        min_val = df.loc[row.name, col_min]
                        st_val = df.loc[row.name, col_stat]
                        est = [''] * len(row)
                        if st_val in ["Finalizado", "Pendiente"] and pd.notna(min_val):
                            color = "#d4edda" if min_val <= 15 else "#fff3cd" if min_val <= 30 else "#f8d7da"
                            est[4] = f"background-color: {color}; color: black;"
                            if st_val == "Finalizado": est[2] = f"background-color: {color}; color: black;"
                        return est

                    cols = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", f"Estado_{proceso}", f"Ver_Trans_{proceso}"]
                    df_dsp = df_show[cols].copy()
                    df_dsp.columns = ['Contenedor', 'Tipo', 'Tiempo', 'Estado', 'Minutos Transcurridos']
                    
                    st.dataframe(df_dsp.style.apply(color_celdas, axis=1).format({"Minutos Transcurridos": "{:.1f}"}), use_container_width=True)

        render_tab(tab1, "Conexión")
        render_tab(tab2, "Desconexión")
        render_tab(tab3, "OnBoard")

        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button(f"📥 Descargar Reporte ({seleccion_rotacion})", buffer.getvalue(), f"Reporte_{seleccion_rotacion}.xlsx")
    else:
        st.error("Hubo un error al procesar los archivos. Verifica el formato.")
else:
    st.info("Sube los archivos para comenzar.")
