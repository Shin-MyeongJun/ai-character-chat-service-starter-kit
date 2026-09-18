# 허용 범위 안에서 같은 계열, 같은 provider, effort 거리, UUID 문자열 순으로 대체 모델을 고른다.
# 동일 거리의 effort는 낮은 단계를 우선한다. 비용·응답 품질 순위는 사용하지 않는다.
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def closest_effort(requested, supported):
    allowed = [e for e in supported if e in EFFORTS]
    if requested not in EFFORTS or not allowed:
        return None
    return min(
        allowed,
        key=lambda e: (
            abs(EFFORTS.index(e) - EFFORTS.index(requested)),
            EFFORTS.index(e),
        ),
    )


def choose_replacement(original, candidates, policy, effort, *, now):
    scope = policy.get("scope", "same_family")
    family = original.capabilities.get("model_family")
    choices = []
    for model in candidates:
        if (
            model.id == original.id
            or not model.is_enabled
            or (model.shutdown_at and model.shutdown_at <= now)
        ):
            continue
        same_provider = model.provider_id == original.provider_id
        same_family = (
            bool(family)
            and same_provider
            and (model.capabilities.get("model_family") == family)
        )
        allowed = (
            scope == "same_family"
            and same_family
            or (scope == "same_provider" and same_provider)
            or (scope == "allowlist" and str(model.id) in policy.get("model_ids", []))
        )
        replacement_effort = closest_effort(
            effort, model.capabilities.get("reasoning_efforts", [])
        )
        if not allowed or replacement_effort is None:
            continue
        choices.append(
            (
                not same_family,
                not same_provider,
                abs(EFFORTS.index(effort) - EFFORTS.index(replacement_effort)),
                str(model.id),
                model,
                replacement_effort,
            )
        )
    if not choices:
        return None
    best = min(choices, key=lambda x: x[:4])
    return (best[4], best[5])
