"""Online fault detection using only published metadata and metered tools.

Every new reference needs at most one paid measurement. Repeated references
reuse measurements in ctx.state; no files or stdout are used by the defense.
"""
from api import Verdict


# Calibration supplied with the lab, rather than fitted to event IDs or phases.
FEATURE_SHIFT_MAX = 0.65
EMBEDDING_SHIFT_MAX = 0.040
CORPUS_AGE_MAX_DAYS = 45.0
BATCH_DISTANCE_MAX = 1.30


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def _measure(ctx, method, *args):
    cache = ctx.state.setdefault("measurements", {})
    key = (method,) + args
    if key not in cache:
        cache[key] = getattr(ctx.tools, method)(*args)
    return cache[key]


def _measurement_error(result, pillar):
    if "error" in result:
        # A failed measurement provides no evidence that the pipeline is faulty.
        return Verdict(alert=False, confidence=0.0, pillar=pillar,
                       reason="measurement unavailable: " + str(result["error"]))
    return None


def _verdict(pillar, reasons):
    return Verdict(alert=bool(reasons), pillar=pillar, reason="; ".join(reasons))


def check_data_batch(payload, ctx):
    profile = _measure(ctx, "batch_profile", payload["batch_id"])
    error = _measurement_error(profile, "checks")
    if error is not None:
        return error

    baseline = ctx.baseline
    rows = profile["row_count"]
    amount = profile["mean_amount"]
    null_rate = profile["null_rate"]["customer_id"]
    stale = profile["staleness_min"]
    reasons = []
    if not baseline["row_count_min"] <= rows <= baseline["row_count_max"]:
        reasons.append("row count outside baseline")
    if null_rate > baseline["null_rate_max"]:
        reasons.append("customer_id null rate exceeds baseline")
    if not baseline["mean_amount_min"] <= amount <= baseline["mean_amount_max"]:
        reasons.append("mean order amount outside baseline")
    if stale > baseline["staleness_min_max"]:
        reasons.append("batch freshness exceeds baseline")

    # Scale by each published 3-sigma half-width, not by one sigma: the
    # 1.30 joint threshold is expressed in units of those baseline bounds.
    row_center = (baseline["row_count_min"] + baseline["row_count_max"]) / 2
    row_radius = (baseline["row_count_max"] - baseline["row_count_min"]) / 2
    amount_center = (baseline["mean_amount_min"] + baseline["mean_amount_max"]) / 2
    amount_radius = (baseline["mean_amount_max"] - baseline["mean_amount_min"]) / 2
    distance_sq = (
        ((rows - row_center) / row_radius) ** 2
        + ((amount - amount_center) / amount_radius) ** 2
        + (null_rate / baseline["null_rate_max"]) ** 2
        + (stale / baseline["staleness_min_max"]) ** 2
    )
    if not reasons and distance_sq > BATCH_DISTANCE_MAX ** 2:
        reasons.append("combined batch signals exceed calibrated distance")
    return _verdict("checks", reasons)


def check_contract_checkpoint(payload, ctx):
    diff = _measure(ctx, "contract_diff", payload["contract_id"],
                    payload["checkpoint_batch_id"])
    error = _measurement_error(diff, "contracts")
    if error is not None:
        return error

    reasons = [str(violation) for violation in diff["violations"]]
    freshness_limit = ctx.baseline["freshness_delay_max_min"]
    declared_limit = (payload.get("declared_sla") or {}).get("freshness_min")
    if declared_limit is not None:
        freshness_limit = min(freshness_limit, declared_limit)
    if diff["freshness_delay_min"] > freshness_limit:
        reasons.append("contract freshness exceeds SLA or baseline")
    return _verdict("contracts", reasons)


def check_lineage_run(payload, ctx):
    graph = _measure(ctx, "lineage_graph_slice", payload["run_id"])
    error = _measurement_error(graph, "lineage")
    if error is not None:
        return error

    reasons = []
    if graph["actual_downstream_count"] == 0:
        reasons.append("orphan output has no downstream consumers")
    # The lab's orders staging model requires both source tables.
    missing = {"raw.orders", "raw.customers"} - set(graph["actual_upstream"])
    if missing:
        reasons.append("missing required upstream: " + ", ".join(sorted(missing)))
    if graph["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        reasons.append("lineage runtime exceeds baseline")
    return _verdict("lineage", reasons)


def check_feature_materialization(payload, ctx):
    drift = _measure(ctx, "feature_drift", payload["feature_view"], payload["batch_id"])
    error = _measurement_error(drift, "ai_infra")
    if error is not None:
        return error

    reasons = []
    if drift["mean_shift_sigma"] > FEATURE_SHIFT_MAX:
        reasons.append("training-serving mean shift exceeds calibrated threshold")
    return _verdict("ai_infra", reasons)


def check_embedding_batch(payload, ctx):
    drift = _measure(ctx, "embedding_drift", payload["corpus"], payload["chunk_batch_id"])
    error = _measurement_error(drift, "ai_infra")
    if error is not None:
        return error

    reasons = []
    if drift["centroid_shift"] > EMBEDDING_SHIFT_MAX:
        reasons.append("embedding centroid shift exceeds calibrated threshold")
    if drift["avg_doc_age_days"] > CORPUS_AGE_MAX_DAYS:
        reasons.append("corpus documents exceed calibrated age limit")
    return _verdict("ai_infra", reasons)
