"""Streamlit — Prediksi Harga Pangan Pasar Beringharjo."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forecast_utils import CSV_PATH, forecast_recursive, load_clean_data, train_all_models

st.set_page_config(
    page_title="Prediksi Harga Pangan Beringharjo",
    page_icon="🛒",
    layout="wide",
)

st.title("Prediksi Harga Pangan — Pasar Beringharjo")
st.caption(
    "Deployment proyek Data Mining · Model XGBoost · "
    "Sumber: [Portal Harga Pangan Jogja](https://hargapangan.jogjakota.go.id/statistik)"
)


@st.cache_data
def get_data() -> pd.DataFrame:
    return load_clean_data(CSV_PATH)


@st.cache_resource(show_spinner="Melatih model XGBoost per komoditas...")
def get_models():
    return train_all_models(get_data())


def format_rp(value: float) -> str:
    return f"Rp {value:,.0f}"


def mape_label(value: float) -> str:
    if value < 10:
        return "Sangat baik"
    if value < 20:
        return "Baik"
    if value < 50:
        return "Cukup"
    return "Kurang baik"


df = get_data()
models = get_models()
commodity_names = sorted(models.keys())

with st.sidebar:
    st.header("Pengaturan")
    selected = st.selectbox("Komoditas", commodity_names)
    horizon = st.slider("Horizon prediksi (hari)", min_value=3, max_value=14, value=7)
    history_days = st.slider("Riwayat harga ditampilkan (hari)", min_value=30, max_value=365, value=90)
    st.divider()
    st.markdown("**Tentang model**")
    st.markdown(
        "- Algoritma: **XGBoost Regressor**\n"
        "- Fitur: lag harga, rolling mean/std, kalender\n"
        "- Evaluasi: MAPE pada 20% data test terakhir"
    )

cm = models[selected]
forecast = forecast_recursive(cm.model, cm.series, cm.feature_cols, horizon)
history = cm.series.tail(history_days)

last_price = cm.series.iloc[-1]
first_forecast = forecast.iloc[0]
last_forecast = forecast.iloc[-1]
change_pct = (last_forecast - last_price) / last_price * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Harga terakhir", format_rp(last_price))
col2.metric(f"Prediksi +{horizon} hari", format_rp(last_forecast), f"{change_pct:+.1f}%")
col3.metric("MAPE (test)", f"{cm.mape:.2f}%", mape_label(cm.mape))
col4.metric("RMSE (test)", format_rp(cm.rmse))

hist_x = pd.to_datetime(history.index).to_pydatetime()
fore_x = pd.to_datetime(forecast.index).to_pydatetime()
last_date = hist_x[-1]

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=hist_x,
        y=history.values,
        mode="lines",
        name="Historis",
        line=dict(color="#1f77b4", width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=fore_x,
        y=forecast.values,
        mode="lines+markers",
        name="Prediksi",
        line=dict(color="#2ca02c", width=2, dash="dash"),
    )
)
fig.add_shape(
    type="line",
    x0=last_date,
    x1=last_date,
    y0=0,
    y1=1,
    yref="paper",
    line=dict(color="gray", dash="dot"),
)
fig.add_annotation(
    x=last_date,
    y=1.02,
    yref="paper",
    text="Data terakhir",
    showarrow=False,
    font=dict(size=11, color="gray"),
)
fig.update_layout(
    title=f"Historis & Prediksi — {selected}",
    xaxis_title="Tanggal",
    yaxis_title="Harga (Rp)",
    hovermode="x unified",
    height=480,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns([1, 1])

with left:
    st.subheader("Tabel prediksi")
    forecast_df = forecast.reset_index()
    forecast_df.columns = ["Tanggal", "Prediksi (Rp)"]
    forecast_df["Prediksi (Rp)"] = forecast_df["Prediksi (Rp)"].map(lambda x: f"{x:,.0f}")
    st.dataframe(forecast_df, hide_index=True, use_container_width=True)

with right:
    st.subheader("Metrik evaluasi model")
    metrics_df = pd.DataFrame(
        {
            "Metrik": ["MAPE", "RMSE", "MAE", "Interpretasi MAPE"],
            "Nilai": [
                f"{cm.mape:.2f}%",
                format_rp(cm.rmse),
                format_rp(cm.mae),
                mape_label(cm.mape),
            ],
        }
    )
    st.dataframe(metrics_df, hide_index=True, use_container_width=True)

    st.subheader("Perbandingan semua komoditas")
    summary = pd.DataFrame(
        [
            {"Komoditas": m.name, "MAPE (%)": round(m.mape, 2), "RMSE (Rp)": round(m.rmse, 0)}
            for m in models.values()
        ]
    ).sort_values("MAPE (%)")
    st.dataframe(summary, hide_index=True, use_container_width=True)

st.divider()
st.markdown(
    f"**Data:** {len(df):,} baris valid · "
    f"Periode {df['tanggal'].min().date()} s.d. {df['tanggal'].max().date()} · "
    f"Pasar Beringharjo"
)
