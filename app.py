import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Sitrans Dashboard Multi-Rotación", layout="wide", page_icon="🚢")

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

st.title("🚢 Control de Operaciones - Sitrans (Multi-Rotación)")

# --- FUNCIONES DE SOPORTE ---
def formatear_duracion(minutos):
    if pd.isna(minutos) or minutos == 0: return ""
    segundos = int(minutos * 60)
    return f"{segundos//3600}:{(segundos%3600)//60:02d}:{segundos%60:02d}"

def extraer_metadatos(file):
    metadatos = {"Nave": "---", "Rotación": "Indefinida", "Fecha": "---"}
    try:
        # Leemos el encabezado
        df_head = pd.read_excel(file, header=None, nrows=20)
        file.seek(0) # Reset importante para volver a leer después
        
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
        file.seek(0)
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

# --- INTERFAZ DE CARGA ---
st.sidebar.header("Carga de Datos")
# CAMBIO 1: accept_multiple_files=True
files_rep_list = st.sidebar.file_uploader("📂 1_Reportes (Varios Archivos)", type=["xls", "xlsx"], accept_multiple_files=True)
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

if files_rep_list and file_mon:
    
    # --- PROCESAMIENTO MULTI-ARCHIVO ---
    lista_dfs_reportes = []
    
    with st.spinner('Consolidando múltiples rotaciones...'):
        # Recorremos cada archivo subido en la lista
        for archivo_rep in files_rep_list:
            # 1. Extraer metadata específica de ESTE archivo
            meta = extraer_metadatos(archivo_rep)
            
            # 2. Cargar la data
            df_individual = cargar_excel(archivo_rep, "CONTENEDOR")
            
            if df_individual is not None:
                # Limpieza básica
                df_individual = df_individual[df_individual['CONTENEDOR'].notna()]
                df_individual = df_individual[df_individual['CONTENEDOR'].astype(str).str.strip() != ""]
                df_individual = df_individual[~df_individual['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]
                
                # 3. ETIQUETADO: Agregamos columna con la Rotación y Nave de origen
                # Esto es clave para el filtro posterior
                df_individual['ROTACION_DETECTADA'] = meta['Rotación']
                df_individual['NAVE_DETECTADA'] = meta['Nave']
                df_individual['FECHA_CONSULTA'] = meta['Fecha']
                
                lista_dfs_reportes.append(df_individual)

    if lista_dfs_reportes:
        # Unimos todos los reportes en uno solo (hacia abajo)
        df_rep_total = pd.concat(lista_dfs_reportes, ignore_index=True)
        
        # Cargamos el Monitor (es uno solo para todos)
        df_mon = cargar_excel(file_mon, "UNIDAD")
        
        if df_mon is not None:
            # Cruce Maestro (Todos los contenedores de todas las rotaciones vs Monitor)
            df_master = pd.merge(df_rep_total, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            
            # --- FILTRO DE ROTACIÓN ---
            st.sidebar.divider()
            st.sidebar.subheader("🔍 Filtros de Visualización")
            
            # Obtenemos lista única de rotaciones detectadas
            opciones_rotacion = df_master['ROTACION_DETECTADA'].unique()
            seleccion_rotacion = st.sidebar.selectbox("Selecciona Rotación:", opciones_rotacion)
            
            # Filtramos el DataFrame Principal para el Dashboard
            df = df_master[df_master['ROTACION_DETECTADA'] == seleccion_rotacion].copy()
            
            # Recuperamos metadata de la selección para el header
            nave_actual = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
            fecha_actual = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

            # --- HEADER DINÁMICO ---
            with st.container():
                c1, c2, c3 = st.columns(3)
                c1.metric("📅 Fecha Consulta", fecha_actual)
                c2.metric("🚢 Nave", nave_actual)
                c3.metric("🔄 Rotación Seleccionada", seleccion_rotacion)
            st.divider()

            # --- A PARTIR DE AQUÍ, LA LÓGICA ES LA MISMA (PERO APLICA AL DF FILTRADO) ---
            
            # Clasificación CT
            cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
            presentes = [c for c in df.columns if c in cols_ct]
            if presentes:
                df['TIPO'] = df[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
            else:
                df['TIPO'] = 'General'

            parejas_calculo = {
                "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
                "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
                "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
            }

            ahora_chile = pd.Timestamp.now(tz='America/Santiago').tz_localize(None)

            for proceso, cols in parejas_calculo.items():
                col_ini, col_fin = cols["Ini"], cols["Fin"]
                if col_ini in df.columns and col_fin in df.columns:
                    df[col_ini] = pd.to_datetime(df[col_ini], dayfirst=True, errors='coerce')
                    df[col_fin] = pd.to_datetime(df[col_fin], dayfirst=True, errors='coerce')
                    
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

            # --- RENDERIZADO TABS ---
            tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

            def render_tab(tab, proceso):
                col_min = f"Min_{proceso}"
                col_stat = f"Estado_{proceso}"
                with tab:
                    if col_stat in df.columns:
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

                            col_izq, col_der = st.columns([1, 2])
                            with col_izq:
                                conteos = df_activo['Semaforo'].value_counts().reset_index()
                                conteos.columns = ['Color', 'Cantidad']
                                fig = px.pie(conteos, values='Cantidad', names='Color', 
                                             color='Color', color_discrete_map={'Verde':'#2ecc71', 'Amarillo':'#f1c40f', 'Rojo':'#e74c3c'}, hole=0.5)
                                fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=180)
                                st.subheader("🚦 Semáforo")
                                st.plotly_chart(fig, use_container_width=True)

                            with col_der:
                                pct = (df_activo['Cumple'].sum() / len(df_activo)) * 100
                                rojos_ct = len(df_activo[(df_activo['TIPO']=='CT') & (~df_activo['Cumple'])])
                                
                                k1, k2 = st.columns(2)
                                k1.metric("KPI Cumplimiento", f"{pct:.1f}%")
                                if rojos_ct > 0: k2.error(f"🚨 {rojos_ct} CT Fuera de Plazo")
                                else: k2.success("✅ CTs al día")
                                
                                k3, k4 = st.columns(2)
                                prom_g = df_activo[df_activo['TIPO']=='General'][col_min].mean()
                                prom_c = df_activo[df_activo['TIPO']=='CT'][col_min].mean()
                                k3.metric("Promedio General", f"{prom_g:.1f} min" if not pd.isna(prom_g) else "-")
                                k4.metric("Promedio CT", f"{prom_c:.1f} min" if not pd.isna(prom_c) else "-")
                        else:
                            st.info("Sin actividad registrada.")

                        st.divider()
                        filtro = st.radio(f"Ver:", ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], horizontal=True, key=proceso)
                        if filtro == "Todos": df_show = df
                        else: df_show = df[df[f"Estado_{proceso}"] == filtro]

                        def color_celdas(row):
                            min_val = df.loc[row.name, col_min]
                            st_val = df.loc[row.name, col_stat]
                            est = [''] * len(row)
                            if st_val in ["Finalizado", "Pendiente"] and pd.notna(min_val):
                                color = "#d4edda" if min_val <= 15 else "#fff3cd" if min_val <= 30 else "#f8d7da"
                                est[4] = f"background-color: {color}; color: black;" # Min Transcurridos
                                if st_val == "Finalizado": est[2] = f"background-color: {color}; color: black;" # Tiempo
                            return est

                        cols = ['CONTENEDOR', 'TIPO', f"Ver_Tiempo_{proceso}", f"Estado_{proceso}", f"Ver_Trans_{proceso}"]
                        df_dsp = df_show[cols].copy()
                        df_dsp.columns = ['Contenedor', 'Tipo', 'Tiempo', 'Estado', 'Minutos Transcurridos']
                        st.dataframe(df_dsp.style.apply(color_celdas, axis=1).format({"Minutos Transcurridos": "{:.1f}"}), use_container_width=True)

            render_tab(tab1, "Conexión")
            render_tab(tab2, "Desconexión")
            render_tab(tab3, "OnBoard")
            
            # Descarga del reporte FILTRADO por la rotación actual
            st.divider()
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            st.download_button(f"📥 Descargar Reporte Rotación {seleccion_rotacion}", buffer.getvalue(), f"Reporte_{seleccion_rotacion}.xlsx")
        else:
            st.error("Error al cargar Monitor.")
else:
    st.info("Sube los archivos (puedes subir varios reportes de contenedor a la vez).")
