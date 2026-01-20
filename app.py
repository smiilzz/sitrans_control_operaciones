import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Sitrans Dashboard", layout="wide", page_icon="🚢")

# Estilos CSS para parecerse al Dashboard de la imagen (Azul Sitrans y KPI Cards)
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        text-align: center;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 14px;
        color: #555;
    }
    div[data-testid="stMetricValue"] {
        font-size: 24px;
        font-weight: bold;
        color: #003366; /* Azul Sitrans */
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Control de Operaciones - Sitrans")

# --- FUNCIONES DE SOPORTE ---

def extraer_metadatos(file):
    metadatos = {"Nave": "---", "Rotación": "---", "Fecha": "---"}
    try:
        df_head = pd.read_excel(file, header=None, nrows=15)
        texto_completo = " ".join(df_head.astype(str).stack().tolist()).upper()
        
        # Regex Fecha+Hora
        match_fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}\s+\d{1,2}:\d{2})', texto_completo)
        if match_fecha: metadatos["Fecha"] = match_fecha.group(1)
        else:
            match_solo_fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', texto_completo)
            if match_solo_fecha: metadatos["Fecha"] = match_solo_fecha.group(1)

        for i, row in df_head.iterrows():
            fila = [str(x).strip().upper() for x in row if pd.notna(x) and str(x).strip() != ""]
            for j, val in enumerate(fila):
                if "NAVE" in val:
                    if ":" in val and len(val.split(":")) > 1: metadatos["Nave"] = val.split(":")[1].strip()
                    elif j+1 < len(fila): metadatos["Nave"] = fila[j+1]
                if "ROTACION" in val or "VIAJE" in val:
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
            row_values = [str(val).strip().upper() for val in row]
            if palabra_clave in row_values:
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
    
    # 1. BARRA SUPERIOR DE METADATOS
    with st.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Fecha Consulta", meta.get('Fecha', '---'))
        c2.metric("Nave", meta.get('Nave', '---'))
        c3.metric("Rotación", meta.get('Rotación', '---'))
    
    st.divider()

    # 2. PROCESAMIENTO
    df_rep = cargar_excel(file_rep, "CONTENEDOR")
    df_mon = cargar_excel(file_mon, "UNIDAD")

    if df_rep is not None and df_mon is not None:
        # Limpieza Básica
        df_rep = df_rep[df_rep['CONTENEDOR'].notna()]
        df_rep = df_rep[df_rep['CONTENEDOR'].astype(str).str.strip() != ""]
        df_rep = df_rep[~df_rep['CONTENEDOR'].astype(str).str.contains("Total", case=False, na=False)]

        # Cruce
        df = pd.merge(df_rep, df_mon, left_on="CONTENEDOR", right_on="UNIDAD", how="left")
        
        # Clasificación Normal vs CT
        cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
        presentes = [c for c in df.columns if c in cols_ct]
        if presentes:
            df['TIPO'] = df[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
        else:
            df['TIPO'] = 'General'

        # --- CÁLCULO DE TIEMPOS (MINUTOS) ---
        # Definimos las parejas de columnas para restar
        parejas_calculo = {
            "Conexión": ("CONEXIÓN", "TIME_IN"),
            "Desconexión": ("DESCONECCIÓN", "SOLICITUD DESCONEXIÓN"), # Ojo con la doble C de Navis
            "OnBoard": ("CONEXIÓN ONBOARD", "TIME_LOAD")
        }

        # Convertimos a Datetime y Calculamos Restas
        for proceso, (col_fin, col_ini) in parejas_calculo.items():
            if col_fin in df.columns and col_ini in df.columns:
                # Convertir a fecha inteligente
                df[col_ini] = pd.to_datetime(df[col_ini], dayfirst=True, errors='coerce')
                df[col_fin] = pd.to_datetime(df[col_fin], dayfirst=True, errors='coerce')
                
                # Calcular diferencia en minutos
                col_min = f"Min_{proceso}"
                df[col_min] = (df[col_fin] - df[col_ini]).dt.total_seconds() / 60
            else:
                st.warning(f"⚠️ Faltan columnas para calcular {proceso}: Buscaba '{col_ini}' y '{col_fin}'")

        # --- DASHBOARD POR PESTAÑAS ---
        tab1, tab2, tab3 = st.tabs(["🔌 Conexión a Stacking", "🔋 Desconexión", "🚢 OnBoard"])

        def mostrar_kpis(tab, proceso, col_minutos):
            with tab:
                if col_minutos in df.columns:
                    # Filtramos solo los que tienen dato válido (no nulos)
                    df_valido = df.dropna(subset=[col_minutos])
                    
                    # Promedios
                    prom_general = df_valido[df_valido['TIPO'] == 'General'][col_minutos].mean()
                    prom_ct = df_valido[df_valido['TIPO'] == 'CT'][col_minutos].mean()
                    
                    # Limpieza de NaN para mostrar 0 si no hay datos
                    prom_general = 0 if pd.isna(prom_general) else prom_general
                    prom_ct = 0 if pd.isna(prom_ct) else prom_ct

                    # Layout de KPIs
                    st.subheader(f"⏱️ Tiempos de {proceso}")
                    k1, k2, k3 = st.columns(3)
                    
                    k1.metric(f"Promedio General", f"{prom_general:.1f} min")
                    k2.metric(f"Promedio CT (Reefer)", f"{prom_ct:.1f} min", delta_color="inverse")
                    
                    # Conteo de casos
                    total_ops = len(df_valido)
                    k3.metric("Contenedores Procesados", total_ops)

                    # Alerta Visual (Ejemplo de la imagen: Rojo si > 30 min)
                    umbral = 30
                    rojos = len(df_valido[df_valido[col_minutos] > umbral])
                    if rojos > 0:
                        st.error(f"🚨 ATENCIÓN: {rojos} Contenedores exceden los {umbral} minutos en {proceso}")
                    else:
                        st.success(f"✅ Operación fluida: Ningún contenedor excede los {umbral} minutos")

                else:
                    st.info(f"No hay datos suficientes para calcular {proceso}.")

        # Renderizar cada pestaña
        mostrar_kpis(tab1, "Conexión", "Min_Conexión")
        mostrar_kpis(tab2, "Desconexión", "Min_Desconexión")
        mostrar_kpis(tab3, "OnBoard", "Min_OnBoard")

        # Botón de Descarga (Oculto al final)
        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Descargar Excel con Cálculos", buffer.getvalue(), "Reporte_Calculado.xlsx")

else:
    st.info("👋 Sube los archivos '1_Reporte' y '2_Monitor' para ver el Dashboard.")
