"""
Dashboard de Pronóstico del Tiempo y Alertas de Extremos
Zonas afectadas por los terremotos de Venezuela (24 de junio de 2026)
=======================================================================
Uso:
    pip install streamlit requests pandas plotly
    streamlit run dashboard_clima_venezuela.py

Fuente de datos: Open-Meteo (https://open-meteo.com) - API gratuita, sin API key.
"""

import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------

st.set_page_config(
    page_title="Clima - Zonas de Desastre Venezuela",
    page_icon="🌦️",
    layout="wide",
)

# Localidades dentro de los estados más afectados por el sismo del 24/06/2026
# (La Guaira, Caracas/Distrito Capital, Miranda, Carabobo, Yaracuy)
ZONAS = {
    "La Guaira (Litoral)":        {"lat": 10.6083, "lon": -66.9317, "estado": "La Guaira"},
    "Caraballeda":                {"lat": 10.6122, "lon": -66.8453, "estado": "La Guaira"},
    "Caracas":                    {"lat": 10.4806, "lon": -66.9036, "estado": "Distrito Capital"},
    "Los Teques":                 {"lat": 10.3399, "lon": -67.0428, "estado": "Miranda"},
    "Valencia":                   {"lat": 10.1620, "lon": -68.0077, "estado": "Carabobo"},
    "San Felipe":                 {"lat": 10.3417, "lon": -68.7419, "estado": "Yaracuy"},
}

# Umbrales para considerar "condición extrema" en contexto de emergencia/campamentos
UMBRAL_LLUVIA_FUERTE_MM = 20     # mm/día -> riesgo de deslizamientos en escombros/laderas
UMBRAL_LLUVIA_INTENSA_MM = 40    # mm/día -> riesgo alto
UMBRAL_VIENTO_FUERTE_KMH = 40    # ráfagas -> riesgo para carpas/campamentos
UMBRAL_CALOR_C = 33              # temp. máxima -> riesgo para personas a la intemperie
UMBRAL_FRIO_C = 15               # temp. mínima -> riesgo nocturno en campamentos

# ----------------------------------------------------------------------
# FUNCIONES DE DATOS
# ----------------------------------------------------------------------

