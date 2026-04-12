"""
verifications.py — Topluluk doğrulama endpoint'leri.

Anomali doğrulama oylaması, güven skoru güncelleme,
otomatik durum değişimi ve kullanıcı trust_score
yönetimi mantığını içerir.

Güven Skoru Formülü:
    confirm_ratio = weighted_confirms / (weighted_confirms + weighted_denies)
    community_score:
        10+ oy → confirm_ratio × 15  (max 15 puan)
        3-9 oy → confirm_ratio × 8
        < 3 oy → 0
    final_confidence = base_score + community_score

Otomatik Durum Değişimi:
    10+ oy AND confirm_ratio > 0.75 → VERIFIED
    5+ oy AND confirm_ratio < 0.25 → REJECTED

Trusted Verifier:
    trust_score > 4.0 → oy 2× ağırlıklı
    Doğru tahmin → trust_score + 0.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.anomaly import Anomaly
from app.models.user import User
from app.models.verification import Verification
from app.models.enums import AnomalyStatus, VerificationVote
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Sabitler
# ═══════════════════════════════════════════════════════════════════════════

TRUSTED_VERIFIER_THRESHOLD = 4.0     # trust_score eşiği — 2× ağırlık
TRUSTED_VOTE_WEIGHT = 2.0            # Güvenilir doğrulayıcı oy çarpanı
NORMAL_VOTE_WEIGHT = 1.0             # Normal oy ağırlığı

AUTO_VERIFY_MIN_VOTES = 10           # Otomatik VERIFIED için min oy
AUTO_VERIFY_CONFIRM_RATIO = 0.75     # Otomatik VERIFIED için min onay oranı

AUTO_REJECT_MIN_VOTES = 5            # Otomatik REJECTED için min oy
AUTO_REJECT_CONFIRM_RATIO = 0.25     # Otomatik REJECTED için max onay oranı

CORRECT_PREDICTION_REWARD = 0.5      # Doğru tahmin trust ödülü
WRONG_PREDICTION_PENALTY = 0.1       # Yanlış tahmin trust cezası (yumuşak)

COMMUNITY_SCORE_HIGH_VOTES = 15.0    # 10+ oy: max community puan
COMMUNITY_SCORE_MED_VOTES = 8.0      # 3-9 oy: max community puan
COMMUNITY_SCORE_HIGH_THRESHOLD = 10  # Yüksek oy eşiği
COMMUNITY_SCORE_MED_THRESHOLD = 3    # Orta oy eşiği

# ═══════════════════════════════════════════════════════════════════════════
# Pydantic v2 Schemas
# ═══════════════════════════════════════════════════════════════════════════


class VerifyRequest(BaseModel):
    """POST /anomalies/{id}/verify — Doğrulama oyu isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vote": "CONFIRM",
                "comment": "Google uydu görüntüsünde yapı net görünüyor, OSM'de yok.",
            }
        }
    )

    vote: VerificationVote = Field(
        ...,
        description="Oy tipi: CONFIRM, DENY veya UNCERTAIN",
    )
    comment: Optional[str] = Field(
        None,
        description="Opsiyonel yorum (max 2000 karakter)",
        max_length=2000,
    )


