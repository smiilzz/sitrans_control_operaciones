import streamlit as st
import pandas as pd
import io
import re  # Importamos Regex para buscar patrones de texto exactos

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
    """
    Escanea las primeras filas buscando patrones inteligentes
    para Nave, Rotación y Fecha, sin importar si están en celdas combinadas.
    """
    metadatos = {"Nave": "---", "Rotación": "---", "Fecha": "---"}
    try:
        # Leemos las primeras 15 filas como texto puro
        df_head = pd.read_excel(file, header=None, nrows=15)
        
        # Estrategia 1: Búsqueda por Texto Completo (Regex)
        # Convertimos todo el bloque de celdas a un solo texto gigante para buscar patrones
        texto_completo = " ".join(df_head.astype(str).stack().tolist()).upper()
        
        # Buscar FECHA (DD/MM/AAAA o DD-MM-AAAA)
        match_fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', texto_completo)
        if match_fecha:
            metadatos["Fecha"] = match_fecha.group(1)
            
        # Estrategia 2: Búsqueda Fila por Fila (Para Nave y Rotación)
        for i, row in df_head.iterrows():
            # Convertimos la fila a lista de strings limpios
            fila = [str(x).strip().upper() for x in row if pd.notna(x) and str(x).strip() != ""]
            
            for j, val in enumerate(fila):
                # Lógica para NAVE
                if "NAVE" in val:
                    # Caso A: "NAVE: MAERSK" (Todo en la misma celda)
                    if ":" in val and len(val.split(":")) > 1:
                        posible_valor = val.split(":")[1].strip()
                        if len(posible_valor) > 2: # Evitar capturar basura
                            metadatos["Nave"] = posible_valor
                            break
                    # Caso B: Celda 1="NAVE", Celda 2="MAERSK" (Celdas separadas)
                    elif j + 1 < len(fila):
                        metadatos["Nave"] = fila[j+1]
                        break

                # Lógica para ROTACIÓN / VIAJE
                if "ROTACION" in val or "ROTACIÓN" in val or "VIAJE" in val:
                    # Caso A: "ROTACION: 12345" (Misma celda)
                    if ":" in val and len(val.split(":")) > 1:
                        metadatos["Rotación"] = val.split(":")[1].strip()
                        break
                    # Caso B: Celdas separadas
                    elif j + 1 < len(fila):
                        metadatos["Rotación"] = fila[j+1]
                        break
        
        file.seek(0)
        return metadatos
    except Exception as e:
        # Si falla algo, devolvemos vacíos pero no rompemos la app
        print(f"Debug Info - Error Metadatos: {e}")
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
        st.error(f"Error cargando datos: {e}")
        return None

# --- INTERFAZ LATERAL ---
st.sidebar.header("Carga de Documentos")
file_rep = st.sidebar.file_uploader("📂 1_Reporte (Contenedor)", type=["xls", "xlsx"])
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

# --- LÓGICA PRINCIPAL ---
if file_rep and file_mon:
    # 1. Extraer Metadatos (Versión Mejorada)
    meta = extraer_metadatos(file_rep)
    
    # Header Informativo
    c1, c2, c3 = st.columns(3)
    c1.info(f"📅 **Fecha Consulta:** {meta.get('Fecha', '---')}")
    c2.info(f"🚢 **Nave:** {meta.get('Nave', '---')}")
    c3.info(f"🔄 **Rotación:** {meta.get('Rotación', '---')}")

    with st.spinner('Procesando lógica de negocio (Normal vs CT)...'):
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

            # Métricas
            st.divider()
            k1, k2, k3 = st.columns(3)
            k1.metric("Total Contenedores", len(df_final))
            k2.metric("Reefers Normales", int(cant_normal))
            k3.metric("Reefers CT (Controlados)", int(cant_ct), delta_color="inverse")

            # Tabla
            st.subheader("Detalle Clasificado")
            st.dataframe(df_final, use_container_width=True)

            # Descarga
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button("📥 Descargar Excel Consolidado", buffer.getvalue(), "Reporte_Sitrans.xlsx")

else:
    st.info("Sube los archivos para ver la información.")
