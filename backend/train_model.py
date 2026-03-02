"""
Train Random Forest model for PDM using AI4I 2020 dataset.
Features: Air temperature, Torque, Rotational speed -> mapped to temp, amp, vib.
Saves model as pdm_model.pkl for server.py.
"""

import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

# Path to dataset (relative to project root or backend)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai4i2020.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pdm_model.pkl")

# AI4I 2020 columns: Air temperature [K], Torque [Nm], Rotational speed [rpm]
# We map to our sensors: temp (from Air temp), vib (from Rotational speed)
FEATURE_COLUMNS = ["Air temperature [K]", "Rotational speed [rpm]"]
TARGET_COLUMN = "Machine failure"


def load_and_prepare_data(csv_path: str) -> tuple:
    """Load CSV and return X, y."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Dataset not found: {csv_path}\n"
            "Download from: https://archive.ics.uci.edu/ml/datasets/ai4i+2020+predictive+maintenance+dataset"
        )
    df = pd.read_csv(csv_path)
    for col in FEATURE_COLUMNS + [TARGET_COLUMN]:
        if col not in df.columns:
            raise ValueError(f"Expected column '{col}' not found. Columns: {list(df.columns)}")
    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].astype(int)
    return X, y


def train_and_save():
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


def get_feature_order():
    """Order of features for inference: [temp, vib] mapped to [Air temp, Rotational speed]."""
    return FEATURE_COLUMNS


if __name__ == "__main__":
    train_and_save()
