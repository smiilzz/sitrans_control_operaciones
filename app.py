import streamlit as st
import pandas as pd
import io

# Configuración de la página
st.set_page_config(page_title="Sitrans Logistics Hub", layout="wide", page_icon="🚢")

# Estilos personalizados para mejorar la apariencia
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Hub de Gestión Reefers - Sitrans")
st.info("Sube los reportes de Navis N4 en la barra lateral para consolidar la información.")

# --- FUNCIONES DE INGENIERÍA ---

def desduplicar_columnas(df):
    """Añade sufijos a columnas con nombres idénticos."""
    cols = pd.Series(df.columns)
    for i, col in enumerate(df.columns):
        if (cols == col).sum() > 1:
            count = (cols[:i] == col).sum()
            if count > 0:
                cols[i] = f"{col}.{count}"
    df.columns = cols
    return df

def cargar_excel_detectando_header(file, palabra_clave):
    """Busca automáticamente la fila donde comienzan los datos reales."""
    try:
        # Leemos el archivo completo para buscar la palabra clave
        df_temp = pd.read_excel(file, header=None)
        for i, row in df_temp.iterrows():
            # Limpiamos y buscamos la palabra clave en la fila
            row_values = [str(val).strip().upper() for val in row]
            if palabra_clave in row_values:
                file.seek(0) # Volver al inicio del archivo
                df = pd.read_excel(file, header=i)
                # Normalizar nombres de columnas (Mayúsculas y sin espacios)
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

file_rep = st.sidebar.file_uploader("📂 1_Reporte (Contenedor)", type=["xls"])
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xlsx"])

# --- LÓGICA PRINCIPAL ---

if file_rep and file_mon:
    with st.spinner('Analizando y cruzando datos de Navis...'):
        df_rep = cargar_excel_detectando_header(file_rep, "CONTENEDOR")
        df_mon = cargar_excel_detectando_header(file_mon, "UNIDAD")

        if df_rep is not None and df_mon is not None:
            # Cruce de datos (Merge)
            df_final = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            
            # Limpiar columnas 'Unnamed' (vacías en Excel)
            df_final = df_final.loc[:, ~df_final.columns.str.contains('^UNNAMED')]

            # Lógica de Persistencia de Sensores (ffill)
            # Busca columnas que contengan 'SENSOR', 'OUT', 'IN' o 'TMP'
            cols_sens = [c for c in df_final.columns if any(x in c for x in ['SENSOR', 'OUT', 'IN', 'TMP'])]
            
            if cols_sens:
                df_final = df_final.sort_values(["CONTENEDOR"])
                # Llenar huecos con el último valor conocido del mismo contenedor
                df_final[cols_sens] = df_final.groupby("CONTENEDOR")[cols_sens].ffill()

            st.success("✅ Reporte Consolidado generado con éxito")

            # Métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Contenedores Totales", len(df_rep))
            m2.metric("Columnas de Datos", len(df_final.columns))
            # Conteo de unidades que tienen al menos un dato de sensor
            con_datos = df_final[cols_sens[0]].notna().sum() if cols_sens else 0
            m3.metric("Unidades Monitoreadas", con_datos)

            # Mostrar Tabla
            st.subheader("Vista Previa del Consolidado")
            st.dataframe(df_final, use_container_width=True)

            # Botón de Descarga Profesional (Excel)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Consolidado')
            
            st.download_button(
                label="📥 Descargar Reporte Final (Excel)",
                data=buffer.getvalue(),
                file_name="Reporte_Consolidado_Sitrans.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("No se detectaron los encabezados correctos. Verifica que el archivo de Reporte tenga 'CONTENEDOR' y el de Monitor tenga 'UNIDAD'.")
else:
    st.info("👋 Bienvenido. Para comenzar, carga los dos archivos de Navis en el panel de la izquierda.")
    st.image("https://img.freepik.com/vector-gratis/ilustracion-concepto-analisis-datos_114360-1114.jpg", width=400)
