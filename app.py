%%writefile app.py
import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Sitrans Logistics Cloud", layout="wide", page_icon="🚢")

st.title("🚢 Hub de Gestión Reefers - Sitrans")
st.markdown("""
Esta aplicación procesa y cruza automáticamente los reportes de **1_Reporte (Rotación)** y **2_Monitor (Sensores)**.
""")

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
    # Leemos el archivo una vez para encontrar la fila del encabezado
    df_temp = pd.read_excel(file, header=None)
    for i, row in df_temp.iterrows():
        if palabra_clave in [str(val).strip().upper() for val in row]:
            # Volvemos al inicio del archivo para leerlo correctamente
            file.seek(0)
            df = pd.read_excel(file, header=i)
            df.columns = [str(c).strip().upper() for c in df.columns]
            df = desduplicar_columnas(df)
            return df
    return None

# --- BARRA LATERAL PARA CARGA ---
st.sidebar.header("Carga de Documentos")
file_rep = st.sidebar.file_uploader("Subir 1_Reporte (Contenedor)", type=["xls"])
file_mon = st.sidebar.file_uploader("Subir 2_Monitor (Unidad)", type=["xlsx"])

if file_rep and file_mon:
    try:
        with st.spinner('Procesando datos de Navis N4...'):
            df_rep = cargar_excel_detectando_header(file_rep, "CONTENEDOR")
            df_mon = cargar_excel_detectando_header(file_mon, "UNIDAD")

            if df_rep is not None and df_mon is not None:
                # Cruce de datos (Merge)
                df_final = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
                
                # Limpieza de columnas vacías
                df_final = df_final.loc[:, ~df_final.columns.str.contains('^UNNAMED')]

                # Lógica de Sensores (Persistencia de datos/ffill)
                cols_sens = [c for c in df_final.columns if any(x in c for x in ['SENSOR', 'OUT', 'IN', 'TEMP'])]
                if cols_sens:
                    df_final = df_final.sort_values(["CONTENEDOR"])
                    df_final[cols_sens] = df_final.groupby("CONTENEDOR")[cols_sens].ffill()

                st.success("✅ Cruce de datos exitoso")
                
                # Métricas Rápidas
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Contenedores", len(df_rep))
                c2.metric("Columnas Finales", len(df_final.columns))
                c3.metric("Datos de Sensores", df_final[cols_sens[0]].notna().sum() if cols_sens else 0)

                # Tabla Principal
                st.subheader("Planilla Consolidada")
                st.dataframe(df_final, use_container_width=True)

                # Botón de Descarga
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Descargar Excel Consolidado",
                    data=output.getvalue(),
                    file_name="consolidado_sitrans_v1.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No se encontraron los encabezados 'CONTENEDOR' o 'UNIDAD' en los archivos.")
    except Exception as e:
        st.error(f"Error técnico al procesar: {e}")
else:
    st.info("Por favor, sube ambos archivos desde la barra lateral para generar el reporte consolidado.")
