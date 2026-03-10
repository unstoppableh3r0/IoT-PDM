"""
Train Random Forest model for PDM using AI4I 2020 dataset.

Training priority is explicit temperature + vibration features only.
Base AI4I columns are converted into our runtime sensor feature space:
    - temp (deg C)
    - vib (relative vibration index)

Saves model as pdm_model.pkl for server.py and supports retraining with
sensor_history.csv.
"""

import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

# Path to dataset (relative to project root or backend)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai4i2020.csv")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sensor_history.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pdm_model.pkl")

# Runtime model features (priority): explicit sensor-facing columns
FEATURE_COLUMNS = ["temp", "vib"]
TARGET_COLUMN = "Machine failure"

# AI4I source columns used for conversion into FEATURE_COLUMNS
BASE_TEMP_COLUMN = "Air temperature [K]"
BASE_VIB_COLUMN = "Rotational speed [rpm]"


def _air_temp_k_to_temp_c(air_temp_k: pd.Series) -> pd.Series:
    """Inverse of server mapping: 296 + (temp_c - 20) * (8 / 30)."""
    temp_c = 20.0 + (air_temp_k - 296.0) * (30.0 / 8.0)
    return temp_c.clip(lower=20.0, upper=50.0)


def _rot_speed_to_vib(rot_speed: pd.Series) -> pd.Series:
    """Inverse of server mapping: rot_speed = 1800 - vib * 15."""
    vib = (1800.0 - rot_speed) / 15.0
    return vib.clip(lower=0.0, upper=100.0)


def load_and_prepare_data(csv_path: str) -> tuple:
    """Load AI4I CSV and return X, y in [temp, vib] feature space."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Dataset not found: {csv_path}\n"
            "Download from: https://archive.ics.uci.edu/ml/datasets/ai4i+2020+predictive+maintenance+dataset"
        )
    df = pd.read_csv(csv_path)
    required_cols = [BASE_TEMP_COLUMN, BASE_VIB_COLUMN, TARGET_COLUMN]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Expected column '{col}' not found. Columns: {list(df.columns)}")

    # Convert AI4I columns into runtime feature space used by live inference.
    X = pd.DataFrame(
        {
            "temp": _air_temp_k_to_temp_c(df[BASE_TEMP_COLUMN].astype(float)),
            "vib": _rot_speed_to_vib(df[BASE_VIB_COLUMN].astype(float)),
        }
    )
    y = df[TARGET_COLUMN].astype(int)
    return X, y


def load_sensor_history(history_path: str) -> tuple:
    """Load sensor history CSV and return X, y in training-compatible format.
    
    Handles legacy format (vib,temp,air_temp_k,rot_speed,label) and new format with timestamps.
    """
    if not os.path.exists(history_path):
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)
    
    try:
        # Try reading with error handling for malformed rows (pandas 1.3+)
        # Don't specify header - let pandas detect it
        df = pd.read_csv(history_path, on_bad_lines='skip')
    except TypeError:
        # Fallback for older pandas versions without on_bad_lines parameter
        try:
            df = pd.read_csv(history_path)
        except Exception as e:
            print(f"Warning: Could not read sensor history: {e}")
            return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)
    except Exception as e:
        print(f"Warning: Could not read sensor history cleanly: {e}")
        print("Attempting to rebuild sensor history file...")
        # If CSV is corrupted, back it up and create fresh one
        import shutil
        backup_path = history_path + ".backup"
        try:
            shutil.copy(history_path, backup_path)
            print(f"Backed up corrupted file to {backup_path}")
        except:
            pass
        # Return empty dataframe
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)
    
    if len(df) == 0:
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)
    
    # Check for required columns
    if "temp" not in df.columns or "vib" not in df.columns or "label" not in df.columns:
        print(f"Warning: CSV has unexpected columns: {df.columns.tolist()}")
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)
    
    # Convert to numeric, handling any string values
    df['temp'] = pd.to_numeric(df['temp'], errors='coerce')
    df['vib'] = pd.to_numeric(df['vib'], errors='coerce')
    df['label'] = pd.to_numeric(df['label'], errors='coerce')
    
    # Drop rows with NaN values
    df = df.dropna(subset=['temp', 'vib', 'label'])
    
    X = pd.DataFrame(
        {
            "temp": df["temp"].astype(float),
            "vib": df["vib"].astype(float),
        }
    )
    y = df["label"].astype(int)
    return X, y


def train_and_save():
    """Train on AI4I base dataset only."""
    X, y = load_and_prepare_data(DATA_PATH)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    print("Accuracy:", accuracy_score(y_test, y_pred))
    print(classification_report(y_test, y_pred, target_names=["Healthy", "Faulty"]))
    os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    return model


def retrain_with_history(history_path: str = None) -> dict:
    """Retrain model using base AI4I dataset + sensor history readings.
    
    Returns dict with accuracy, base_count, history_count, total_count.
    """
    if history_path is None:
        history_path = HISTORY_PATH

    # Load base dataset
    X_base, y_base = load_and_prepare_data(DATA_PATH)
    base_count = len(X_base)
    print(f"Base dataset: {base_count} samples ({y_base.sum()} faulty)")

    # Load sensor history
    X_hist, y_hist = load_sensor_history(history_path)
    history_count = len(X_hist)
    print(f"Sensor history: {history_count} samples ({y_hist.sum() if len(y_hist) > 0 else 0} faulty)")

    # Combine datasets
    if history_count > 0:
        X_combined = pd.concat([X_base, X_hist], ignore_index=True)
        y_combined = pd.concat([y_base, y_hist], ignore_index=True)
    else:
        X_combined = X_base
        y_combined = y_base

    total_count = len(X_combined)
    print(f"Combined: {total_count} samples ({y_combined.sum()} faulty)")

    # Need at least 2 classes for stratified split
    if y_combined.nunique() < 2:
        print("Warning: Only one class in data. Training without stratification.")
        X_train, X_test, y_train, y_test = train_test_split(
            X_combined, y_combined, test_size=0.2, random_state=42
        )
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X_combined, y_combined, test_size=0.2, random_state=42, stratify=y_combined
        )

    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    print(f"Retrained accuracy: {acc:.4f}")
    print(classification_report(y_test, y_pred, target_names=["Healthy", "Faulty"], zero_division=0))

    os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Retrained model saved to {MODEL_PATH}")

    return {
        "accuracy": acc,
        "base_count": base_count,
        "history_count": history_count,
        "total_count": total_count,
    }


def get_feature_order():
    """Feature order expected by model inference: [temp, vib]."""
    return FEATURE_COLUMNS


if __name__ == "__main__":
    train_and_save()
