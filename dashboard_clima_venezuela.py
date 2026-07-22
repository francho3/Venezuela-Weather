"""
Dashboard de Pronóstico del Tiempo y Alertas de Extremos
Zonas afectadas por los terremotos de Venezuela (24 de junio de 2026)
=======================================================================
Uso:
    pip install streamlit requests pandas plotly
    streamlit run dashboard_clima_venezuela.py

Fuente de datos: Visual Crossing Weather API (https://www.visualcrossing.com)
Se usa esta API (en vez de Open-Meteo) porque su límite gratuito es POR
API KEY personal (1,000 registros/día), no por dirección IP. Esto evita
el error 429 "Too Many Requests" que ocurre en Streamlit Cloud, donde
muchas apps de distintos usuarios comparten la misma IP de salida.

CÓMO OBTENER TU API KEY GRATIS (2 minutos, no pide tarjeta):
    1. Ve a https://www.visualcrossing.com/sign-up
    2. Crea una cuenta gratuita con tu correo.
    3. Copia tu API key desde el panel ("Account" -> "API Key").
    4. Configúrala de una de estas formas:
       a) Local: crea un archivo ".streamlit/secrets.toml" junto a este
          script con el contenido:
              VISUALCROSSING_API_KEY = "tu_key_aqui"
       b) Streamlit Cloud: en "Manage app" -> "Settings" -> "Secrets",
          pega la misma línea de arriba.
       c) Si no configuras nada, el dashboard te pedirá que la escribas
          en un campo de texto al abrir la app (solo para pruebas rápidas).
"""

import os
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta

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
UMBRAL_FRIO_C = 11               # temp. mínima -> riesgo nocturno en campamentos

DIAS_PRONOSTICO = 7

# Traducción aproximada de condiciones más comunes de Visual Crossing
TRADUCCIONES_CONDICION = {
    "Clear": "Despejado",
    "Partially cloudy": "Parcialmente nublado",
    "Cloudy": "Nublado",
    "Overcast": "Cielo cubierto",
    "Rain": "Lluvia",
    "Rain, Partially cloudy": "Lluvia, parcialmente nublado",
    "Rain, Overcast": "Lluvia, cielo cubierto",
    "Snow": "Nieve",
    "Thunderstorm": "Tormenta eléctrica",
    "Fog": "Neblina",
}


def traducir_condicion(texto: str) -> str:
    return TRADUCCIONES_CONDICION.get(texto, texto)


# ----------------------------------------------------------------------
# API KEY
# ----------------------------------------------------------------------

def obtener_api_key() -> str:
    """Busca la API key en secrets, variable de entorno, o la pide al usuario."""
    try:
        if "VISUALCROSSING_API_KEY" in st.secrets:
            return st.secrets["VISUALCROSSING_API_KEY"]
    except Exception:
        pass  # no hay archivo secrets.toml configurado, seguimos buscando

    env_key = os.environ.get("VISUALCROSSING_API_KEY")
    if env_key:
        return env_key

    st.warning(
        "No se encontró una API key de Visual Crossing configurada. "
        "Puedes obtener una gratis en https://www.visualcrossing.com/sign-up "
        "y pegarla abajo (o configurarla como 'secret' para no repetir este paso)."
    )
    return st.text_input("API key de Visual Crossing", type="password")


