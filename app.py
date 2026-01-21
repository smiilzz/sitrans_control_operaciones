import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Sitrans Control Operaciones", layout="wide", page_icon="🚢")

# --- CSS VISUAL (ESTILOS AVANZADOS) ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f6f9; }
    
    /* 1. Header Personalizado (Banner de Datos) */
    .header-data-box {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #003366; /* Azul Sitrans */
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
        display: flex;
        justify-content: space-around;
        align-items: center;
    }
    .header-item { text-align: center; }
    .header-label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
    .header-value { font-size: 22px; font-weight: bold; color: #003366; }

    /* 2. Pestañas (Tabs) estilo Botón Grande */
    /* Tab inactiva */
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #e0e0e0;
        border-radius: 5px 5px 0 0;
        gap: 2px;
        padding-top: 10px;
        padding-bottom: 10px;
        margin-right: 5px;
        font-weight: 600;
        color: #555;
    }
    /* Tab ACTIVA (Seleccionada) */
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #003366 !important;
        color: white !important;
        border-bottom: none;
    }
    /* Texto dentro de las tabs */
    .stTabs [data-baseweb="tab"] div[data-testid="stMarkdownContainer"] p {
        font-size: 18px !important; /* Letra más grande */
    }

    /* 3. KPI Cards */
    .kpi-card {
        padding: 15px;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px;
        height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .kpi-value { font-size: 28px; font-weight: bold; margin: 0; line-height: 1.2; }
    .kpi-label { font-size: 12px; font-weight: 500; opacity: 0.9; margin: 0; }
    
    .bg-green { background-color: #28a745; }
    .bg-yellow { background-color: #ffc107; color: #333 !important; }
    .bg-red { background-color: #dc3545; }

    /* 4. Alertas de Texto (CT y Normales) */
    .alert-box {
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 8px;
        text-align: center;
        font-weight: bold;
    }
    .alert-red { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .alert-green { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }

    /* 5. Filtros Pills (Botones redondos) */
    div[role="radiogroup"] {
        background-color: white;
        padding: 5px;
        border-radius: 10px;
        border: 1px solid #ddd;
        display: inline-flex;
        width: 100%;
        margin-bottom: 10px;
    }
    div[role="radiogroup"] label {
        flex: 1;
        text-align: center;
        background-color: transparent;
        border: none;
        margin: 0 2px;
        border-radius: 8px;
        padding: 8px 15px;
        font-weight: 500;
        cursor: pointer;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES SOPORTE (CACHEADAS) ---
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

@st.cache_data(show_spinner="Procesando datos...")
def procesar_datos_completos(files_rep_list, file_mon):
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
    df_mon_data = cargar_excel(file_mon, "UNIDAD")
    if df_mon_data is None: return None
    df_master = pd.merge(df_rep, df_mon_data, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
    
    cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
    presentes = [c for c in df_master.columns if c in cols_ct]
    if presentes: df_master['TIPO'] = df_master[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
    else: df_master['TIPO'] = 'General'
        
    cols_fecha_posibles = ["TIME_IN", "CONEXIÓN", "SOLICITUD DESCONEXIÓN", "DESCONECCIÓN", "TIME_LOAD", "CONEXIÓN ONBOARD"]
    for col in cols_fecha_posibles:
        if col in df_master.columns:
            df_master[col] = pd.to_datetime(df_master[col], dayfirst=True, errors='coerce')
    return df_master

# --- INTERFAZ ---
with st.sidebar:
    st.image("https://www.sitrans.cl/wp-content/themes/sitrans-child/img/logo-sitrans.png", width=180)
    st.header("Carga de Datos")
    files_rep_list = st.file_uploader("📂 1_Reportes", type=["xls", "xlsx"], accept_multiple_files=True)
    file_mon = st.file_uploader("📂 2_Monitor", type=["xlsx"])

if files_rep_list and file_mon:
    df_master = procesar_datos_completos(files_rep_list, file_mon)

    if df_master is not None:
        # --- 1. HEADER REORGANIZADO ---
        c_head_izq, c_head_der = st.columns([3, 1])
        opciones_rot = df_master['ROTACION_DETECTADA'].unique()
        
        with c_head_der:
            seleccion_rot = st.selectbox("⚓ Cambiar Rotación:", opciones_rot)

        df = df_master[df_master['ROTACION_DETECTADA'] == seleccion_rot].copy()
        nave = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
        fecha = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

        with c_head_izq:
            st.title("🚢 Control de Operaciones")
            
        # Banner de datos visualmente destacado (Debajo del título)
        st.markdown(f"""
        <div class="header-data-box">
            <div class="header-item">
                <div class="header-label">Nave</div>
                <div class="header-value">{nave}</div>
            </div>
            <div class="header-item">
                <div class="header-label">Fecha Consulta</div>
                <div class="header-value">{fecha}</div>
            </div>
            <div class="header-item">
                <div class="header-label">Rotación</div>
                <div class="header-value">{seleccion_rot}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # --- CÁLCULOS ---
        parejas = {
            "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
            "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
            "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
        }
        ahora = pd.Timestamp.now(tz='America/Santiago').tz_localize(None)

        for proceso, cols in parejas.items():
            df[f"Estado_{proceso}"] = "Sin Solicitud"
            df[f"Min_{proceso}"] = 0.0
            df[f"Ver_Tiempo_{proceso}"] = ""
            df[f"Ver_Trans_{proceso}"] = 0.0

            if cols["Ini"] in df.columns and cols["Fin"] in df.columns:
                cond = [
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].notna()), 
                    (df[cols["Ini"]].notna()) & (df[cols["Fin"]].isna()),  
                    (df[cols["Ini"]].isna())                           
                ]
                df[f"Estado_{proceso}"] = np.select(cond, ["Finalizado", "Pendiente", "Sin Solicitud"], default="Sin Solicitud")
                
                col_min = f"Min_{proceso}"
                mask_fin = df[f"Estado_{proceso}"] == "Finalizado"
                df.loc[mask_fin, col_min] = (df.loc[mask_fin, cols["Fin"]] - df.loc[mask_fin, cols["Ini"]]).dt.total_seconds() / 60
                
                mask_pen = df[f"Estado_{proceso}"] == "Pendiente"
                df.loc[mask_pen, col_min] = (ahora - df.loc[mask_pen, cols["Ini"]]).dt.total_seconds() / 60
                
                df[f"Ver_Tiempo_{proceso}"] = np.where(mask_fin, df[col_min].apply(formatear_duracion), "")
                df[f"Ver_Trans_{proceso}"] = np.where(mask_pen, df[col_min], 0)

        # --- TABS (Con iconos y estilo destacado) ---
        tab1, tab2, tab3 = st.tabs(["🔌 CONEXIÓN", "🔋 DESCONEXIÓN", "🚢 ONBOARD"])

        def render_tab(tab, proceso):
            with tab:
                col_stat = f"Estado_{proceso}"
                col_min = f"Min_{proceso}"
                
                df_activo = df[df[col_stat].isin(["Finalizado", "Pendiente"])].copy()
                
                if not df_activo.empty:
                    # Lógica Semáforo
                    cond_semaforo = [
                        df_activo[col_min] <= 15,
                        (df_activo[col_min] > 15) & (df_activo[col_min] <= 30),
                        df_activo[col_min] > 30
                    ]
                    df_activo['Semaforo'] = np.select(cond_semaforo, ['Verde', 'Amarillo', 'Rojo'], default='Rojo')
                    
                    # Lógica KPI y Cumplimiento
                    if proceso == "OnBoard": 
                        df_activo['Cumple'] = df_activo[col_min] <= 30
                    else:
                        cond_cumple = [
                            (df_activo['TIPO'] == 'CT') & (df_activo[col_min] <= 30),
                            (df_activo['TIPO'] == 'General') & (df_activo[col_min] <= 60)
                        ]
                        df_activo['Cumple'] = np.select(cond_cumple, [True, True], default=False)

                    # --- DASHBOARD VISUAL ---
                    c1, c2 = st.columns([1, 2])
                    
                    with c1: # Gráfico
                        conteos = df_activo['Semaforo'].value_counts().reset_index()
                        conteos.columns = ['Color', 'Cantidad']
                        fig = px.pie(conteos, values='Cantidad', names='Color', 
                                     color='Color', 
                                     color_discrete_map={'Verde':'#2ecc71', 'Amarillo':'#f1c40f', 'Rojo':'#e74c3c'}, 
                                     hole=0.6)
                        fig.update_layout(showlegend=True, margin=dict(t=0,b=0,l=0,r=0), height=200, legend=dict(orientation="h", y=-0.2))
                        st.plotly_chart(fig, use_container_width=True)

                    with c2: # Métricas
                        pct = (df_activo['Cumple'].sum() / len(df_activo)) * 100
                        
                        # Cálculos de Rojos (Fuera de Plazo)
                        rojos_ct = len(df_activo[(df_activo['TIPO']=='CT') & (~df_activo['Cumple'])])
                        rojos_normal = len(df_activo[(df_activo['TIPO']=='General') & (~df_activo['Cumple'])])

                        prom_g = df_activo[df_activo['TIPO']=='General'][col_min].mean()
                        prom_c = df_activo[df_activo['TIPO']=='CT'][col_min].mean()

                        bg_color = "bg-green" if pct >= 95 else "bg-yellow" if pct >= 85 else "bg-red"
                        
                        # Fila 1: KPI Principal y Alertas Apiladas
                        k1, k2 = st.columns([1, 1.2])
                        with k1:
                            st.markdown(f"""<div class="kpi-card {bg_color}"><p class="kpi-value">{pct:.1f}%</p><p class="kpi-label">CUMPLIMIENTO</p></div>""", unsafe_allow_html=True)
                        
                        with k2:
                            # Alerta CT
                            if rojos_ct > 0:
                                st.markdown(f"""<div class="alert-box alert-red">🚨 {rojos_ct} CT Fuera de Plazo</div>""", unsafe_allow_html=True)
                            else:
                                st.markdown(f"""<div class="alert-box alert-green">✅ CTs al día</div>""", unsafe_allow_html=True)
                            
                            # Alerta Normales
                            if rojos_normal > 0:
                                st.markdown(f"""<div class="alert-box alert-red">⚠️ {rojos_normal} Normales Fuera de Plazo</div>""", unsafe_allow_html=True)
                            else:
                                st.markdown(f"""<div class="alert-box alert-green">✅ Normales al día</div>""", unsafe_allow_html=True)

                        # Fila 2: Promedios al lado del KPI (abajo de lo anterior)
                        st.write("") # Espaciador
                        p1, p2 = st.columns(2)
                        p1.markdown(f"""<div class="metric-box"><div class="metric-val">{prom_g:.1f} min</div><div class="metric-lbl">Promedio General</div></div>""", unsafe_allow_html=True)
                        p2.markdown(f"""<div class="metric-box"><div class="metric-val">{prom_c:.1f} min</div><div class="metric-lbl">Promedio CT</div></div>""", unsafe_allow_html=True)

                else:
                    st.info(f"ℹ️ No hay actividad detectada para {proceso}.")

                st.divider()

                # --- TABLA Y FILTROS ---
                filtro = st.radio(f"f_{proceso}", ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], horizontal=True, label_visibility="collapsed", key=proceso)
                
                if filtro == "Todos": df_show = df
                else: df_show = df[df[col_stat] == filtro]

                # Métricas
                kd1, kd2, kd3 = st.columns(3)
                kd1.metric("📦 Vista Actual", len(df_show))
                kd2.metric("❄️ Normales", len(df_show[df_show['TIPO'] == 'General']))
                kd3.metric("⚡ CT (Reefers)", len(df_show[df_show['TIPO'] == 'CT']))

                # Tabla
                def pintar(row):
                    val = df.loc[row.name, col_min]
                    stt = df.loc[row.name, col_stat]
                    est = [''] * len(row)
                    if stt in ["Finalizado", "Pendiente"] and val > 0:
                        c = "#d4edda" if val<=15 else "#fff3cd" if val<=30 else "#f8d7da"
                        est[4] = f"background-color: {c}; font-weight: bold; color: #333;"
                        if stt == "Finalizado": est[2] = f"background-color: {c}; font-weight: bold; color: #333;"
                    return est

                cols_ver = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", col_stat, f"Ver_Trans_{proceso}"]
                df_dsp = df_show[cols_ver].copy()
                df_dsp.columns = ['Contenedor', 'Tipo', 'Tiempo', 'Estado', 'Minutos Transcurridos']
                
                st.dataframe(df_dsp.style.apply(pintar, axis=1).format({"Minutos Transcurridos": "{:.1f}"}), use_container_width=True, height=400)

        render_tab(tab1, "Conexión")
        render_tab(tab2, "Desconexión")
        render_tab(tab3, "OnBoard")

        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button(f"📥 Descargar Excel Completo", buffer.getvalue(), f"Reporte_{seleccion_rot}.xlsx")

    else:
        st.error("Error al procesar archivos.")
else:
    st.info("Sube los reportes.")
