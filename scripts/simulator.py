import argparse
import time

import httpx
import pandas as pd

from app.data.loader import FEATURE_COLUMNS


def _num(v):
    """Coerce a raw xlsx cell value to float.

    banner.xlsx has ~37.7% of rows with datetime/mixed-type artifacts in
    numeric columns (same issue handled defensively in
    SimilarityEngine.query, app/similarity/engine.py) — a bare float(v)
    raises on those. Falls back to pd.to_numeric (coerce) and returns None
    when the value truly cannot be turned into a finite number.
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        coerced = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
        return None if pd.isna(coerced) else float(coerced)


def build_payload(row) -> dict:
    """Build the /eventos JSON payload from one xlsx row.

    EventIn.validate_features does float(value) on every field, so a raw
    None would reach the API as JSON null and blow up with a 500
    (TypeError: float() argument must be a string or a real number, not
    'NoneType'). Contract: when a column can't be coerced, substitute 0.0
    and print a console warning naming the affected column instead of
    sending None.
    """
    payload = {}
    for c in FEATURE_COLUMNS:
        value = _num(row[c])
        if value is None:
            print(f"aviso: coluna {c!r} nao pode ser convertida para numero "
                  f"(valor bruto={row[c]!r}); enviando 0.0 no lugar")
            value = 0.0
        payload[c] = value
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Simula gateway industrial enviando eventos")
    ap.add_argument("--url", default="http://localhost:8000/eventos")
    ap.add_argument("--arquivo", default="banner.xlsx")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--intervalo", type=float, default=3.0)
    args = ap.parse_args()

    df = pd.read_excel(args.arquivo).sample(args.n, random_state=None)
    for _, row in df.iterrows():
        payload = build_payload(row)
        resp = httpx.post(args.url, json=payload, timeout=120)
        print(f"fault real={row['fault']!r} → status={resp.json().get('status')} "
              f"family={resp.json().get('family')}")
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