class VerifyResponse(BaseModel):
    """POST /anomalies/{id}/verify — Doğrulama oyu yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "verification_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "vote": "CONFIRM",
                "is_update": False,
                "anomaly_status": "PENDING",
                "new_confidence_score": 78.5,
                "message": "Oyunuz kaydedildi.",
            }
        }
    )

    verification_id: str = Field(..., description="Doğrulama kaydı UUID")
    vote: str = Field(..., description="Kaydedilen oy")
    is_update: bool = Field(..., description="Mevcut oy güncellendi mi")
    anomaly_status: str = Field(..., description="Anomali güncel durumu")
    new_confidence_score: float = Field(..., description="Güncellenmiş güven skoru")
    message: str = Field(..., description="Bilgi mesajı")


class VerificationItem(BaseModel):
    """Tek bir doğrulama kaydı özetli görünümü."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Doğrulama UUID")
    user_id: str = Field(..., description="Kullanıcı UUID")
    username: str = Field(..., description="Kullanıcı adı")
    vote: str = Field(..., description="Oy: CONFIRM / DENY / UNCERTAIN")
    comment: Optional[str] = Field(None, description="Yorum")
    is_trusted_verifier: bool = Field(
        False, description="Trusted verifier badge (trust_score > 4.0)"
    )
    vote_weight: float = Field(1.0, description="Oy ağırlığı")
    created_at: Optional[datetime] = Field(None, description="Oy tarihi")


