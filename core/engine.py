import json
import re
import os
import sys

# Official weights from Tabela v1.1
WEIGHTS = {
    "A1": 1.0,
    "A2": 2.0,
    "A3": 1.5,
    "A4": 2.5,
    "A5": 3.0,
    "A6": 1.0,
    "A7": 4.0,
    "A8": 2.0,
    "A9": 3.5,
    "A10": 12.0,
    "A11": 1.0,
    "A12": 5.0,
}

def parse_kihon_line(line):
    """
    Parse a single line in the format 'Kihon: <code>:<value>'
    where value may use comma as decimal separator (e.g., 1,7 -> 1.7).
    Returns a tuple (code, value) or None if line does not match.
    """
    pattern = r'Kihon:\s*(A\d{1,2}):\s*([\d,]+)'
    match = re.search(pattern, line, re.IGNORECASE)
    if not match:
        return None
    code = match.group(1).upper()
    raw_value = match.group(2).replace(',', '.')
    try:
        value = float(raw_value)
    except ValueError:
        print(f"WARNING: Could not convert '{raw_value}' to float in line: {line.strip()}")
        return None
    return code, value

def parse_kihon_input(text):
    """
    Parse multiple lines of text (e.g., from a file or string)
    and return a dict mapping code -> value.
    """
    scores = {}
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = parse_kihon_line(line)
        if parsed:
            code, value = parsed
            scores[code] = value
            print(f"  Parsed: {code} = {value}")
        else:
            print(f"  SKIP (no match): {line}")
    return scores

def calcular_resultados(scores):
    """
    Compute weighted total from the scores dictionary.
    - Uses .get(k, 0) for missing keys.
    - Caps the weighted A10 contribution at 10.0.
    Returns: (total, weighted_details)
    """
    total = 0.0
    weighted = {}
    print("Calculating contributions:")
    for code, weight in WEIGHTS.items():
        raw = scores.get(code, 0.0)
        contribution = raw * weight
        if code == "A10":
            # Apply cap of 10.0 to the weighted contribution
            capped = min(contribution, 10.0)
            print(f"  {code}: raw={raw}, weight={weight}, weighted={contribution:.4f}, capped={capped:.4f}")
            contribution = capped
        else:
            print(f"  {code}: raw={raw}, weight={weight}, weighted={contribution:.4f}")
        weighted[code] = contribution
        total += contribution
    print(f"  Total weighted score: {total:.4f}")
    return total, weighted

def save_diagnostico(total, weighted):
    """Save results to output/diagnostico.json."""
    os.makedirs("output", exist_ok=True)
    data = {
        "total_score": round(total, 4),
        "weighted_details": {k: round(v, 4) for k, v in weighted.items()}
    }
    with open("output/diagnostico.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Saved results to output/diagnostico.json")

def main():
    # Simulated input (replace with reading from file or stdin as needed)
    sample_input = """Kihon: A1:1,7
Kihon: A2:2,5
Kihon: A3:3,0
Kihon: A4:4,2
Kihon: A5:5,1
Kihon: A6:6,0
Kihon: A7:7,8
Kihon: A8:8,3
Kihon: A9:9,6
Kihon: A10:10,0
Kihon: A11:11,2
Kihon: A12:12,4
"""
    print("=== Starting Kihon Parser ===")
    print("Input text:")
    print(sample_input)
    print("\nParsing lines...")
    scores = parse_kihon_input(sample_input)
    print(f"\nParsed scores: {scores}")
    print("\nCalculating results...")
    total, weighted = calcular_resultados(scores)
    print(f"\nFinal total: {total:.4f}")
    save_diagnostico(total, weighted)
    print("=== Done ===")

if __name__ == "__main__":
    main()