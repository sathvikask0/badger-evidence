"""Honest, table-scoped evaluation of an agent-transcribed regression set.

This measures agreement with supplied annotations, not scientific validity or
accuracy on all of a paper's records. Endpoints and inequality relations remain
distinct; concentration units are normalized using decimal arithmetic.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation


_UNIT_TO_MOLAR = {
    "nM": Decimal("1e-9"),
    "µM": Decimal("1e-6"),
    "μM": Decimal("1e-6"),
    "uM": Decimal("1e-6"),
    "mM": Decimal("1e-3"),
    "M": Decimal("1"),
}
_RELATIONS = {"=", "<", ">", "<=", ">="}
_ENDPOINTS = {"Ki", "IC50"}
BENCHMARK_LABEL = (
    "Agent-transcribed regression set; not independently scientist validated."
)


def _text(record: dict, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _scope(record: dict) -> tuple[str, str]:
    if not isinstance(record, dict):
        raise ValueError("Each record and scoped table must be an object")
    return _text(record, "pmcid"), _text(record, "table_id")


def _identity(record: dict, *, gold: bool = False) -> tuple:
    scope = _scope(record)
    compound = _text(record, "compound_label")
    endpoint = _text(record, "measurement_type")
    if endpoint not in _ENDPOINTS:
        raise ValueError("measurement_type must be Ki or IC50")
    target = record.get("target", "CA2")
    if not isinstance(target, str) or not target:
        raise ValueError("target, when provided, must be a non-empty string")
    if gold and target != "CA2":
        raise ValueError("Gold annotations must target CA2")
    return scope + (compound, endpoint, target)


def _key(record: dict, *, gold: bool = False) -> tuple:
    identity = _identity(record, gold=gold)
    relation = _text(record, "relation")
    if relation not in _RELATIONS:
        raise ValueError("relation must be =, <, >, <=, or >=")
    unit = _text(record, "unit")
    if unit not in _UNIT_TO_MOLAR:
        raise ValueError("unit must be nM, µM (or uM), mM, or M")
    if "value" not in record:
        raise ValueError("value is required, and may be null")
    value = record["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Numeric value must be a finite number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Numeric value must be a finite number") from exc
    if not number.is_finite():
        raise ValueError("Numeric value must be a finite number")
    # Shift the exponent exactly, including large values, without
    # multiplying under the default decimal precision context.
    exponent = _UNIT_TO_MOLAR[unit].as_tuple().exponent
    parts = number.as_tuple()
    normalized = Decimal((parts.sign, parts.digits, parts.exponent + exponent))
    return identity + (normalized, relation)


def evaluate(records: list[dict], gold: dict) -> dict:
    """Compare records only in explicitly annotated tables, counting duplicates.

    ``gold`` must contain non-empty ``records`` and ``scoped_tables`` lists.
    Unscoped predictions are excluded and counted separately. Malformed scoped
    records raise ``ValueError`` rather than silently disappearing. A wrong
    target, endpoint, value, or relation yields an extra and a missing record.
    Null values never count as numeric predictions or true positives. They are
    scored separately against ``expected_missing`` annotations (or null-valued
    gold records). Fabricated numbers on these cells remain false positives.
    """
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if not isinstance(gold, dict):
        raise ValueError("gold must be an object")
    annotations = gold.get("records")
    if not isinstance(annotations, list) or not annotations:
        raise ValueError("Gold records must be a non-empty list")
    tables = gold.get("scoped_tables")
    if not isinstance(tables, list) or not tables:
        raise ValueError("scoped_tables must be a non-empty list")
    ordered_scopes = list(dict.fromkeys(_scope(table) for table in tables))
    scopes = set(ordered_scopes)
    expected_by_key = defaultdict(list)
    predicted_by_key = defaultdict(list)
    expected_missing_by_key = defaultdict(list)
    abstentions_by_key = defaultdict(list)
    for annotation in annotations:
        if _scope(annotation) not in scopes:
            raise ValueError("Every gold record must belong to a scoped table")
        if "value" not in annotation:
            raise ValueError("Gold records require a value, which may be null")
        if annotation["value"] is None:
            expected_missing_by_key[_identity(annotation, gold=True)].append(annotation)
        else:
            expected_by_key[_key(annotation, gold=True)].append(annotation)
    if not expected_by_key:
        raise ValueError("Gold must contain at least one numeric measurement")
    expected_missing = gold.get("expected_missing", [])
    if not isinstance(expected_missing, list):
        raise ValueError("expected_missing must be a list")
    numeric_identities = {key[:5] for key in expected_by_key}
    for annotation in expected_missing:
        if _scope(annotation) not in scopes:
            raise ValueError("Every expected-missing record must belong to a scoped table")
        expected_missing_by_key[_identity(annotation, gold=True)].append(annotation)
    if numeric_identities.intersection(expected_missing_by_key):
        raise ValueError("A gold cell cannot be both numeric and expected missing")
    ignored = 0
    for record in records:
        if _scope(record) not in scopes:
            ignored += 1
            continue
        if "value" not in record:
            raise ValueError("value is required, and may be null")
        if record["value"] is None:
            abstentions_by_key[_identity(record)].append(record)
        else:
            predicted_by_key[_key(record)].append(record)

    missing = []
    extra = []
    true_positives = 0
    for key, expected_records in expected_by_key.items():
        predicted_records = predicted_by_key.get(key, [])
        matches = min(len(expected_records), len(predicted_records))
        true_positives += matches
        missing.extend(dict(item) for item in expected_records[matches:])
    for key, predicted_records in predicted_by_key.items():
        matches = min(len(expected_by_key.get(key, [])), len(predicted_records))
        extra.extend(dict(item) for item in predicted_records[matches:])

    missing_abstentions = []
    extra_abstentions = []
    null_matches = 0
    for key, missing_records in expected_missing_by_key.items():
        matches = min(len(missing_records), len(abstentions_by_key.get(key, [])))
        null_matches += matches
        missing_abstentions.extend(dict(item) for item in missing_records[matches:])
    for key, abstentions in abstentions_by_key.items():
        matches = min(len(abstentions), len(expected_missing_by_key.get(key, [])))
        extra_abstentions.extend(dict(item) for item in abstentions[matches:])
    fabricated_missing = [
        dict(item)
        for key, numeric_records in predicted_by_key.items()
        if key[:5] in expected_missing_by_key
        for item in numeric_records
    ]
    expected = sum(len(items) for items in expected_by_key.values())
    predicted = sum(len(items) for items in predicted_by_key.values())
    precision = true_positives / predicted if predicted else 0.0
    recall = true_positives / expected
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "benchmark_label": BENCHMARK_LABEL,
        "independently_scientist_validated": False,
        "annotation_method": gold.get("annotation_method", "Not supplied"),
        "scope_note": "Numeric metrics cover only the explicitly annotated tables; null values are scored separately as abstentions.",
        "scoped_tables": [
            {"pmcid": pmcid, "table_id": table_id}
            for pmcid, table_id in ordered_scopes
        ],
        "expected": expected,
        "predicted": predicted,
        "true_positives": true_positives,
        "false_positives": len(extra),
        "false_negatives": len(missing),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "ignored_unscoped_records": ignored,
        "null_value_matches": null_matches,
        "expected_missing_values": sum(len(items) for items in expected_missing_by_key.values()),
        "predicted_abstentions": sum(len(items) for items in abstentions_by_key.values()),
        "correct_missing_value_abstentions": null_matches,
        "unexpected_abstentions": len(extra_abstentions),
        "unreported_missing_values": len(missing_abstentions),
        "fabricated_missing_values": len(fabricated_missing),
        "fabricated_missing_records": fabricated_missing,
        "missing_abstention_records": missing_abstentions,
        "unexpected_abstention_records": extra_abstentions,
        "missing_records": missing,
        "extra_records": extra,
    }
