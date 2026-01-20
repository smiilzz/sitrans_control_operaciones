import streamlit as st
import pandas as pd
import io
import re
import numpy as np
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Sitrans Dashboard Dinámico", layout="wide", page_icon="🚢")

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
        df_head = pd.read_excel(file, header=None, nrows=20)
        file.seek(0)
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

# --- CARGA DE DATOS ---
st.sidebar.header("Carga de Datos")
files_rep_list = st.sidebar.file_uploader("📂 1_Reportes (Varios Archivos)", type=["xls", "xlsx"], accept_multiple_files=True)
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

if files_rep_list and file_mon:
    lista_dfs_reportes = []
    
    with st.spinner('Procesando archivos...'):
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

    if lista_dfs_reportes:
        df_rep_total = pd.concat(lista_dfs_reportes, ignore_index=True)
        df_mon = cargar_excel(file_mon, "UNIDAD")
        
        if df_mon is not None:
            df_master = pd.merge(df_rep_total, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            
            # FILTRO ROTACIÓN
            st.sidebar.divider()
            st.sidebar.subheader("🔍 Filtros")
            opciones_rotacion = df_master['ROTACION_DETECTADA'].unique()
            seleccion_rotacion = st.sidebar.selectbox("Selecciona Rotación:", opciones_rotacion)
            
            df = df_master[df_master['ROTACION_DETECTADA'] == seleccion_rotacion].copy()
            
            # Header
            nave_actual = df['NAVE_DETECTADA'].iloc[0] if not df.empty else "---"
            fecha_actual = df['FECHA_CONSULTA'].iloc[0] if not df.empty else "---"

            with st.container():
                c1, c2, c3 = st.columns(3)
                c1.metric("📅 Fecha Consulta", fecha_actual)
                c2.metric("🚢 Nave", nave_actual)
                c3.metric("🔄 Rotación", seleccion_rotacion)
            st.divider()
            
            # Lógica CT
            cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
            presentes = [c for c in df.columns if c in cols_ct]
            if presentes:
                df['TIPO'] = df[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
            else:
                df['TIPO'] = 'General'

            # Lógica Tiempos
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

            # TABS
            tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

            def render_tab(tab, proceso):
                col_min = f"Min_{proceso}"
                col_stat = f"Estado_{proceso}"
                with tab:
                    if col_stat in df.columns:
                        # 1. Dashboard Superior (Gráfico + KPI Cumplimiento)
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

                        # 2. FILTRO Y MÉTRICAS DINÁMICAS (Aquí está lo nuevo)
                        filtro = st.radio(f"Estado en {proceso}:", ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], horizontal=True, key=proceso)
                        
                        # Aplicamos el filtro a los datos
                        if filtro == "Todos": df_show = df
                        else: df_show = df[df[f"Estado_{proceso}"] == filtro]

                        # --- KPI DINÁMICOS DEL FILTRO ACTUAL ---
                        # Se calculan sobre df_show (que ya está filtrado)
                        st.markdown(f"**📊 Detalle para selección: {filtro}**")
                        kd1, kd2, kd3 = st.columns(3)
                        
                        total_filtrado = len(df_show)
                        normal_filtrado = len(df_show[df_show['TIPO'] == 'General'])
                        ct_filtrado = len(df_show[df_show['TIPO'] == 'CT'])
                        
                        kd1.metric("📦 Total Listados", total_filtrado)
                        kd2.metric("❄️ Normales", normal_filtrado)
                        kd3.metric("⚡ CT (Reefers)", ct_filtrado)
                        # ----------------------------------------

                        # 3. TABLA
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
            st.download_button(f"📥 Descargar Datos ({seleccion_rotacion})", buffer.getvalue(), f"Reporte_{seleccion_rotacion}.xlsx")
        else:
            st.error("Error al cargar Monitor.")
else:
    st.info("Sube los archivos para comenzar.")
