import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Sitrans Logistics Hub", layout="wide", page_icon="🚢")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Hub de Gestión Reefers - Sitrans")

# --- FUNCIONES DE INGENIERÍA ---

def extraer_metadatos(file):
    """Busca Nave, Rotación y Fecha en las primeras filas del Excel."""
    metadatos = {"Nave": "No encontrada", "Rotación": "-", "Fecha": "-"}
    try:
        # Leemos solo las primeras 10 filas para no cargar todo el archivo
        df_head = pd.read_excel(file, header=None, nrows=10)
        
        # Convertimos todo a texto para buscar fácil
        texto_completo = df_head.astype(str).apply(lambda x: ' '.join(x), axis=1)

        # Buscamos fila por fila
        for i, row in df_head.iterrows():
            fila_txt = " ".join([str(x) for x in row if pd.notna(x)]).upper()
            
            # Lógica simple de búsqueda (ajusta según tu reporte real)
            if "NAVE" in fila_txt:
                # Intenta buscar el valor en la celda siguiente a la palabra "Nave"
                for j, val in enumerate(row):
                    if isinstance(val, str) and "NAVE" in val.upper():
                        if j + 1 < len(row): metadatos["Nave"] = str(row[j+1])
                        break
            
            if "VIAJE" in fila_txt or "ROTACIÓN" in fila_txt or "ROTACION" in fila_txt:
                for j, val in enumerate(row):
                    if isinstance(val, str) and ("ROTACION" in val.upper() or "ROTACIÓN" in val.upper()):
                        if j + 1 < len(row): metadatos["Rotación"] = str(row[j+1])
                        break
            
            if "FECHA" in fila_txt:
                 # A veces la fecha está en la misma celda tipo "Fecha: 20/01/2026"
                 metadatos["Fecha"] = fila_txt.replace("FECHA", "").replace(":", "").strip()[:10]

        file.seek(0) # IMPORTANTE: Rebobinar el archivo para leerlo después
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

def cargar_excel_detectando_header(file, palabra_clave):
    try:
        df_temp = pd.read_excel(file, header=None)
        for i, row in df_temp.iterrows():
            row_values = [str(val).strip().upper() for val in row]
            if palabra_clave in row_values:
                file.seek(0)
                df = pd.read_excel(file, header=i)
                df.columns = [str(c).strip().upper() for c in df.columns]
                df = desduplicar_columnas(df)
                return df
        return None
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- INTERFAZ LATERAL ---
st.sidebar.header("Carga de Documentos")
file_rep = st.sidebar.file_uploader("📂 1_Reporte (Contenedor)", type=["xls", "xlsx"])
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

# --- LÓGICA PRINCIPAL ---
if file_rep and file_mon:
    # 1. Extraer Metadatos ANTES de procesar
    meta = extraer_metadatos(file_rep)
    
    # Mostrar encabezado con datos del viaje
    c1, c2, c3 = st.columns(3)
    c1.info(f"📅 **Fecha:** {meta.get('Fecha', '-')}")
    c2.info(f"🚢 **Nave:** {meta.get('Nave', '-')}")
    c3.info(f"🔄 **Rotación:** {meta.get('Rotación', '-')}")

    with st.spinner('Procesando...'):
        df_rep = cargar_excel_detectando_header(file_rep, "CONTENEDOR")
        df_mon = cargar_excel_detectando_header(file_mon, "UNIDAD")

        if df_rep is not None and df_mon is not None:
            # Limpieza
            df_rep = df_rep[df_rep['CONTENEDOR'].notna()]
            df_rep = df_rep[df_rep['CONTENEDOR'].astype(str).str.strip() != ""]
            df_rep = df_rep[~df_rep['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]

            # Cruce
            df_final = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            df_final = df_final.loc[:, ~df_final.columns.str.contains('^UNNAMED')]

            # Lógica Normal vs CT
            cols_ct_target = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
            cols_ct_presentes = [c for c in df_final.columns if c in cols_ct_target]

            if cols_ct_presentes:
                es_ct = df_final[cols_ct_presentes].notna().any(axis=1)
                cant_ct = es_ct.sum()
                cant_normal = len(df_final) - cant_ct
                df_final['TIPO_REEFER'] = es_ct.apply(lambda x: 'CT' if x else 'NORMAL')
            else:
                cant_ct = 0
                cant_normal = len(df_final)
                df_final['TIPO_REEFER'] = 'NORMAL'

            # Métricas de Resumen
            st.divider()
            k1, k2, k3 = st.columns(3)
            k1.metric("Total Contenedores", len(df_final))
            k2.metric("Reefers Normales", int(cant_normal))
            k3.metric("Reefers CT (Controlados)", int(cant_ct), delta_color="inverse")

            st.dataframe(df_final, use_container_width=True)

            # Descarga
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button("📥 Descargar Excel Consolidado", buffer.getvalue(), "Reporte_Sitrans.xlsx")

else:
    st.info("Sube los archivos para ver la información de la Nave y el detalle de carga.")
