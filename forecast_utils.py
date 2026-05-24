"""Utilitas forecasting harga pangan — dipakai notebook, script, dan Streamlit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

CSV_PATH = "harga_pangan_beringharjo.csv"
TEST_RATIO = 0.2
LAGS = [1, 2, 3, 7, 14, 21, 28]

XGB_PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    objective="reg:squarederror",
    n_jobs=-1,
)


@dataclass
class CommodityModel:
    name: str
    model: xgb.XGBRegressor
    feature_cols: list[str]
    series: pd.Series
    mape: float
    rmse: float
    mae: float


def load_clean_data(csv_path: str = CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["tanggal"])
    df = df[df["harga"] > 0].copy()
    return df.sort_values(["nama_komoditas", "tanggal"]).reset_index(drop=True)


def make_features(series: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame({"y": series})
    out["dayofweek"] = out.index.dayofweek
    out["month"] = out.index.month
    out["day"] = out.index.day
    out["weekofyear"] = out.index.isocalendar().week.astype(int)
    for lag in LAGS:
        out[f"lag_{lag}"] = out["y"].shift(lag)
    out["rolling_mean_7"] = out["y"].shift(1).rolling(7).mean()
    out["rolling_std_7"] = out["y"].shift(1).rolling(7).std()
    out["rolling_mean_14"] = out["y"].shift(1).rolling(14).mean()
    return out.dropna()


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.asarray(y_true) != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def series_from_df(df: pd.DataFrame, komoditas: str) -> pd.Series:
    sub = df[df["nama_komoditas"] == komoditas].sort_values("tanggal")
    return sub.set_index("tanggal")["harga"].asfreq("D")


def train_xgboost(series: pd.Series) -> tuple[xgb.XGBRegressor, list[str], float, float, float]:
    full = make_features(series)
    feat_cols = [c for c in full.columns if c != "y"]
    split = int(len(full) * (1 - TEST_RATIO))

    X_train = full.iloc[:split][feat_cols]
    y_train = full.iloc[:split]["y"]
    X_test = full.iloc[split:][feat_cols]
    y_test = full.iloc[split:]["y"]

    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    pred = model.predict(X_test)
    return (
        model,
        feat_cols,
        mape(y_test.values, pred),
        float(np.sqrt(mean_squared_error(y_test, pred))),
        float(mean_absolute_error(y_test, pred)),
    )


def train_all_models(df: pd.DataFrame | None = None) -> dict[str, CommodityModel]:
    if df is None:
        df = load_clean_data()

    models: dict[str, CommodityModel] = {}
    for name in sorted(df["nama_komoditas"].unique()):
        series = series_from_df(df, name)
        model, feat_cols, mape_val, rmse_val, mae_val = train_xgboost(series)
        models[name] = CommodityModel(
            name=name,
            model=model,
            feature_cols=feat_cols,
            series=series,
            mape=mape_val,
            rmse=rmse_val,
            mae=mae_val,
        )
    return models


def forecast_recursive(
    model: xgb.XGBRegressor,
    series: pd.Series,
    feat_cols: list[str],
    horizon: int,
) -> pd.Series:
    """Prediksi multi-hari ke depan dengan update lag secara rekursif."""
    values = series.tolist()
    dates = list(series.index)
    future_preds: list[float] = []
    future_dates: list[pd.Timestamp] = []

    for _ in range(horizon):
        temp = pd.Series(values, index=dates)
        row = make_features(temp).iloc[[-1]][feat_cols]
        pred = float(model.predict(row)[0])
        pred = max(pred, 0)

        next_date = dates[-1] + pd.Timedelta(days=1)
        values.append(pred)
        dates.append(next_date)
        future_preds.append(pred)
        future_dates.append(next_date)

    return pd.Series(future_preds, index=future_dates, name="prediksi")
