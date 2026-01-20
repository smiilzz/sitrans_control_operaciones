import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px # Importamos Plotly para los gráficos

# Configuración de página
st.set_page_config(page_title="Sitrans Dashboard", layout="wide", page_icon="🚢")

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
    /* Estilo para las métricas grandes de KPI */
    .big-font {
        font-size: 24px !important;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Control de Operaciones - Sitrans")

# --- FUNCIONES DE SOPORTE ---
def formatear_duracion(minutos):
    """Convierte minutos float a HH:MM:SS"""
    if pd.isna(minutos) or minutos == 0: return ""
    segundos = int(minutos * 60)
    return f"{segundos//3600}:{(segundos%3600)//60:02d}:{segundos%60:02d}"

def extraer_metadatos(file):
    metadatos = {"Nave": "---", "Rotación": "---", "Fecha": "---"}
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
        file.seek(0)
        return metadatos
    except:
        file.seek(0)
        return metadatos

def desduplicar_columnas(df):
    cols = pd.Series(df.columns)
    for i, col in enumerate(df.columns):
        if (cols == col).sum() > 1:
            count = (cols[:i] == col).sum()
            if count > 0: cols[i] = f"{col}.{count}"
    df.columns = cols
    return df

def cargar_excel(file, palabra_clave):
    try:
        df_temp = pd.read_excel(file, header=None)
        for i, row in df_temp.iterrows():
            vals = [str(v).strip().upper() for v in row]
            if palabra_clave in vals:
                file.seek(0)
                df = pd.read_excel(file, header=i)
                df.columns = [str(c).strip().upper() for c in df.columns]
                df = desduplicar_columnas(df)
                return df
        return None
    except: return None

# --- INTERFAZ ---
st.sidebar.header("Carga de Datos")
file_rep = st.sidebar.file_uploader("📂 1_Reporte", type=["xls", "xlsx"])
file_mon = st.sidebar.file_uploader("📂 2_Monitor", type=["xlsx"])

if file_rep and file_mon:
    meta = extraer_metadatos(file_rep)
    with st.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("📅 Fecha Consulta", meta.get('Fecha', '---'))
        c2.metric("🚢 Nave", meta.get('Nave', '---'))
        c3.metric("🔄 Rotación", meta.get('Rotación', '---'))
    st.divider()

    df_rep = cargar_excel(file_rep, "CONTENEDOR")
    df_mon = cargar_excel(file_mon, "UNIDAD")

    if df_rep is not None and df_mon is not None:
        # Limpieza
        df_rep = df_rep[df_rep['CONTENEDOR'].notna()]
        df_rep = df_rep[df_rep['CONTENEDOR'].astype(str).str.strip() != ""]
        df_rep = df_rep[~df_rep['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]

        # Cruce
        df = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
        
        # Clasificación CT vs General
        cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
        presentes = [c for c in df.columns if c in cols_ct]
        if presentes:
            df['TIPO'] = df[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
        else:
            df['TIPO'] = 'General'

        # Configuración de Procesos
        parejas_calculo = {
            "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
            "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
            "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
        }

        # Hora Actual Chile
        ahora_chile = pd.Timestamp.now(tz='America/Santiago').tz_localize(None)

        # --- BUCLE DE CÁLCULO ---
        for proceso, cols in parejas_calculo.items():
            col_ini, col_fin = cols["Ini"], cols["Fin"]
            
            if col_ini in df.columns and col_fin in df.columns:
                df[col_ini] = pd.to_datetime(df[col_ini], dayfirst=True, errors='coerce')
                df[col_fin] = pd.to_datetime(df[col_fin], dayfirst=True, errors='coerce')
                
                # Estados
                condiciones = [
                    (df[col_ini].notna()) & (df[col_fin].notna()), 
                    (df[col_ini].notna()) & (df[col_fin].isna()),  
                    (df[col_ini].isna())                           
                ]
                df[f"Estado_{proceso}"] = np.select(condiciones, ["Finalizado", "Pendiente", "Sin Solicitud"], default="Sin Solicitud")

                # Minutos Reales (Numerico para cálculo)
                col_min = f"Min_{proceso}"
                # A. Finalizado
                df.loc[df[f"Estado_{proceso}"] == "Finalizado", col_min] = (df[col_fin] - df[col_ini]).dt.total_seconds() / 60
                # B. Pendiente (En Vivo)
                df.loc[df[f"Estado_{proceso}"] == "Pendiente", col_min] = (ahora_chile - df[col_ini]).dt.total_seconds() / 60
                # C. Sin Solicitud
                df.loc[df[f"Estado_{proceso}"] == "Sin Solicitud", col_min] = 0

                # Columnas Visuales
                df[f"Ver_Tiempo_{proceso}"] = np.where(df[f"Estado_{proceso}"] == "Finalizado", df[col_min].apply(formatear_duracion), "")
                df[f"Ver_Trans_{proceso}"] = np.where(df[f"Estado_{proceso}"] == "Pendiente", df[col_min], 0)

        # --- VISUALIZACIÓN ---
        tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

        def render_tab(tab, proceso):
            col_min = f"Min_{proceso}"
            col_stat = f"Estado_{proceso}"
            
            with tab:
                if col_stat in df.columns:
                    # 1. PREPARACIÓN DE DATOS KPI
                    # Filtramos solo lo que tiene actividad (Finalizado o Pendiente)
                    df_activo = df[df[col_stat].isin(["Finalizado", "Pendiente"])].copy()
                    
                    if not df_activo.empty:
                        # --- CLASIFICACIÓN SEMÁFORO (0-15, 15-30, >30) ---
                        cond_semaforo = [
                            df_activo[col_min] <= 15,
                            (df_activo[col_min] > 15) & (df_activo[col_min] <= 30),
                            df_activo[col_min] > 30
                        ]
                        df_activo['Semaforo'] = np.select(cond_semaforo, ['Verde', 'Amarillo', 'Rojo'], default='Rojo')
                        
                        # --- CLASIFICACIÓN CUMPLIMIENTO (REGLAS DE NEGOCIO) ---
                        # OnBoard: Todo < 30 min
                        # Conex/Desconex: CT < 30 min, General < 60 min
                        if proceso == "OnBoard":
                            df_activo['Cumple'] = df_activo[col_min] <= 30
                        else:
                            cond_cumple = [
                                (df_activo['TIPO'] == 'CT') & (df_activo[col_min] <= 30),
                                (df_activo['TIPO'] == 'General') & (df_activo[col_min] <= 60)
                            ]
                            df_activo['Cumple'] = np.select(cond_cumple, [True, True], default=False)

                        # --- DASHBOARD SUPERIOR (GRÁFICO + TARJETAS) ---
                        col_izq, col_der = st.columns([1, 2])
                        
                        with col_izq:
                            # GRÁFICO DONUT
                            conteos_semaforo = df_activo['Semaforo'].value_counts().reset_index()
                            conteos_semaforo.columns = ['Color', 'Cantidad']
                            
                            # Mapa de colores oficial
                            color_map = {'Verde': '#2ecc71', 'Amarillo': '#f1c40f', 'Rojo': '#e74c3c'}
                            
                            fig = px.pie(conteos_semaforo, values='Cantidad', names='Color', 
                                         color='Color', color_discrete_map=color_map, hole=0.5)
                            fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=180)
                            
                            st.subheader("🚦 Semáforo Tiempos")
                            st.plotly_chart(fig, use_container_width=True)

                        with col_der:
                            # TARJETAS DE INDICADORES
                            pct_cumplimiento = (df_activo['Cumple'].sum() / len(df_activo)) * 100
                            rojos_ct = len(df_activo[(df_activo['TIPO']=='CT') & (~df_activo['Cumple'])])
                            
                            # Fila 1: KPI Principal y Alerta
                            k1, k2 = st.columns(2)
                            k1.metric("KPI Cumplimiento Global", f"{pct_cumplimiento:.1f}%")
                            if rojos_ct > 0:
                                k2.error(f"🚨 {rojos_ct} CT Fuera de Plazo")
                            else:
                                k2.success("✅ CTs al día")

                            # Fila 2: Promedios
                            k3, k4 = st.columns(2)
                            prom_gen = df_activo[df_activo['TIPO']=='General'][col_min].mean()
                            prom_ct = df_activo[df_activo['TIPO']=='CT'][col_min].mean()
                            
                            k3.metric("Promedio General", f"{prom_gen:.1f} min" if not pd.isna(prom_gen) else "-")
                            k4.metric("Promedio CT", f"{prom_ct:.1f} min" if not pd.isna(prom_ct) else "-")

                    else:
                        st.info("No hay operaciones iniciadas para generar gráficos.")

                    st.divider()

                    # --- TABLA DE DETALLE ---
                    filtro = st.radio(f"Filtro {proceso}:", ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], horizontal=True, key=proceso)
                    
                    if filtro == "Todos": df_show = df
                    else: df_show = df[df[f"Estado_{proceso}"] == filtro]

                    # Preparar columnas
                    cols_finales = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", f"Estado_{proceso}", f"Ver_Trans_{proceso}"]
                    df_display = df_show[cols_finales].copy()
                    df_display.columns = ['Contenedor', 'Categoría', 'Tiempo', 'Estado', 'Minutos Transcurridos']

                    # --- FORMATEO CONDICIONAL DE COLORES ---
                    # Usamos el dataframe original 'df' para mirar los valores numéricos
                    # Requerimos alinear índices. df_display conserva el índice de df_show
                    
                    def colorear_celdas(row):
                        idx = row.name
                        # Obtenemos el valor numérico real
                        minutos_reales = df.loc[idx, col_min]
                        estado = df.loc[idx, f"Estado_{proceso}"]
                        
                        estilos = [''] * len(row)
                        
                        if estado in ["Finalizado", "Pendiente"] and pd.notna(minutos_reales):
                            # Definir color de fondo según regla 15/30
                            bg_color = ""
                            if minutos_reales <= 15: bg_color = "background-color: #d4edda; color: #155724;" # Verde claro
                            elif 15 < minutos_reales <= 30: bg_color = "background-color: #fff3cd; color: #856404;" # Amarillo
                            else: bg_color = "background-color: #f8d7da; color: #721c24; font-weight: bold;" # Rojo
                            
                            # Aplicar a columna "Minutos Transcurridos" (índice 4)
                            estilos[4] = bg_color
                            
                            # Si está finalizado, aplicar también a "Tiempo" (índice 2)
                            if estado == "Finalizado":
                                estilos[2] = bg_color
                        
                        return estilos

                    st.dataframe(
                        df_display.style.apply(colorear_celdas, axis=1)
                        .format({"Minutos Transcurridos": "{:.1f}"}),
                        use_container_width=True
                    )
        
        render_tab(tab1, "Conexión")
        render_tab(tab2, "Desconexión")
        render_tab(tab3, "OnBoard")

        # Descarga
        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Descargar Reporte Full", buffer.getvalue(), "Sitrans_Reporte.xlsx")

else:
    st.info("👋 Sube los archivos para ver el Dashboard.")
