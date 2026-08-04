import pandas as pd
from app.data.labels import normalize_label

FEATURE_COLUMNS = [
    "z_rms_velocity_in_s", "z_rms_velocity_mm_s", "temperature_f", "temperature_c",
    "x_rms_velocity_in_s", "x_rms_velocity_mm_s", "z_peak_acceleration_g",
    "x_peak_acceleration_g", "z_peak_vel_comp_freq_hz", "x_peak_vel_comp_freq_hz",
    "z_rms_acceleration_g", "x_rms_acceleration_g", "z_kurtosis", "x_kurtosis",
    "z_crest_factor", "x_crest_factor", "z_peak_velocity_in_s", "z_peak_velocity_mm_s",
    "x_peak_velocity_in_s", "x_peak_velocity_mm_s", "z_high_freq_rms_accel_g",
    "x_high_freq_rms_accel_g", "rpm",
]
REQUIRED = ["id", "created_at", "fault", *FEATURE_COLUMNS]


def load_dataset(path: str) -> pd.DataFrame:
    df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"colunas ausentes no dataset: {missing}")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    infos = df["fault"].astype(str).map(normalize_label)
    df["family"] = [i.family for i in infos]
    df["kind"] = [i.kind for i in infos]
    return df
