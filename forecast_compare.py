"""Perbandingan SARIMA vs XGBoost untuk forecasting harga pangan."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX

CSV = "harga_pangan_beringharjo.csv"
TEST_RATIO = 0.2
LAGS = [1, 2, 3, 7, 14, 21, 28]


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def make_features(series: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"y": series})
    df["dayofweek"] = df.index.dayofweek
    df["month"] = df.index.month
    df["day"] = df.index.day
    df["weekofyear"] = df.index.isocalendar().week.astype(int)
    for lag in LAGS:
        df[f"lag_{lag}"] = df["y"].shift(lag)
    df["rolling_mean_7"] = df["y"].shift(1).rolling(7).mean()
    df["rolling_std_7"] = df["y"].shift(1).rolling(7).std()
    df["rolling_mean_14"] = df["y"].shift(1).rolling(14).mean()
    return df.dropna()


def evaluate_commodity(series: pd.Series) -> dict[str, float | str | int]:
    split = int(len(series) * (1 - TEST_RATIO))
    train, test = series.iloc[:split], series.iloc[split:]

    sarima = SARIMAX(
        train,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, 7),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    sarima_fit = sarima.fit(disp=False)
    sarima_pred = np.asarray(sarima_fit.forecast(steps=len(test)), dtype=float)
    valid = np.isfinite(sarima_pred) & np.isfinite(test.values)
    if valid.sum() == 0:
        raise ValueError("SARIMA forecast menghasilkan semua NaN")
    sarima_mape = mape(test.values[valid], sarima_pred[valid])
    sarima_rmse = float(np.sqrt(mean_squared_error(test.values[valid], sarima_pred[valid])))

    full = make_features(series)
    feat_cols = [c for c in full.columns if c != "y"]
    split_feat = int(len(full) * (1 - TEST_RATIO))
    X_train = full.iloc[:split_feat][feat_cols]
    y_train = full.iloc[:split_feat]["y"]
    X_test = full.iloc[split_feat:][feat_cols]
    y_test = full.iloc[split_feat:]["y"]

    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="reg:squarederror",
        n_jobs=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    xgb_pred = model.predict(X_test)
    xgb_mape = mape(y_test.values, xgb_pred)
    xgb_rmse = float(np.sqrt(mean_squared_error(y_test, xgb_pred)))

    return {
        "train_n": len(train),
        "test_n": len(test),
        "sarima_mape": sarima_mape,
        "sarima_rmse": sarima_rmse,
        "xgb_mape": xgb_mape,
        "xgb_rmse": xgb_rmse,
        "winner_mape": "XGBoost" if xgb_mape < sarima_mape else "SARIMA",
    }


def main() -> None:
    raw = pd.read_csv(CSV, parse_dates=["tanggal"])
    raw = raw[raw["harga"] > 0].copy()

    rows = []
    for komoditas in sorted(raw["nama_komoditas"].unique()):
        sub = raw[raw["nama_komoditas"] == komoditas].sort_values("tanggal")
        series = sub.set_index("tanggal")["harga"].asfreq("D")
        metrics = evaluate_commodity(series)
        metrics["komoditas"] = komoditas
        rows.append(metrics)
        print(f"OK: {komoditas}")

    res = pd.DataFrame(rows)
    cols = [
        "komoditas",
        "sarima_mape",
        "xgb_mape",
        "sarima_rmse",
        "xgb_rmse",
        "winner_mape",
    ]
    print("\n" + res[cols].to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print(f"\nRata-rata MAPE SARIMA : {res['sarima_mape'].mean():.2f}%")
    print(f"Rata-rata MAPE XGBoost: {res['xgb_mape'].mean():.2f}%")


if __name__ == "__main__":
    main()