class VerificationSummary(BaseModel):
    """GET /anomalies/{id}/verifications — Doğrulama özeti."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "anomaly_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "total_votes": 15,
                "confirm_count": 11,
                "deny_count": 3,
                "uncertain_count": 1,
                "weighted_confirm_count": 15.0,
                "weighted_deny_count": 3.0,
                "confirm_ratio": 0.833,
                "community_score": 12.5,
                "base_confidence": 72.0,
                "final_confidence": 84.5,
                "anomaly_status": "VERIFIED",
                "verifications": [],
            }
        }
    )

    anomaly_id: str = Field(..., description="Anomali UUID")
    total_votes: int = Field(0, description="Toplam oy sayısı")
    confirm_count: int = Field(0, description="Onay oyu sayısı (ağırlıksız)")
    deny_count: int = Field(0, description="Red oyu sayısı (ağırlıksız)")
    uncertain_count: int = Field(0, description="Belirsiz oy sayısı")
    weighted_confirm_count: float = Field(
        0.0, description="Ağırlıklı onay sayısı (trusted 2×)"
    )
    weighted_deny_count: float = Field(
        0.0, description="Ağırlıklı red sayısı (trusted 2×)"
    )
    confirm_ratio: float = Field(
        0.0, description="Onay oranı (0.0–1.0, ağırlıklı)"
    )
    community_score: float = Field(
        0.0, description="Topluluk katkısı (0–15 puan)"
    )
    base_confidence: float = Field(
        0.0, description="Anomalinin temel güven skoru"
    )
    final_confidence: float = Field(
        0.0, description="Nihai güven skoru (base + community)"
    )
    anomaly_status: str = Field(..., description="Anomali güncel durumu")
    verifications: List[VerificationItem] = Field(
        default_factory=list, description="Son doğrulama kayıtları"
    )


# ═══════════════════════════════════════════════════════════════════════════
# İç Mantık — Ağırlıklı Skor Hesaplama
# ═══════════════════════════════════════════════════════════════════════════


async def _compute_weighted_votes(
    anomaly_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    Anomali için ağırlıklı oy istatistiklerini hesaplar.

    Trusted verifier (trust_score > 4.0) oyları 2× ağırlıkla sayılır.
    UNCERTAIN oylar oran hesabına dahil edilmez.

    Args:
        anomaly_id: Anomali UUID.
        db: Async veritabanı oturumu.

    Returns:
        Ağırlıklı oy istatistikleri sözlüğü:
        - confirm_count, deny_count, uncertain_count (ağırlıksız)
        - weighted_confirms, weighted_denies (ağırlıklı)
        - total_effective (confirm + deny, ağırlıksız)
        - confirm_ratio (ağırlıklı)
    """
    # Tüm doğrulamaları kullanıcı bilgisiyle birlikte çek
    stmt = (
        select(
            Verification.vote,
            User.trust_score,
        )
        .join(User, Verification.user_id == User.id)
        .where(Verification.anomaly_id == anomaly_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    confirm_count = 0
    deny_count = 0
    uncertain_count = 0
    weighted_confirms = 0.0
    weighted_denies = 0.0

    for row in rows:
        vote = row.vote
        trust = row.trust_score or 50.0

        # Ağırlık: trusted verifier ise 2×
        weight = (
            TRUSTED_VOTE_WEIGHT
            if trust > TRUSTED_VERIFIER_THRESHOLD
            else NORMAL_VOTE_WEIGHT
        )

        if vote == VerificationVote.CONFIRM.value:
            confirm_count += 1
            weighted_confirms += weight
        elif vote == VerificationVote.DENY.value:
            deny_count += 1
            weighted_denies += weight
        elif vote == VerificationVote.UNCERTAIN.value:
            uncertain_count += 1

    total_effective = confirm_count + deny_count
    total_weighted = weighted_confirms + weighted_denies

    confirm_ratio = 0.0
    if total_weighted > 0:
        confirm_ratio = weighted_confirms / total_weighted

    return {
        "confirm_count": confirm_count,
        "deny_count": deny_count,
        "uncertain_count": uncertain_count,
        "weighted_confirms": round(weighted_confirms, 1),
        "weighted_denies": round(weighted_denies, 1),
        "total_effective": total_effective,
        "total_votes": confirm_count + deny_count + uncertain_count,
        "confirm_ratio": round(confirm_ratio, 4),
    }


def _compute_community_score(
    total_effective: int,
    confirm_ratio: float,
) -> float:
    """
    Topluluk güven skoru katkısını hesaplar.

    Formül:
        10+ oy → confirm_ratio × 15  (max 15 puan)
        3-9 oy → confirm_ratio × 8   (max 8 puan)
        < 3 oy → 0

    Args:
        total_effective: confirm + deny oy sayısı.
        confirm_ratio: Ağırlıklı onay oranı (0.0–1.0).

    Returns:
        Topluluk güven skoru katkısı (0.0–15.0).
    """
    if total_effective >= COMMUNITY_SCORE_HIGH_THRESHOLD:
        return round(confirm_ratio * COMMUNITY_SCORE_HIGH_VOTES, 2)
    elif total_effective >= COMMUNITY_SCORE_MED_THRESHOLD:
        return round(confirm_ratio * COMMUNITY_SCORE_MED_VOTES, 2)
    else:
        return 0.0


async def _update_anomaly_score_and_status(
    anomaly: Anomaly,
    vote_stats: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Anomali güven skorunu ve durumunu oy istatistiklerine göre günceller.

    Adımlar:
    1. community_score hesapla
    2. final_confidence = base + community
    3. Otomatik durum değişimi kontrol et
    4. Durum değişiminde kullanıcı trust_score güncelle

    Args:
        anomaly: SQLAlchemy Anomaly nesnesi.
        vote_stats: _compute_weighted_votes çıktısı.
        db: Async veritabanı oturumu.
    """
    total_effective = vote_stats["total_effective"]
    confirm_ratio = vote_stats["confirm_ratio"]

    # --- Community score hesapla ---
    community_score = _compute_community_score(total_effective, confirm_ratio)

    # --- Base score: community_score'u çıkar, orijinal analiz skorunu bul ---
    # meta_data.base_confidence varsa onu kullan, yoksa mevcut scoru base kabul et
    base_score = anomaly.confidence_score
    if anomaly.meta_data and isinstance(anomaly.meta_data, dict):
        base_score = anomaly.meta_data.get(
            "base_confidence", anomaly.confidence_score
        )
    else:
        # İlk kez: mevcut skoru base olarak kaydet
        if anomaly.meta_data is None:
            anomaly.meta_data = {}
        anomaly.meta_data["base_confidence"] = anomaly.confidence_score
        base_score = anomaly.confidence_score

    # --- Final confidence ---
    final_confidence = round(base_score + community_score, 2)
    anomaly.confidence_score = final_confidence

    # --- Community score'u meta_data'ya yaz ---
    anomaly.meta_data["community_score"] = community_score
    anomaly.meta_data["confirm_ratio"] = confirm_ratio
    anomaly.meta_data["total_votes"] = vote_stats["total_votes"]

    # --- Otomatik durum değişimi ---
    old_status = anomaly.status
    new_status = old_status

    if (
        total_effective >= AUTO_VERIFY_MIN_VOTES
        and confirm_ratio > AUTO_VERIFY_CONFIRM_RATIO
    ):
        new_status = AnomalyStatus.VERIFIED.value
    elif (
        total_effective >= AUTO_REJECT_MIN_VOTES
        and confirm_ratio < AUTO_REJECT_CONFIRM_RATIO
    ):
        new_status = AnomalyStatus.REJECTED.value

    # Durum değiştiyse
    if new_status != old_status:
        anomaly.status = new_status
        anomaly.verified_at = datetime.now(timezone.utc)

        logger.info(
            "Anomali durumu değişti: id=%s %s → %s "
            "(votes=%d, ratio=%.2f, score=%.1f)",
            anomaly.id,
            old_status,
            new_status,
            total_effective,
            confirm_ratio,
            final_confidence,
        )

        # --- Kullanıcı trust_score güncelleme ---
        await _update_voter_trust_scores(
            anomaly_id=str(anomaly.id),
            final_status=new_status,
            db=db,
        )


async def _update_voter_trust_scores(
    anomaly_id: str,
    final_status: str,
    db: AsyncSession,
) -> None:
    """
    Durum kesinleştikten sonra oy verenlerin trust_score'unu günceller.

    - VERIFIED olursa: CONFIRM verenler +0.5, DENY verenler -0.1
    - REJECTED olursa: DENY verenler +0.5, CONFIRM verenler -0.1
    - UNCERTAIN oylar etkilenmez

    Args:
        anomaly_id: Anomali UUID.
        final_status: Kesinleşen durum (VERIFIED / REJECTED).
        db: Async veritabanı oturumu.
    """
    if final_status not in (
        AnomalyStatus.VERIFIED.value,
        AnomalyStatus.REJECTED.value,
    ):
        return

    # Tüm oyları kullanıcılarıyla çek
    stmt = (
        select(Verification.user_id, Verification.vote)
        .where(Verification.anomaly_id == anomaly_id)
    )
    result = await db.execute(stmt)
    votes = result.all()

    # Doğru oy hangi yönde?
    correct_vote = (
        VerificationVote.CONFIRM.value
        if final_status == AnomalyStatus.VERIFIED.value
        else VerificationVote.DENY.value
    )
    wrong_vote = (
        VerificationVote.DENY.value
        if final_status == AnomalyStatus.VERIFIED.value
        else VerificationVote.CONFIRM.value
    )

    user_ids_correct: list[str] = []
    user_ids_wrong: list[str] = []

    for row in votes:
        if row.vote == correct_vote:
            user_ids_correct.append(str(row.user_id))
        elif row.vote == wrong_vote:
            user_ids_wrong.append(str(row.user_id))

    # Doğru tahmin edenler: +0.5 trust
    if user_ids_correct:
        for uid in user_ids_correct:
            user_stmt = select(User).where(User.id == uid)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if user:
                user.trust_score = round(
                    (user.trust_score or 50.0) + CORRECT_PREDICTION_REWARD, 2
                )
                user.verified_count = (user.verified_count or 0) + 1

        logger.info(
            "Trust ödülü verildi: %d kullanıcı (+%.1f) — anomaly=%s status=%s",
            len(user_ids_correct),
            CORRECT_PREDICTION_REWARD,
            anomaly_id,
            final_status,
        )

    # Yanlış tahmin edenler: -0.1 trust (yumuşak ceza)
    if user_ids_wrong:
        for uid in user_ids_wrong:
            user_stmt = select(User).where(User.id == uid)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if user:
                user.trust_score = round(
                    max(0.0, (user.trust_score or 50.0) - WRONG_PREDICTION_PENALTY),
                    2,
                )

        logger.info(
            "Trust cezası verildi: %d kullanıcı (-%.1f) — anomaly=%s status=%s",
            len(user_ids_wrong),
            WRONG_PREDICTION_PENALTY,
            anomaly_id,
            final_status,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /anomalies/{anomaly_id}/verify — Oy Ver
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/{anomaly_id}/verify",
    response_model=VerifyResponse,
    summary="Anomali doğrulama oyu ver",
    description=(
        "Belirtilen anomali için CONFIRM, DENY veya UNCERTAIN oyu verir. "
        "Her kullanıcı bir anomali için tek oy verebilir; mevcut oy değiştirilebilir. "
        "Oy sonrası güven skoru otomatik güncellenir. Eşik aşıldığında anomali "
        "durumu otomatik olarak VERIFIED veya REJECTED olarak değişir. "
        "Trusted verifier (trust_score > 4.0) oyları 2× ağırlıkla sayılır."
    ),
    response_description="Kaydedilen oy bilgisi ve güncellenmiş anomali durumu",
    tags=["verifications"],
)
async def verify_anomaly(
    anomaly_id: str,
    body: VerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """
    Anomali doğrulama oyu verir veya mevcut oyu günceller.

    İş akışı:
    1. Anomali varlığını kontrol et
    2. Mevcut oy var mı kontrol et (güncelleme veya yeni)
    3. Oyu kaydet / güncelle
    4. Ağırlıklı oy istatistiklerini hesapla
    5. Anomali güven skorunu ve durumunu güncelle
    6. Gerekirse kullanıcı trust_score'larını güncelle
    """

    # --- Anomali varlık kontrolü ---
    anomaly_stmt = select(Anomaly).where(Anomaly.id == anomaly_id)
    anomaly_result = await db.execute(anomaly_stmt)
    anomaly = anomaly_result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "anomaly_not_found",
                "message": f"Anomali bulunamadı: {anomaly_id}",
            },
        )

    # --- Mevcut oy kontrolü ---
    existing_stmt = select(Verification).where(
        and_(
            Verification.anomaly_id == anomaly_id,
            Verification.user_id == current_user.id,
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing_vote = existing_result.scalar_one_or_none()

    is_update = False

    if existing_vote is not None:
        # Mevcut oyu güncelle
        old_vote = existing_vote.vote
        existing_vote.vote = body.vote.value
        existing_vote.comment = body.comment
        existing_vote.created_at = datetime.now(timezone.utc)
        is_update = True

        logger.info(
            "Oy güncellendi: user=%s anomaly=%s %s → %s",
            current_user.id,
            anomaly_id,
            old_vote,
            body.vote.value,
        )
        verification_id = str(existing_vote.id)
    else:
        # Yeni oy oluştur
        new_vote = Verification(
            anomaly_id=anomaly_id,
            user_id=current_user.id,
            vote=body.vote.value,
            comment=body.comment,
        )
        db.add(new_vote)
        await db.flush()  # ID'yi almak için flush

        logger.info(
            "Yeni oy kaydedildi: user=%s anomaly=%s vote=%s",
            current_user.id,
            anomaly_id,
            body.vote.value,
        )
        verification_id = str(new_vote.id)

    # --- Ağırlıklı oy istatistiklerini hesapla ---
    vote_stats = await _compute_weighted_votes(anomaly_id, db)

    # --- Anomali skor ve durum güncelle ---
    await _update_anomaly_score_and_status(anomaly, vote_stats, db)

    # --- Değişiklikleri kaydet ---
    await db.commit()
    await db.refresh(anomaly)

    message = (
        "Oyunuz güncellendi." if is_update else "Oyunuz kaydedildi."
    )

    return VerifyResponse(
        verification_id=verification_id,
        vote=body.vote.value,
        is_update=is_update,
        anomaly_status=anomaly.status,
        new_confidence_score=anomaly.confidence_score,
        message=message,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies/{anomaly_id}/verifications — Oy Özeti
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/{anomaly_id}/verifications",
    response_model=VerificationSummary,
    summary="Anomali doğrulama özeti",
    description=(
        "Anomali için toplam oy istatistikleri (ağırlıklı ve ağırlıksız), "
        "güven skoru katkısı ve son doğrulama kayıtlarını döndürür. "
        "Kullanıcı bilgileri ve trusted verifier badge'i dahildir."
    ),
    response_description="Oy istatistikleri ve doğrulama kayıt listesi",
    tags=["verifications"],
)
async def get_verifications(
    anomaly_id: str,
    page: int = Query(1, description="Sayfa numarası", ge=1),
    limit: int = Query(50, description="Sayfa başına kayıt", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> VerificationSummary:
    """
    Anomali doğrulama özetini döndürür.

    İçerik:
    - Toplam oy sayıları (ağırlıklı/ağırlıksız)
    - Confirm ratio ve community score
    - Base ve final güven skoru
    - Sayfalanmış doğrulama kayıtları (kullanıcı adı, yorum, badge)
    """

    # --- Anomali varlık kontrolü ---
    anomaly_stmt = select(Anomaly).where(Anomaly.id == anomaly_id)
    anomaly_result = await db.execute(anomaly_stmt)
    anomaly = anomaly_result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "anomaly_not_found",
                "message": f"Anomali bulunamadı: {anomaly_id}",
            },
        )

    # --- Ağırlıklı oy istatistikleri ---
    vote_stats = await _compute_weighted_votes(anomaly_id, db)

    # --- Community score ---
    community_score = _compute_community_score(
        vote_stats["total_effective"],
        vote_stats["confirm_ratio"],
    )

    # --- Base confidence ---
    base_confidence = anomaly.confidence_score
    if anomaly.meta_data and isinstance(anomaly.meta_data, dict):
        base_confidence = anomaly.meta_data.get(
            "base_confidence", anomaly.confidence_score
        )

    final_confidence = round(base_confidence + community_score, 2)

    # --- Doğrulama kayıtları (sayfalanmış, en yeni önce) ---
    offset = (page - 1) * limit
    verif_stmt = (
        select(Verification, User.username, User.trust_score)
        .join(User, Verification.user_id == User.id)
        .where(Verification.anomaly_id == anomaly_id)
        .order_by(Verification.created_at.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )
    verif_result = await db.execute(verif_stmt)
    verif_rows = verif_result.all()

    verification_items: List[VerificationItem] = []
    for row in verif_rows:
        verif = row[0]       # Verification ORM nesnesi
        username = row[1]    # User.username
        trust = row[2] or 50.0  # User.trust_score

        is_trusted = trust > TRUSTED_VERIFIER_THRESHOLD
        weight = TRUSTED_VOTE_WEIGHT if is_trusted else NORMAL_VOTE_WEIGHT

        verification_items.append(
            VerificationItem(
                id=str(verif.id),
                user_id=str(verif.user_id),
                username=username,
                vote=verif.vote,
                comment=verif.comment,
                is_trusted_verifier=is_trusted,
                vote_weight=weight,
                created_at=verif.created_at,
            )
        )

    return VerificationSummary(
        anomaly_id=str(anomaly_id),
        total_votes=vote_stats["total_votes"],
        confirm_count=vote_stats["confirm_count"],
        deny_count=vote_stats["deny_count"],
        uncertain_count=vote_stats["uncertain_count"],
        weighted_confirm_count=vote_stats["weighted_confirms"],
        weighted_deny_count=vote_stats["weighted_denies"],
        confirm_ratio=vote_stats["confirm_ratio"],
        community_score=community_score,
        base_confidence=base_confidence,
        final_confidence=final_confidence,
        anomaly_status=anomaly.status,
        verifications=verification_items,
    )