@st.cache_data(ttl=1800)  # refresca cada 30 min
def obtener_pronostico(lat: float, lon: float) -> dict:
    """Consulta el pronóstico diario y por hora de Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "windspeed_10m_max",
            "windgusts_10m_max",
            "weathercode",
        ],
        "hourly": ["temperature_2m", "precipitation", "windspeed_10m"],
        "timezone": "America/Caracas",
        "forecast_days": 7,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def codigo_a_descripcion(codigo: int) -> str:
    """Traduce el weathercode de Open-Meteo (estándar WMO) a texto en español."""
    mapa = {
        0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado",
        3: "Nublado", 45: "Neblina", 48: "Neblina con escarcha",
        51: "Llovizna leve", 53: "Llovizna moderada", 55: "Llovizna intensa",
        61: "Lluvia leve", 63: "Lluvia moderada", 65: "Lluvia fuerte",
        66: "Lluvia helada leve", 67: "Lluvia helada fuerte",
        71: "Nieve leve", 73: "Nieve moderada", 75: "Nieve fuerte",
        80: "Chubascos leves", 81: "Chubascos moderados", 82: "Chubascos violentos",
        95: "Tormenta eléctrica", 96: "Tormenta con granizo leve",
        99: "Tormenta con granizo fuerte",
    }
    return mapa.get(codigo, "Desconocido")


def evaluar_alertas(dia: dict) -> list:
    """Devuelve lista de alertas (texto, nivel) para un día dado."""
    alertas = []
    lluvia = dia["precipitacion_mm"]
    viento = dia["rafagas_kmh"]
    tmax = dia["temp_max"]
    tmin = dia["temp_min"]

    if lluvia >= UMBRAL_LLUVIA_INTENSA_MM:
        alertas.append(("🔴 Lluvia intensa: alto riesgo de deslizamientos en zonas con escombros/laderas inestables", "alta"))
    elif lluvia >= UMBRAL_LLUVIA_FUERTE_MM:
        alertas.append(("🟠 Lluvia fuerte: posible riesgo de deslizamientos y anegación en campamentos", "media"))

    if viento >= UMBRAL_VIENTO_FUERTE_KMH:
        alertas.append(("🟠 Viento fuerte: riesgo para carpas y estructuras temporales", "media"))

    if tmax >= UMBRAL_CALOR_C:
        alertas.append(("🟡 Calor elevado: riesgo de golpe de calor para personas a la intemperie", "media"))

    if tmin <= UMBRAL_FRIO_C:
        alertas.append(("🔵 Temperatura baja nocturna: riesgo de hipotermia en campamentos", "media"))

    return alertas


def procesar_pronostico(data: dict) -> pd.DataFrame:
    daily = data["daily"]
    filas = []
    for i, fecha in enumerate(daily["time"]):
        filas.append({
            "fecha": fecha,
            "temp_max": daily["temperature_2m_max"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "precipitacion_mm": daily["precipitation_sum"][i],
            "prob_precipitacion": daily["precipitation_probability_max"][i],
            "viento_max_kmh": daily["windspeed_10m_max"][i],
            "rafagas_kmh": daily["windgusts_10m_max"][i],
            "condicion": codigo_a_descripcion(daily["weathercode"][i]),
        })
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# INTERFAZ
# ----------------------------------------------------------------------

import os

# ----------------------------------------------------------------------
# LOGO INSTITUCIONAL (IFRC Climate Centre)
# ----------------------------------------------------------------------
# Este script NO incluye el logo por sí mismo (es una marca registrada de
# terceros). Para mostrarlo:
#   1. Descarga el logo oficial desde https://climatecentre.org
#      (sección de prensa / brand assets, o solicítalo directamente al IFRC).
#   2. Guarda el archivo como "ifrc_climate_centre_logo.png" en la misma
#      carpeta que este script.
#   3. El dashboard lo detectará y mostrará automáticamente.
LOGO_PATH = "ifrc_climate_centre_logo.png"

col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, use_container_width=True)
    else:
        st.caption("📌 Coloca aquí 'ifrc_climate_centre_logo.png' (ver comentario en el código)")

with col_titulo:
    st.title("Pronóstico del Tiempo — Zonas de Desastre Sísmico en Venezuela")
    st.caption(
        "Seguimiento meteorológico para las zonas afectadas por los terremotos del 24 de junio de 2026 "
        "(La Guaira, Distrito Capital, Miranda, Carabobo y Yaracuy)."
    )
    
st.info(
    "⚠️ Este dashboard es una herramienta de apoyo informativo y **no sustituye** las alertas "
    "oficiales de Protección Civil / INAMEH. Verifica siempre con fuentes oficiales.",
    icon="⚠️",
)

col_izq, col_der = st.columns([1, 3])

with col_izq:
    st.subheader("Zonas")
    zonas_seleccionadas = st.multiselect(
        "Selecciona localidades",
        options=list(ZONAS.keys()),
        default=list(ZONAS.keys()),
    )
    st.markdown("---")
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()

if not zonas_seleccionadas:
    st.warning("Selecciona al menos una zona para ver el pronóstico.")
    st.stop()

# ----------------------------------------------------------------------
# RESUMEN DE ALERTAS (todas las zonas, próximos 3 días)
# ----------------------------------------------------------------------

st.subheader("🚨 Resumen de alertas — próximos 3 días")

resumen_alertas = []
datos_por_zona = {}

for nombre in zonas_seleccionadas:
    info = ZONAS[nombre]
    try:
        data = obtener_pronostico(info["lat"], info["lon"])
        df = procesar_pronostico(data)
        datos_por_zona[nombre] = df
        for _, dia in df.head(3).iterrows():
            for texto, nivel in evaluar_alertas(dia):
                resumen_alertas.append({
                    "Zona": nombre, "Estado": info["estado"],
                    "Fecha": dia["fecha"], "Alerta": texto, "Nivel": nivel,
                })
    except Exception as e:
        st.error(f"No se pudo obtener el pronóstico para {nombre}: {e}")

if resumen_alertas:
    df_alertas = pd.DataFrame(resumen_alertas)
    orden_nivel = {"alta": 0, "media": 1, "baja": 2}
    df_alertas["orden"] = df_alertas["Nivel"].map(orden_nivel)
    df_alertas = df_alertas.sort_values(["orden", "Fecha"]).drop(columns="orden")
    st.dataframe(df_alertas[["Zona", "Estado", "Fecha", "Alerta"]], use_container_width=True, hide_index=True)
else:
    st.success("No se detectan condiciones extremas en los próximos 3 días para las zonas seleccionadas.")

st.markdown("---")

# ----------------------------------------------------------------------
# DETALLE POR ZONA
# ----------------------------------------------------------------------

st.subheader("📍 Detalle por localidad")

tabs = st.tabs(zonas_seleccionadas)

for tab, nombre in zip(tabs, zonas_seleccionadas):
    with tab:
        if nombre not in datos_por_zona:
            continue
        df = datos_por_zona[nombre]
        info = ZONAS[nombre]

        c1, c2, c3, c4 = st.columns(4)
        hoy = df.iloc[0]
        c1.metric("Temp. máxima hoy", f"{hoy['temp_max']:.0f} °C")
        c2.metric("Temp. mínima hoy", f"{hoy['temp_min']:.0f} °C")
        c3.metric("Precipitación hoy", f"{hoy['precipitacion_mm']:.1f} mm")
        c4.metric("Ráfagas máx.", f"{hoy['rafagas_kmh']:.0f} km/h")

        # Gráfico de temperatura
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(x=df["fecha"], y=df["temp_max"], name="Máxima",
                                       mode="lines+markers", line=dict(color="firebrick")))
        fig_temp.add_trace(go.Scatter(x=df["fecha"], y=df["temp_min"], name="Mínima",
                                       mode="lines+markers", line=dict(color="royalblue")))
        fig_temp.update_layout(title=f"Temperatura — {nombre}", yaxis_title="°C", height=320,
                                margin=dict(t=40, b=20))

        # Gráfico de precipitación
        fig_lluvia = go.Figure()
        fig_lluvia.add_trace(go.Bar(x=df["fecha"], y=df["precipitacion_mm"], name="Precipitación (mm)",
                                     marker_color="teal"))
        fig_lluvia.add_hline(y=UMBRAL_LLUVIA_FUERTE_MM, line_dash="dot", line_color="orange",
                              annotation_text="Umbral lluvia fuerte")
        fig_lluvia.add_hline(y=UMBRAL_LLUVIA_INTENSA_MM, line_dash="dot", line_color="red",
                              annotation_text="Umbral lluvia intensa")
        fig_lluvia.update_layout(title=f"Precipitación diaria — {nombre}", yaxis_title="mm", height=320,
                                  margin=dict(t=40, b=20))

        g1, g2 = st.columns(2)
        g1.plotly_chart(fig_temp, use_container_width=True)
        g2.plotly_chart(fig_lluvia, use_container_width=True)

        st.markdown("**Tabla de pronóstico (7 días)**")
        df_mostrar = df.copy()
        df_mostrar.columns = ["Fecha", "T. Máx (°C)", "T. Mín (°C)", "Precip. (mm)",
                               "Prob. Precip. (%)", "Viento máx (km/h)", "Ráfagas (km/h)", "Condición"]
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption(
    f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    "Datos meteorológicos: Open-Meteo· "
    "Contexto terremotos de magnitud 7.5 y 7.2 del 24 de junio de 2026."
)
st.caption("Dashboard elaborado IFRC Climate Centre (climatecentre.org).")

