import hashlib
import hmac
import secrets
from typing import Annotated, cast
from uuid import UUID

from aevyra_contracts.accounts import (
    AccountView,
    Credentials,
    CreditAnalysisRequest,
    CreditEntryView,
    CreditProductView,
    RedeemRequest,
    RedemptionView,
    SessionView,
    UserView,
    WalletView,
)
from aevyra_contracts.commercial import AnalysisResultView, AnalysisView, EmptyRequest
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import (
    COOKIE,
    CSRF_COOKIE,
    AccountService,
    RateLimiter,
    csrf_token,
    pepper,
)
from aevyra_api.commercial.models import Analysis, AnalysisResult, Product
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.codes import redeem
from aevyra_api.credits.models import CreditTransaction, User, Wallet
from aevyra_api.entitlements import credit_cost

router = APIRouter(prefix="/api/v1", tags=["accounts and Credits"])


def config(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def sessions(request: Request) -> sessionmaker[Session]:
    return cast(sessionmaker[Session], request.app.state.sessions)


def account_service(request: Request) -> AccountService:
    return AccountService(sessions(request), config(request))


def current_user(request: Request) -> User:
    return account_service(request).authenticate(request.cookies.get(COOKIE))


CurrentUser = Annotated[User, Depends(current_user)]


def csrf(request: Request) -> None:
    settings = config(request)
    # Exact Origin is mandatory even for pre-login POSTs. Proxy headers are not trusted.
    if request.headers.get("origin") not in settings.cors_origins:
        raise DomainError("Request origin rejected", 403)
    token = request.cookies.get(COOKIE) or request.cookies.get(CSRF_COOKIE)
    submitted = request.headers.get("x-csrf-token", "")
    if (
        not token
        or len(token) > 100
        or not hmac.compare_digest(csrf_token(token, settings), submitted)
    ):
        raise DomainError("CSRF validation failed", 403)


def rate(request: Request, scope: str, limit: int, identity: str = "") -> None:
    # No raw address/login identifier appears in Redis keys or logs. Never trust XFF.
    client = request.client.host if request.client else "unknown"
    limiter = cast(RateLimiter, request.app.state.rate_limiter)
    key = hmac.new(pepper(config(request)).encode(), client.encode(), hashlib.sha256).hexdigest()
    # Tunnel client IP provenance is unverified. Keep a conservative shared-proxy
    # ceiling, with the existing tighter per-account limit, rather than trusting XFF.
    shared_limits = {"register": 60, "login": 120, "redeem": 120, "analysis": 180}
    shared_proxy = config(request).public_pilot or config(request).shared_proxy_rate_limits
    ip_limit = shared_limits.get(scope, limit) if shared_proxy else limit
    limiter.check(f"{scope}:ip:{key}", ip_limit, 300)
    if identity:
        key = hmac.new(
            pepper(config(request)).encode(), identity.encode(), hashlib.sha256
        ).hexdigest()
        limiter.check(f"{scope}:account:{key}", limit, 300)


def set_cookie(response: Response, name: str, value: str, settings: Settings) -> None:
    response.set_cookie(
        name,
        value,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/auth/csrf")
def get_csrf(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(COOKIE) or secrets.token_urlsafe(32)
    if COOKIE not in request.cookies:
        set_cookie(response, CSRF_COOKIE, token, config(request))
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": csrf_token(token, config(request))}


@router.post("/auth/register", response_model=SessionView, dependencies=[Depends(csrf)])
def register(body: Credentials, request: Request, response: Response) -> SessionView:
    rate(request, "register", 5, body.login_identifier)
    user, token = account_service(request).register(body.login_identifier, body.password)
    return logged_in(request, response, user, token)


@router.post("/auth/login", response_model=SessionView, dependencies=[Depends(csrf)])
def login(body: Credentials, request: Request, response: Response) -> SessionView:
    rate(request, "login", 10, body.login_identifier)
    user, token = account_service(request).login(body.login_identifier, body.password)
    old_token = request.cookies.get(COOKIE)
    if old_token:
        account_service(request).logout(old_token)
    return logged_in(request, response, user, token)


def logged_in(request: Request, response: Response, user: User, token: str) -> SessionView:
    set_cookie(response, COOKIE, token, config(request))
    response.delete_cookie(CSRF_COOKIE, path="/")
    return SessionView(
        user=UserView.model_validate(user), csrf_token=csrf_token(token, config(request))
    )


@router.get("/auth/me", response_model=SessionView)
def me(request: Request, user: CurrentUser) -> SessionView:
    return SessionView(
        user=UserView.model_validate(user),
        csrf_token=csrf_token(request.cookies[COOKIE], config(request)),
    )


@router.post("/auth/logout", dependencies=[Depends(csrf)])
def logout(
    body: EmptyRequest, request: Request, response: Response, user: CurrentUser
) -> dict[str, bool]:
    account_service(request).logout(request.cookies[COOKIE])
    response.delete_cookie(COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"logged_out": True}


@router.get("/account", response_model=AccountView)
def account(request: Request, user: CurrentUser) -> AccountView:
    with sessions(request)() as session:
        wallet = session.scalar(select(Wallet).where(Wallet.user_id == user.id))
        if wallet is None:
            raise DomainError("Wallet not found", 404)
        entries = session.scalars(
            select(CreditTransaction)
            .where(CreditTransaction.wallet_id == wallet.id)
            .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
            .limit(50)
        )
        analyses = session.scalars(
            select(Analysis)
            .where(Analysis.user_id == user.id)
            .order_by(Analysis.created_at.desc())
            .limit(50)
        )
        return AccountView(
            user=UserView.model_validate(user),
            wallet=WalletView(
                balance=wallet.cached_balance,
                transactions=[CreditEntryView.model_validate(entry) for entry in entries],
            ),
            analyses=[AnalysisView.model_validate(analysis) for analysis in analyses],
        )


@router.post("/redeem", response_model=RedemptionView, dependencies=[Depends(csrf)])
def redeem_code(body: RedeemRequest, request: Request, user: CurrentUser) -> RedemptionView:
    rate(request, "redeem", 10, user.public_user_id)
    added, balance = redeem(sessions(request), pepper(config(request)), user.id, body.code)
    return RedemptionView(credits_added=added, balance=balance)


@router.get("/credit-products", response_model=list[CreditProductView])
def credit_products(request: Request, user: CurrentUser) -> list[CreditProductView]:
    with sessions(request)() as session:
        return [
            CreditProductView(
                slug=product.slug,
                name="Auvylen Analysis",
                credit_cost=credit_cost(user, product.credit_cost),
                available=config(request).api_environment != "production",
            )
            for product in session.scalars(
                select(Product).where(
                    Product.active.is_(True), Product.product_type == "test_analysis"
                )
            )
        ]


def analysis_service(request: Request) -> CreditAnalysisService:
    return CreditAnalysisService(
        sessions(request),
        request.app.state.credit_registry,
        production=config(request).api_environment == "production",
    )


@router.post("/credit-analyses", response_model=AnalysisView, dependencies=[Depends(csrf)])
def create_credit_analysis(
    body: CreditAnalysisRequest,
    request: Request,
    user: CurrentUser,
) -> AnalysisView:
    rate(request, "analysis", 30, user.public_user_id)
    analysis_id = analysis_service(request).create(
        user.id, body.product_slug, str(body.idempotency_key)
    )
    return owned_analysis(analysis_id, request, user)


@router.get("/credit-analyses/{analysis_id}", response_model=AnalysisView)
def owned_analysis(analysis_id: UUID, request: Request, user: CurrentUser) -> AnalysisView:
    with sessions(request)() as session:
        analysis = session.scalar(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user.id)
        )
        if analysis is None:
            raise DomainError("Analysis not found", 404)
        return AnalysisView.model_validate(analysis)


@router.get("/credit-analyses/{analysis_id}/result", response_model=AnalysisResultView)
def owned_result(analysis_id: UUID, request: Request, user: CurrentUser) -> AnalysisResultView:
    owned_analysis(analysis_id, request, user)
    with sessions(request)() as session:
        result = session.scalar(
            select(AnalysisResult).where(AnalysisResult.analysis_id == analysis_id)
        )
        if result is None:
            raise DomainError("Analysis result not available", 404)
        return AnalysisResultView(
            analysis_id=analysis_id,
            raw_score=result.raw_score,
            display_score=result.display_score,
            engine_slug=result.engine_slug,
            engine_version=result.engine_version,
            calibration_version=result.calibration_version,
            metadata=result.result_metadata,
            created_at=result.created_at,
        )
