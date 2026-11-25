"""Human-readable explanation helpers."""


def contribution_sentence(row):
    probability = row.normalized_ai_probability
    if probability is None:
        return None
    direction = "AI-generated origin" if probability > 0.5 else "authentic origin"
    return f"{row.detector_name} supports {direction} (normalized score {probability:.2f}, effective weight {row.effective_weight:.3f})."


def build_explanations(contributions, media_reasons, conflict_ids):
    ranked = sorted((row for row in contributions if row.effective_weight > 0), key=lambda row: row.effective_weight * abs((row.normalized_ai_probability or 0.5) - 0.5), reverse=True)
    supporting = [sentence for row in ranked if (sentence := contribution_sentence(row))][:6]
    conflicts = [contribution_sentence(row) for row in ranked if row.detector_id in conflict_ids]
    limitations = list(dict.fromkeys(media_reasons))
    unavailable = [row.detector_name for row in contributions if row.status in {"unavailable", "disabled", "unsupported", "failed"}]
    if unavailable:
        limitations.append(f"Unavailable, disabled, unsupported, or failed sources did not vote: {', '.join(unavailable[:8])}.")
    if any(row.status == "uncalibrated" for row in contributions):
        limitations.append("At least one learned-model score is uncalibrated and is down-weighted; it is not a probability of truth.")
    limitations.append("This is a probabilistic evidence summary, not proof of origin or authorship.")
    primary = supporting[:3] or ["No sufficiently reliable directional evidence was available."]
    return primary, supporting, [item for item in conflicts if item], limitations
