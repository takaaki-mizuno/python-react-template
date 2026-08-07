export const queryKeys = {
  auth: {
    root: ['auth'] as const,
    me: ['auth', 'me'] as const,
    oidcProviders: ['auth', 'oidcProviders'] as const,
  },
}
