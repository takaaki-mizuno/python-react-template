from datetime import timedelta
from uuid import UUID

from injector import inject

from app.config.auth import AuthSettings
from app.config.oidc import OidcSettings
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.libraries.clock import utcnow
from app.libraries.password_hasher import PasswordHashExecutor
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import (AccountDeletionConfirmationMismatchError,
                                    AccountDeletionInvalidPasswordError,
                                    AccountDeletionOidcReauthRequiredError,
                                    AccountDeletionReauthRequiredError, RateLimitExceededError)
from app.models.auth_event_type import AuthEventType


class AccountDeletionUsecase(AccountDeletionUsecaseInterface):

    @inject
    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        sample_item_repository: SampleItemRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
        auth_rate_limiter: LoginRateLimiterInterface,
        auth_settings: AuthSettings,
        oidc_settings: OidcSettings,
        password_hash_executor: PasswordHashExecutor,
    ) -> None:
        self._auth_repository = auth_repository
        self._sample_item_repository = sample_item_repository
        self._unit_of_work = unit_of_work
        self._auth_rate_limiter = auth_rate_limiter
        self._auth_settings = auth_settings
        self._oidc_settings = oidc_settings
        self._password_hash_executor = password_hash_executor

    async def delete_account(
        self,
        auth_context: AuthenticatedSessionContext,
        confirm_email: str,
        password: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        normalized_user_email = auth_context.user.email.strip().lower()
        normalized_confirm_email = confirm_email.strip().lower()
        if normalized_user_email != normalized_confirm_email:
            raise AccountDeletionConfirmationMismatchError

        rate_limit_ip = ip_address or "unknown"
        if auth_context.user.password_hash is not None:
            if not self._auth_rate_limiter.is_account_deletion_reauth_allowed(
                    rate_limit_ip, normalized_user_email):
                raise RateLimitExceededError(self._auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            if not password:
                raise AccountDeletionReauthRequiredError
            password_matches = await self._password_hash_executor.verify(
                password,
                auth_context.user.password_hash,
            )
            if not password_matches:
                self._auth_rate_limiter.record_failure(
                    rate_limit_ip,
                    normalized_user_email,
                    include_email_bucket=False,
                )
                await self._auth_repository.create_audit_log(
                    AuthAuditLog(
                        user_id=auth_context.user.id,
                        session_id=auth_context.session.id,
                        event_type=AuthEventType.ACCOUNT_DELETION_REAUTH_FAILED,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ))
                raise AccountDeletionInvalidPasswordError
        else:
            await self._require_fresh_oidc_reauth(auth_context)

        deleted_at = utcnow()
        async with self._unit_of_work.transaction():
            await self._sample_item_repository.delete_all_for_owner(auth_context.user.id)
            await self._auth_repository.delete_auth_identities_for_user(auth_context.user.id)
            await self._auth_repository.mark_user_deleted(
                auth_context.user.id,
                deleted_at,
                session_id=auth_context.session.id,
                ip_address=ip_address,
            )
            await self._auth_repository.revoke_sessions_for_user(auth_context.user.id, deleted_at)

    async def _require_fresh_oidc_reauth(
        self,
        auth_context: AuthenticatedSessionContext,
    ) -> None:
        auth_time = auth_context.session.last_oidc_auth_time_at
        if auth_time is None:
            raise AccountDeletionOidcReauthRequiredError(await self._linked_provider_details(
                auth_context.user.id))
        if utcnow() - auth_time > timedelta(
                seconds=self._oidc_settings.AUTH_OIDC_REAUTH_FRESHNESS_SECONDS):
            raise AccountDeletionOidcReauthRequiredError(await self._linked_provider_details(
                auth_context.user.id))

    async def _linked_provider_details(self, user_id: UUID) -> list[dict[str, str]]:
        identities = await self._auth_repository.find_identities_by_user_id(user_id)
        providers_by_id = {
            provider.provider_id: provider
            for provider in self._oidc_settings.providers
        }
        details: list[dict[str, str]] = []
        seen_provider_ids: set[str] = set()
        for identity in identities:
            if identity.provider_id in seen_provider_ids:
                continue
            provider = providers_by_id.get(identity.provider_id)
            if provider is None:
                continue
            details.append({
                "providerId": provider.provider_id,
                "displayName": provider.display_name,
            })
            seen_provider_ids.add(identity.provider_id)
        return details
