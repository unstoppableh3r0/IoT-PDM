# Data folder for PDM

Place **ai4i2020.csv** here for training the Random Forest model.

- **Download:** [UCI ML Repository - AI4I 2020 Predictive Maintenance](https://archive.ics.uci.edu/ml/datasets/ai4i+2020+predictive+maintenance+dataset)
- **Columns used:** `Air temperature [K]`, `Torque [Nm]`, `Rotational speed [rpm]`, `Machine failure` (target)

Then run from the project root:
```bash
cd backend && python train_model.py
```
