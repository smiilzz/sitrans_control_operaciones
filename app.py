import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px

# Configuración de página (Layout Wide es obligatorio para el filtro a la derecha)
st.set_page_config(page_title="Sitrans Control Operaciones", layout="wide", page_icon="🚢")

# --- CSS PERSONALIZADO (AQUÍ ESTÁ LA MAGIA VISUAL) ---
st.markdown("""
    <style>
    /* 1. Fondo general más limpio */
    .stApp { background-color: #f4f6f9; }
    
    /* 2. Estilo para el KPI de Cumplimiento (Tarjeta de Color) */
    .kpi-card {
        padding: 20px;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .kpi-value { font-size: 32px; font-weight: bold; margin: 0; }
    .kpi-label { font-size: 14px; font-weight: 500; opacity: 0.9; margin: 0; }
    
    /* Colores del KPI */
    .bg-green { background-color: #28a745; }
    .bg-yellow { background-color: #ffc107; color: #333 !important; }
    .bg-red { background-color: #dc3545; }

    /* 3. Estilo para los Botones de Filtro (Parecen Tabs/Pastillas) */
    div[role="radiogroup"] {
        background-color: white;
        padding: 5px;
        border-radius: 10px;
        border: 1px solid #ddd;
        display: inline-flex;
        width: 100%;
    }
    div[role="radiogroup"] label {
        flex: 1;
        text-align: center;
        background-color: transparent;
        border: none;
        margin: 0 2px;
        border-radius: 8px;
        padding: 8px 15px;
        transition: all 0.2s;
        font-weight: 500;
    }
    /* Cuando un botón está seleccionado */
    div[role="radiogroup"] label[data-checked="true"] {
        background-color: #003366 !important; /* Azul Sitrans */
        color: white !important;
        font-weight: bold;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    /* 4. Métricas Promedio (Estilo Tarjeta Blanca) */
    .metric-box {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
    .metric-val { font-size: 20px; font-weight: bold; color: #003366; }
    .metric-lbl { font-size: 12px; color: #666; }

    /* 5. Ajuste del Selectbox (Filtro Rotación) para que se vea compacto */
    div[data-testid="stSelectbox"] > label { font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE SOPORTE (CACHEADAS) ---
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
def cargar_excel(file, palabra_clave):
    try:
        df_temp = pd.read_excel(file, header=None)
        for i, row in df_temp.iterrows():
            vals = [str(v).strip().upper() for v in row]
            if palabra_clave in vals:
                df = pd.read_excel(file, header=i)
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

@st.cache_data(show_spinner="Procesando Base de Datos...")
def procesar_datos_completos(files_rep_list, file_mon):
    lista_dfs_reportes = []
    for archivo_rep in files_rep_list:
        meta = extraer_metadatos(archivo_rep)
        df_individual = cargar_excel(archivo_rep, "CONTENEDOR")
        if df_individual is not None:
            df_individual = df_individual[df_individual['CONTENEDOR'].notna()]
            df_individual = df_individual[df_individual['CONTENEDOR'].astype(str).str.strip() != ""]
            df_individual = df_individual[~df_individual['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]
            df_individual['ROTACION_DETECTADA'] = meta['Rotación']
            df_individual['NAVE_DETECTADA'] = meta['Nave']
            df_individual['FECHA_CONSULTA'] = meta['Fecha']
            lista_dfs_reportes.append(df_individual)
            
    if not lista_dfs_reportes: return None
    df_rep_total = pd.concat(lista_dfs_reportes, ignore_index=True)
    df_mon_data = cargar_excel(file_mon, "UNIDAD")
    if df_mon_data is None: return None
    df_master = pd.merge(df_rep_total, df_mon_data, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
    
    cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
    presentes = [c for c in df_master.columns if c in cols_ct]
    if presentes: df_master['TIPO'] = df_master[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
    else: df_master['TIPO'] = 'General'

    parejas = {"Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"}, "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"}, "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}}
    for _, cols in parejas.items():
        if cols["Ini"] in df_master.columns: df_master[cols["Ini"]] = pd.to_datetime(df_master[cols["Ini"]], dayfirst=True, errors='coerce')
        if cols["Fin"] in df_master.columns: df_master[cols["Fin"]] = pd.to_datetime(df_master[cols["Fin"]], dayfirst=True, errors='coerce')
    return df_master

# --- INTERFAZ PRINCIPAL ---

# Sidebar solo para carga
with st.sidebar:
    st.image("https://www.sitrans.cl/wp-content/themes/sitrans-child/img/logo-sitrans.png", width=180)
    st.header("Carga de Datos")
    files_rep_list = st.file_uploader("📂 1_Reportes", type=["xls", "xlsx"], accept_multiple_files=True)
    file_mon = st.file_uploader("📂 2_Monitor", type=["xlsx"])
    st.markdown("---")
    st.markdown("Desarrollado para **TPS/Sitrans**")

if files_rep_list and file_mon:
    df_master = procesar_datos_completos(files_rep_list, file_mon)

    if df_master is not None:
        
        # --- HEADER SUPERIOR CON FILTRO A LA DERECHA ---
        # Creamos 2 columnas: Izquierda (Título y Datos) | Derecha (Filtro Rotación)
        col_header_izq, col_header_der = st.columns([3, 1])
        
        opciones_rotacion = df_master['ROTACION_DETECTADA'].unique()
        
        with col_header_der:
            # EL FILTRO ARRIBA A LA DERECHA
            seleccion_rotacion = st.selectbox("⚓ Seleccionar Rotación:", opciones_rotacion)

        # Filtrado de Datos
        df = df_master[df_master['ROTACION_DETECTADA'] == seleccion_rotacion].copy()
        nave_actual = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
        fecha_actual = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

        with col_header_izq:
            st.title(f"🚢 Control de Operaciones: {nave_actual}")
            # Sub-datos en línea
            st.markdown(f"**Fecha Consulta:** {fecha_actual} &nbsp; | &nbsp; **Rotación:** {seleccion_rotacion}", unsafe_allow_html=True)
        
        st.divider()

        # --- CÁLCULOS EN VIVO ---
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

        # --- TABS VISUALES ---
        tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

        def render_tab(tab, proceso):
            col_min = f"Min_{proceso}"
            col_stat = f"Estado_{proceso}"
            with tab:
                if col_stat in df.columns:
                    df_activo = df[df[col_stat].isin(["Finalizado", "Pendiente"])].copy()
                    
                    if not df_activo.empty:
                        # Lógica Semáforo y Cumplimiento
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

                        # --- LAYOUT DASHBOARD SUPERIOR ---
                        c_izq, c_der = st.columns([1, 2])
                        
                        # 1. GRÁFICO DONUT (Izquierda)
                        with c_izq:
                            conteos = df_activo['Semaforo'].value_counts().reset_index()
                            conteos.columns = ['Color', 'Cantidad']
                            fig = px.pie(conteos, values='Cantidad', names='Color', 
                                         color='Color', color_discrete_map={'Verde':'#2ecc71', 'Amarillo':'#f1c40f', 'Rojo':'#e74c3c'}, hole=0.6)
                            fig.update_layout(showlegend=True, margin=dict(t=20, b=20, l=20, r=20), height=250, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                            st.plotly_chart(fig, use_container_width=True)

                        # 2. METRICAS Y KPI (Derecha)
                        with c_der:
                            pct = (df_activo['Cumple'].sum() / len(df_activo)) * 100
                            rojos_ct = len(df_activo[(df_activo['TIPO']=='CT') & (~df_activo['Cumple'])])
                            prom_g = df_activo[df_activo['TIPO']=='General'][col_min].mean()
                            prom_c = df_activo[df_activo['TIPO']=='CT'][col_min].mean()

                            # Lógica de Color KPI (Verde >=95, Amarillo 85-95, Rojo <85)
                            color_class = "bg-red"
                            if pct >= 95: color_class = "bg-green"
                            elif pct >= 85: color_class = "bg-yellow"
                            
                            # Fila 1: KPI Grande y Alerta
                            k1, k2 = st.columns([1, 1])
                            with k1:
                                st.markdown(f"""
                                <div class="kpi-card {color_class}">
                                    <p class="kpi-value">{pct:.1f}%</p>
                                    <p class="kpi-label">KPI CUMPLIMIENTO</p>
                                </div>
                                """, unsafe_allow_html=True)
                            with k2:
                                if rojos_ct > 0:
                                    st.error(f"🚨 **ALERTA CRÍTICA**\n\n**{rojos_ct}** Contenedores Reefers (CT) están fuera de plazo.")
                                else:
                                    st.success("✅ **OPERACIÓN NORMAL**\n\nTodos los Reefers (CT) están dentro del tiempo objetivo.")

                            # Fila 2: Promedios (Cajas Blancas)
                            st.markdown("") # Espacio
                            p1, p2 = st.columns(2)
                            with p1:
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-val">{prom_g:.1f} min</div>
                                    <div class="metric-lbl">Promedio General</div>
                                </div>
                                """, unsafe_allow_html=True)
                            with p2:
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-val">{prom_c:.1f} min</div>
                                    <div class="metric-lbl">Promedio CT (Reefer)</div>
                                </div>
                                """, unsafe_allow_html=True)

                    st.markdown("---")

                    # --- FILTRO VISUAL TIPO BOTONES ---
                    filtro = st.radio(
                        f"filtro_{proceso}", # Key único invisible
                        ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], 
                        horizontal=True, 
                        label_visibility="collapsed", # Ocultamos la etiqueta "Estado en..."
                        key=proceso
                    )
                    
                    if filtro == "Todos": df_show = df
                    else: df_show = df[df[f"Estado_{proceso}"] == filtro]

                    # --- DETALLE DE CONTEO ---
                    kd1, kd2, kd3 = st.columns(3)
                    kd1.metric("📦 Total Vista", len(df_show))
                    kd2.metric("❄️ Normales", len(df_show[df_show['TIPO'] == 'General']))
                    kd3.metric("⚡ CT (Reefers)", len(df_show[df_show['TIPO'] == 'CT']))

                    # --- TABLA ---
                    def color_celdas(row):
                        min_val = df.loc[row.name, col_min]
                        st_val = df.loc[row.name, col_stat]
                        est = [''] * len(row)
                        if st_val in ["Finalizado", "Pendiente"] and pd.notna(min_val):
                            color = "#d4edda" if min_val <= 15 else "#fff3cd" if min_val <= 30 else "#f8d7da"
                            est[4] = f"background-color: {color}; color: black; font-weight: bold;"
                            if st_val == "Finalizado": est[2] = f"background-color: {color}; color: black; font-weight: bold;"
                        return est

                    cols = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", f"Estado_{proceso}", f"Ver_Trans_{proceso}"]
                    df_dsp = df_show[cols].copy()
                    df_dsp.columns = ['Contenedor', 'Tipo', 'Tiempo', 'Estado', 'Minutos Transcurridos']
                    
                    st.dataframe(
                        df_dsp.style.apply(color_celdas, axis=1)
                        .format({"Minutos Transcurridos": "{:.1f}"}), 
                        use_container_width=True,
                        height=400
                    )

            render_tab(tab1, "Conexión")
            render_tab(tab2, "Desconexión")
            render_tab(tab3, "OnBoard")
            
            # Footer y Descarga
            st.markdown("---")
            col_d1, col_d2 = st.columns([4, 1])
            with col_d2:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                st.download_button(
                    f"📥 Descargar Excel", 
                    buffer.getvalue(), 
                    f"Reporte_{seleccion_rotacion}.xlsx",
                    use_container_width=True,
                    type="primary"
                )

    else:
        st.warning("⚠️ El formato del archivo no parece correcto o faltan datos clave.")
else:
    # Pantalla de bienvenida vacía
    st.info("👋 Sube los archivos en la barra lateral izquierda para comenzar.")
