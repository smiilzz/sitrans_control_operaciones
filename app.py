import streamlit as st
import pandas as pd
import io
import re
import numpy as np

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
    </style>
    """, unsafe_allow_html=True)

st.title("🚢 Control de Operaciones - Sitrans")

# --- FUNCIONES DE SOPORTE ---
def extraer_metadatos(file):
    metadatos = {"Nave": "---", "Rotación": "---", "Fecha": "---"}
    try:
        df_head = pd.read_excel(file, header=None, nrows=20)
        texto_completo = " ".join(df_head.astype(str).stack().tolist()).upper()
        
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
                if any(x in val for x in ["ROTACION", "ROTACIÓN", "VIAJE", "VOY"]):
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
        
        # Clasificación
        cols_ct = ['SENSOR1_TMP', 'SENSOR2_TMP', 'SENSOR3_TMP', 'SENSOR4_TMP']
        presentes = [c for c in df.columns if c in cols_ct]
        if presentes:
            df['TIPO'] = df[presentes].notna().any(axis=1).apply(lambda x: 'CT' if x else 'General')
        else:
            df['TIPO'] = 'General'

        # --- CÁLCULO DE TIEMPOS ---
        parejas_calculo = {
            "Conexión": {"Fin": "CONEXIÓN", "Ini": "TIME_IN"},
            "Desconexión": {"Fin": "DESCONECCIÓN", "Ini": "SOLICITUD DESCONEXIÓN"},
            "OnBoard": {"Fin": "CONEXIÓN ONBOARD", "Ini": "TIME_LOAD"}
        }

        # --- AQUI ESTÁ EL CAMBIO DE HORA CHILE ---
        # 1. Obtenemos hora actual en Chile (Santiago)
        # 2. .tz_localize(None) elimina la info de zona horaria para poder restar con el Excel
        ahora_chile = pd.Timestamp.now(tz='America/Santiago').tz_localize(None)

        for proceso, cols in parejas_calculo.items():
            col_ini = cols["Ini"]
            col_fin = cols["Fin"]
            
            if col_ini in df.columns and col_fin in df.columns:
                df[col_ini] = pd.to_datetime(df[col_ini], dayfirst=True, errors='coerce')
                df[col_fin] = pd.to_datetime(df[col_fin], dayfirst=True, errors='coerce')
                
                # Estados
                condiciones = [
                    (df[col_ini].notna()) & (df[col_fin].notna()), 
                    (df[col_ini].notna()) & (df[col_fin].isna()),  
                    (df[col_ini].isna())                           
                ]
                opciones = ["Finalizado", "Pendiente", "Sin Solicitud"]
                col_status = f"Estado_{proceso}"
                df[col_status] = np.select(condiciones, opciones, default="Sin Solicitud")

                # Minutos Transcurridos
                col_min_real = f"Min_Transcurridos_{proceso}"
                
                # A. Finalizado: Diferencia entre Fin e Inicio
                df.loc[df[col_status] == "Finalizado", col_min_real] = (df[col_fin] - df[col_ini]).dt.total_seconds() / 60
                
                # B. Pendiente: Diferencia entre AHORA (Chile) e Inicio
                df.loc[df[col_status] == "Pendiente", col_min_real] = (ahora_chile - df[col_ini]).dt.total_seconds() / 60
                
                # C. Sin Solicitud: 0
                df.loc[df[col_status] == "Sin Solicitud", col_min_real] = 0

            else:
                st.warning(f"⚠️ Faltan columnas para {proceso}")

        # --- VISUALIZACIÓN ---
        tab1, tab2, tab3 = st.tabs(["🔌 Conexión", "🔋 Desconexión", "🚢 OnBoard"])

        def render_tab(tab, proceso):
            col_stat = f"Estado_{proceso}"
            col_min_real = f"Min_Transcurridos_{proceso}"
            
            with tab:
                if col_stat in df.columns:
                    # Métricas
                    conteo = df[col_stat].value_counts()
                    
                    k1, k2, k3, k4, k5 = st.columns(5)
                    k1.metric("Finalizados", conteo.get("Finalizado", 0))
                    k2.metric("Pendientes", conteo.get("Pendiente", 0), delta="En Vivo", delta_color="off")
                    k3.metric("Sin Solicitud", conteo.get("Sin Solicitud", 0))
                    
                    df_fin = df[df[col_stat] == "Finalizado"]
                    prom_gen = df_fin[df_fin['TIPO'] == 'General'][col_min_real].mean()
                    prom_ct = df_fin[df_fin['TIPO'] == 'CT'][col_min_real].mean()
                    
                    k4.metric("Promedio General", f"{prom_gen:.1f} min" if not pd.isna(prom_gen) else "0 min")
                    k5.metric("Promedio CT", f"{prom_ct:.1f} min" if not pd.isna(prom_ct) else "0 min")

                    st.divider()

                    # Filtro
                    filtro = st.radio(f"Ver estado en {proceso}:", 
                                      ["Todos", "Finalizado", "Pendiente", "Sin Solicitud"], 
                                      horizontal=True, key=proceso)
                    
                    if filtro == "Todos": df_show = df
                    else: df_show = df[df[col_stat] == filtro]

                    # Tabla
                    cols_base = ['CONTENEDOR', 'TIPO']
                    parejas = parejas_calculo[proceso]
                    cols_fechas = [parejas["Ini"], parejas["Fin"]]
                    cols_finales = cols_base + cols_fechas + [col_stat, col_min_real]
                    
                    df_display = df_show[cols_finales].copy()
                    df_display.rename(columns={col_min_real: "Minutos Transcurridos"}, inplace=True)
                    
                    # Formato Condicional (Rojo si > 60 min y es positivo)
                    st.dataframe(
                        df_display.style.applymap(
                            lambda x: 'color: red; font-weight: bold;' if isinstance(x, (int, float)) and x > 60 else '', 
                            subset=["Minutos Transcurridos"]
                        ).format({"Minutos Transcurridos": "{:.1f}"}), 
                        use_container_width=True
                    )

        render_tab(tab1, "Conexión")
        render_tab(tab2, "Desconexión")
        render_tab(tab3, "OnBoard")

        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Descargar Reporte Full", buffer.getvalue(), "Sitrans_Reporte.xlsx")

else:
    st.info("👋 Sube los archivos para comenzar.")
