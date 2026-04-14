"""MBSE 분류 키워드 패턴 및 스코어링.

도메인 독립적으로 설계됨. 도메인별 확장은 DOMAIN_KEYWORDS에 추가.
"""
from __future__ import annotations

import re

# ── MBSE 타입별 키워드 패턴 ───────────────────────────────────────────────────
# key: MBSE 타입
# value: {"title": [...], "body": [...], "labels": [...]}
#   - title 패턴은 제목에 적용 (가중치 3)
#   - labels 패턴은 레이블에 적용 (가중치 2)
#   - body 패턴은 본문에 적용 (가중치 1)

MBSE_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "Requirement": {
        "title": [
            r"\bshall\b", r"\bmust\b", r"\brequirement[s]?\b", r"\brequire[sd]?\b",
            r"\bspec\b", r"\bspecification\b", r"\bcompliance\b", r"\bconstraint\b",
            r"\bbudget\b", r"\bthreshold\b", r"\blimit\b",
            # 한국어
            r"요구사항", r"요건", r"규격", r"성능\s*요구", r"기능\s*요구", r"비기능\s*요구",
        ],
        "body": [
            r"\bshall\b", r"\bmust\b", r"acceptance criteria",
            r"stakeholder", r"user need", r"system.*shall",
            r"성능 요구", r"기능 요구", r"비기능 요구", r"합격 기준",
        ],
        "labels": [
            r"requirement", r"req", r"shall", r"user.?need", r"stakeholder",
            r"요구사항",
        ],
    },
    "Architecture_Block": {
        "title": [
            r"\barchitecture\b", r"\bmodule\b", r"\bcomponent\b",
            r"\binterface\b", r"\bsubsystem\b", r"\bblock\b",
            r"\bpartition", r"\ballocat", r"\bdesign\s+decision\b",
            r"\bhw.?sw\b", r"\bframework\b",
            # 한국어
            r"아키텍처", r"모듈", r"인터페이스", r"서브시스템", r"블록", r"할당",
        ],
        "body": [
            r"\binterface\b", r"\bprotocol\b", r"block diagram",
            r"\bICD\b", r"\bICF\b", r"\ballocat", r"hw.?sw",
            r"partitioning", r"subsystem", r"design decision",
        ],
        "labels": [
            r"architecture", r"arch", r"component", r"interface",
            r"module", r"subsystem", r"아키텍처",
        ],
    },
    "Design_Spec": {
        "title": [
            r"^implement", r"^develop", r"^add\b", r"^create\b", r"^refactor",
            r"\bdriver\b", r"\balgorithm\b", r"\bAPI\b", r"\bflow\b",
            r"\bregister\b", r"\bbuffer\b", r"\bqueue\b", r"\bscheduler\b",
            # 한국어
            r"구현", r"개발", r"설계\s*명세", r"상세\s*설계",
        ],
        "body": [
            r"implementation", r"algorithm", r"pseudo.?code",
            r"register map", r"sequence diagram", r"class diagram",
            r"\bdriver\b", r"buffer", r"queue", r"API",
        ],
        "labels": [
            r"implementation", r"design.?spec", r"spec", r"detail",
            r"구현", r"설계명세",
        ],
    },
    "Verification": {
        "title": [
            r"\btest\b", r"\btesting\b", r"\bverif", r"\bvalidat",
            r"\bbenchmark\b", r"\bmeasure", r"\bV&V\b",
            # 한국어
            r"시험", r"검증", r"테스트", r"측정", r"인증",
        ],
        "body": [
            r"test step", r"expected result", r"pass.?fail",
            r"test script", r"certification", r"\bmeasure\b",
            r"시험 절차", r"합격 기준", r"시험 결과",
        ],
        "labels": [
            r"test", r"verification", r"validation", r"qa", r"v&v",
            r"시험", r"검증",
        ],
    },
    "Issue": {
        "title": [
            r"\bbug\b", r"\bdefect\b", r"\brisk\b", r"\bfail",
            r"\berror\b", r"\bblock", r"\bspike\b", r"\bcrash\b",
            # 한국어
            r"버그", r"결함", r"위험", r"오류", r"장애",
        ],
        "body": [
            r"root cause", r"workaround", r"\bimpact\b",
            r"regression", r"crash", r"failure", r"risk factor",
        ],
        "labels": [
            r"bug", r"defect", r"risk", r"impediment",
            r"버그", r"결함",
        ],
    },
}

# 필드별 가중치
_WEIGHTS: dict[str, int] = {"title": 3, "labels": 2, "body": 1}

VALID_TYPES: frozenset[str] = frozenset(MBSE_KEYWORDS.keys())


def score_document(
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, float]:
    """각 MBSE 타입별 키워드 매칭 점수 반환."""
    scores: dict[str, float] = {t: 0.0 for t in MBSE_KEYWORDS}

    texts = {
        "title": title.lower(),
        "body": body.lower()[:1500],
        "labels": " ".join(labels).lower(),
    }

    for mbse_type, patterns in MBSE_KEYWORDS.items():
        for field, pat_list in patterns.items():
            text = texts.get(field, "")
            weight = _WEIGHTS[field]
            for pat in pat_list:
                if re.search(pat, text, re.IGNORECASE):
                    scores[mbse_type] += weight

    return scores


def keyword_classify(
    title: str,
    body: str,
    labels: list[str],
    confidence_threshold: float = 0.65,
) -> tuple[str | None, float]:
    """키워드 스코어링으로 MBSE 타입 결정.

    Returns:
        (mbse_type, confidence) — 신뢰도 미달 시 (None, raw_confidence).
    """
    scores = score_document(title, body, labels)
    total = sum(scores.values())

    if total == 0:
        return None, 0.0

    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winner, winner_score = sorted_types[0]
    second_score = sorted_types[1][1] if len(sorted_types) > 1 else 0.0

    if winner_score == 0:
        return None, 0.0

    # 1위 점수 비율로 신뢰도 계산 (2위와의 격차가 클수록 높음)
    confidence = round(winner_score / (winner_score + second_score + 1e-6), 3)

    if confidence >= confidence_threshold:
        return winner, confidence
    return None, confidence
