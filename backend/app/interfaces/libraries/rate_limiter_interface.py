from abc import ABCMeta, abstractmethod


class LoginRateLimiterInterface(metaclass=ABCMeta):

    @abstractmethod
    async def is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def is_account_deletion_reauth_allowed(
        self,
        ip_address: str,
        normalized_email: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool = True,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def record_success(self, ip_address: str, normalized_email: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def is_registration_allowed(self, ip_address: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def record_registration(self, ip_address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def is_oidc_authorization_allowed(self, ip_address: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def record_oidc_authorization(self, ip_address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError
