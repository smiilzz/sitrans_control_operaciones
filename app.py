import streamlit as st
import pandas as pd
import io

# Configuración de la página
st.set_page_config(page_title="Sitrans Logistics Hub", layout="wide", page_icon="🚢")

# Estilos personalizados
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Hub de Gestión Reefers - Sitrans")
st.info("Sube los reportes de Navis N4 para clasificar Contenedores Normales vs CT.")

# --- FUNCIONES DE INGENIERÍA ---

def desduplicar_columnas(df):
    cols = pd.Series(df.columns)
    for i, col in enumerate(df.columns):
        if (cols == col).sum() > 1:
            count = (cols[:i] == col).sum()
            if count > 0:
                cols[i] = f"{col}.{count}"
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
        st.error(f"Error leyendo archivo: {e}")
        return None

# --- INTERFAZ LATERAL ---
st.sidebar.image("https://www.sitrans.cl/wp-content/themes/sitrans-child/img/logo-sitrans.png", width=150)
st.sidebar.header("Carga de Documentos")

file_rep = st.sidebar.file_uploader("📂 1_Reporte (Contenedor)", type=["xls", "xlsx"])
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

# --- LÓGICA PRINCIPAL ---

if file_rep and file_mon:
    with st.spinner('Procesando lógica de negocio (Normal vs CT)...'):
        df_rep = cargar_excel_detectando_header(file_rep, "CONTENEDOR")
        df_mon = cargar_excel_detectando_header(file_mon, "UNIDAD")

        if df_rep is not None and df_mon is not None:
            # 1. LIMPIEZA DE FILAS FANTASMA
            df_rep = df_rep[df_rep['CONTENEDOR'].notna()]
            df_rep = df_rep[df_rep['CONTENEDOR'].astype(str).str.strip() != ""]
            df_rep = df_rep[~df_rep['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]

            # 2. CRUCE DE DATOS
            df_final = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            df_final = df_final.loc[:, ~df_final.columns.str.contains('^UNNAMED')]

            # 3. LÓGICA DE CLASIFICACIÓN (NORMAL vs CT)
            # Buscamos específicamente estas 4 columnas
            cols_ct_target = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
            
            # Verificamos cuáles de esas columnas existen realmente en el archivo subido
            cols_ct_presentes = [c for c in df_final.columns if c in cols_ct_target]

            if cols_ct_presentes:
                # Un contenedor es CT si tiene valor (no vacío) en CUALQUIERA de los sensores encontrados
                # axis=1 significa que revisamos fila por fila
                es_ct = df_final[cols_ct_presentes].notna().any(axis=1)
                
                # Contamos
                cant_ct = es_ct.sum()
                cant_normal = len(df_final) - cant_ct
                
                # (Opcional) Marcamos en el Excel qué tipo es cada uno
                df_final['TIPO_REEFER'] = es_ct.apply(lambda x: 'CT' if x else 'NORMAL')
            else:
                # Si no existen las columnas de sensores, asumimos todos Normales (o faltan datos)
                cant_ct = 0
                cant_normal = len(df_final)
                df_final['TIPO_REEFER'] = 'NORMAL'

            st.success("✅ Clasificación completada")

            # 4. MÉTRICAS SOLICITADAS
            m1, m2, m3 = st.columns(3)
            m1.metric("Contenedores Totales", len(df_final))
            m2.metric("Contenedores Normales", int(cant_normal))
            m3.metric("Contenedores CT", int(cant_ct)) # Se pone en rojo si es alto, verde si bajo, etc.

            # Mostrar Tabla
            st.subheader("Detalle de Unidades")
            st.dataframe(df_final, use_container_width=True)

            # Botón de Descarga
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Consolidado_Clasificado')
            
            st.download_button(
                label="📥 Descargar Reporte Clasificado (Excel)",
                data=buffer.getvalue(),
                file_name="Reporte_Sitrans_Normal_vs_CT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Error: No se encontraron las columnas clave 'CONTENEDOR' o 'UNIDAD'.")
else:
    st.info("Esperando archivos...")
