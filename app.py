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
st.info("Sube los reportes de Navis N4 en la barra lateral para consolidar la información.")

# --- FUNCIONES DE INGENIERÍA ---

def desduplicar_columnas(df):
    """Evita el error de columnas duplicadas añadiendo sufijos."""
    cols = pd.Series(df.columns)
    for i, col in enumerate(df.columns):
        if (cols == col).sum() > 1:
            count = (cols[:i] == col).sum()
            if count > 0:
                cols[i] = f"{col}.{count}"
    df.columns = cols
    return df

def cargar_excel_detectando_header(file, palabra_clave):
    """Busca la fila donde empiezan los datos reales."""
    try:
        # Leemos el archivo completo sin encabezado
        df_temp = pd.read_excel(file, header=None)
        
        for i, row in df_temp.iterrows():
            # Buscamos la palabra clave (ej: CONTENEDOR) en la fila
            row_values = [str(val).strip().upper() for val in row]
            
            if palabra_clave in row_values:
                file.seek(0) # Volver al inicio
                # Cargamos de nuevo usando esa fila como encabezado
                df = pd.read_excel(file, header=i)
                # Normalizamos nombres de columnas
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
file_mon = st.sidebar.file_uploader("📂 2_Monitor (Unidad)", type=["xls", "xlsx"])

# --- LÓGICA PRINCIPAL ---

if file_rep and file_mon:
    with st.spinner('Analizando y cruzando datos de Navis...'):
        df_rep = cargar_excel_detectando_header(file_rep, "CONTENEDOR")
        df_mon = cargar_excel_detectando_header(file_mon, "UNIDAD")

        if df_rep is not None and df_mon is not None:
            
            # --- LIMPIEZA DE FILAS FANTASMA (Corrección 429 vs 327) ---
            # 1. Eliminar filas donde CONTENEDOR es nulo
            df_rep = df_rep[df_rep['CONTENEDOR'].notna()]
            # 2. Eliminar filas donde CONTENEDOR es texto vacío o espacios
            df_rep = df_rep[df_rep['CONTENEDOR'].astype(str).str.strip() != ""]
            # 3. Eliminar filas de "Total" si existen
            df_rep = df_rep[~df_rep['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]
            # ----------------------------------------------------------

            # Cruce de datos (Left Join)
            df_final = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
            
            # Eliminar columnas basura ("Unnamed")
            df_final = df_final.loc[:, ~df_final.columns.str.contains('^UNNAMED')]

            # Lógica de Sensores (Rellenar hacia abajo - ffill)
            cols_sens = [c for c in df_final.columns if any(x in c for x in ['SENSOR', 'OUT', 'IN', 'TMP'])]
            
            if cols_sens:
                df_final = df_final.sort_values(["CONTENEDOR"])
                df_final[cols_sens] = df_final.groupby("CONTENEDOR")[cols_sens].ffill()

            st.success("✅ Reporte Consolidado generado con éxito")

            # Métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Contenedores Totales", len(df_rep)) # Ahora debe marcar el número real
            m2.metric("Columnas de Datos", len(df_final.columns))
            
            con_datos = df_final[cols_sens[0]].notna().sum() if cols_sens else 0
            m3.metric("Unidades Monitoreadas", con_datos)

            # Mostrar Tabla
            st.subheader("Vista Previa del Consolidado")
            st.dataframe(df_final, use_container_width=True)

            # Botón de Descarga
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
            st.error("No se detectaron las columnas 'CONTENEDOR' o 'UNIDAD'. Revisa los archivos.")
else:
    st.info("👋 Sube ambos archivos en la barra lateral para comenzar.")
