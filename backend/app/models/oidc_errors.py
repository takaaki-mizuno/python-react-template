class OidcProviderNotConfiguredError(Exception):
    pass


class OidcProviderUnavailableError(Exception):
    pass


class OidcProviderMetadataError(Exception):
    pass


class OidcStateMismatchError(Exception):
    pass


class OidcBrowserBindingMismatchError(Exception):
    pass


class OidcTokenExchangeError(Exception):
    pass


class OidcProviderAccessDeniedError(Exception):
    pass


class OidcClaimsValidationError(Exception):
    pass


class OidcEmailNotVerifiedError(Exception):
    pass


class OidcProvisioningDisabledError(Exception):
    pass


class OidcIdentityLinkRequiredError(Exception):
    pass


class OidcIdentityLinkDisabledError(Exception):
    pass


class OidcIdentityUnavailableError(Exception):
    pass


class OidcAuthorizationRateLimitedError(Exception):
    pass


class OidcReauthSubjectMismatchError(Exception):
    pass


class OidcReauthAuthenticationRequiredError(Exception):
    pass


class OidcReauthAuthTimeRequiredError(Exception):
    pass


class OidcReauthStaleError(Exception):
    pass


class OidcCallbackFlowError(Exception):

    def __init__(self, error: Exception, *, purpose: str, redirect_path: str) -> None:
        super().__init__(str(error))
        self.error = error
        self.purpose = purpose
        self.redirect_path = redirect_path