# ----------------------------------------------------------------------
# FUNCIONES DE DATOS
# ----------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Consultando pronóstico...")  # refresca cada 60 min
def obtener_pronostico(nombre_zona: str, lat: float, lon: float, api_key: str) -> dict:
    """Consulta el pronóstico diario de Visual Crossing para una localidad.

    Se pide un rango de fechas explícito (hoy -> hoy + DIAS_PRONOSTICO-1) en
    la URL, porque la API no tiene un parámetro "forecastDays": si no se
    especifican fechas, devuelve su rango por defecto (15 días).
    """
    hoy = datetime.now().date()
    fecha_fin = hoy + timedelta(days=DIAS_PRONOSTICO - 1)

    url = (
        f"https://weather.visualcrossing.com/VisualCrossingWebServices/"
        f"rest/services/timeline/{lat},{lon}/{hoy.isoformat()}/{fecha_fin.isoformat()}"
    )
    params = {
        "unitGroup": "metric",
        "include": "days",
        "elements": "datetime,tempmax,tempmin,precip,precipprob,windspeed,windgust,conditions",
        "key": api_key,
        "contentType": "json",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


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
    filas = []
    for dia in data.get("days", []):
        rafagas = dia.get("windgust")
        if rafagas is None:
            rafagas = dia.get("windspeed", 0)
        filas.append({
            "fecha": dia["datetime"],
            "temp_max": dia["tempmax"],
            "temp_min": dia["tempmin"],
            "precipitacion_mm": dia.get("precip") or 0,
            "prob_precipitacion": dia.get("precipprob") or 0,
            "viento_max_kmh": dia.get("windspeed", 0),
            "rafagas_kmh": rafagas,
            "condicion": traducir_condicion(dia.get("conditions", "")),
        })
    return pd.DataFrame(filas)


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
    st.title("🌦️ Pronóstico del Tiempo — Zonas de Desastre Sísmico en Venezuela")
    st.caption(
        "Seguimiento meteorológico para las zonas afectadas por los terremotos del 24 de junio de 2026 "
        "(La Guaira, Distrito Capital, Miranda, Carabobo y Yaracuy)."
    )
    
st.info(
    "⚠️ Este dashboard es una herramienta de apoyo informativo y **no sustituye** las alertas "
    "oficiales de Protección Civil / INAMEH. Verifica siempre con fuentes oficiales.",
    icon="⚠️",
)

with st.expander("🛰️ ¿Qué modelo meteorológico se usa?"):
    st.markdown(
        "**ensamble** que combina y pondera varios modelos numéricos reconocidos, incluyendo:\n"
        "- **ECMWF** (IFS y ENS) \n"
        "- **GFS** (NOAA, EE.UU.)\n"
        "- **ICON** (DWD, Alemania)\n"
    )

api_key = obtener_api_key()
if not api_key:
    st.stop()

col_izq, col_der = st.columns([1, 3])

with col_izq:
    st.subheader("Zonas")
    zonas_seleccionadas = st.multiselect(
        "Selecciona localidades",
        options=list(ZONAS.keys()),
        default=list(ZONAS.keys()),
    )
    st.markdown("---")
    dias_alerta = st.slider(
        "Días a incluir en el resumen de alertas",
        min_value=1, max_value=DIAS_PRONOSTICO, value=3,
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

st.subheader(f"🚨 Resumen de alertas — próximos {dias_alerta} días")

with st.expander("ℹ️ Ver umbrales usados para generar las alertas"):
    df_umbrales = pd.DataFrame([
        {"Tipo": "🔴 Lluvia intensa", "Umbral": f"≥ {UMBRAL_LLUVIA_INTENSA_MM} mm/día",
         "Riesgo": "Alto riesgo de deslizamientos en zonas con escombros/laderas inestables"},
        {"Tipo": "🟠 Lluvia fuerte", "Umbral": f"≥ {UMBRAL_LLUVIA_FUERTE_MM} mm/día",
         "Riesgo": "Posible deslizamiento y anegación en campamentos"},
        {"Tipo": "🟠 Viento fuerte", "Umbral": f"≥ {UMBRAL_VIENTO_FUERTE_KMH} km/h (ráfagas)",
         "Riesgo": "Riesgo para carpas y estructuras temporales"},
        {"Tipo": "🟡 Calor elevado", "Umbral": f"≥ {UMBRAL_CALOR_C} °C (máxima)",
         "Riesgo": "Riesgo de golpe de calor a la intemperie"},
        {"Tipo": "🔵 Frío nocturno", "Umbral": f"≤ {UMBRAL_FRIO_C} °C (mínima)",
         "Riesgo": "Riesgo de hipotermia en campamentos"},
    ])
    st.dataframe(df_umbrales, use_container_width=True, hide_index=True)
    st.caption("Puedes ajustar estos valores editando las constantes UMBRAL_... al inicio del código.")

resumen_alertas = []
datos_por_zona = {}

for nombre in zonas_seleccionadas:
    info = ZONAS[nombre]
    try:
        data = obtener_pronostico(nombre, info["lat"], info["lon"], api_key)
        df = procesar_pronostico(data)
        datos_por_zona[nombre] = df
        for _, dia in df.head(dias_alerta).iterrows():
            for texto, nivel in evaluar_alertas(dia):
                resumen_alertas.append({
                    "Zona": nombre, "Estado": info["estado"],
                    "Fecha": dia["fecha"], "Alerta": texto, "Nivel": nivel,
                })
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            st.error(f"La API key no es válida para {nombre}. Verifica que la copiaste bien.")
        else:
            st.error(f"No se pudo obtener el pronóstico para {nombre}: {e}")
    except Exception as e:
        st.error(f"No se pudo obtener el pronóstico para {nombre}: {e}")

if resumen_alertas:
    df_alertas = pd.DataFrame(resumen_alertas)
    orden_nivel = {"alta": 0, "media": 1, "baja": 2}
    df_alertas["orden"] = df_alertas["Nivel"].map(orden_nivel)
    df_alertas = df_alertas.sort_values(["orden", "Fecha"]).drop(columns="orden")
    st.dataframe(df_alertas[["Zona", "Estado", "Fecha", "Alerta"]], use_container_width=True, hide_index=True)
else:
    st.success(f"No se detectan condiciones extremas en los próximos {dias_alerta} días para las zonas seleccionadas.")

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

        st.markdown(f"**Tabla de pronóstico ({DIAS_PRONOSTICO} días)**")
        df_mostrar = df.copy()
        df_mostrar.columns = ["Fecha", "T. Máx (°C)", "T. Mín (°C)", "Precip. (mm)",
                               "Prob. Precip. (%)", "Viento máx (km/h)", "Ráfagas (km/h)", "Condición"]
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption(
    f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    "Datos meteorológicos: (Visual Crossing Weather) "
   
)
st.caption("Dashboard elaborado IFRC Climate Centre (www.climatecentre.org).")
