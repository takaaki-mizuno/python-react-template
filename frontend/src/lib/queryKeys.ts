export const queryKeys = {
  auth: {
    root: ['auth'] as const,
    me: ['auth', 'me'] as const,
    oidcProviders: ['auth', 'oidcProviders'] as const,
  },
  adminUsers: {
    root: ['adminUsers'] as const,
    list: (params: unknown) => ['adminUsers', 'list', params] as const,
    detail: (userId: string) => ['adminUsers', 'detail', userId] as const,
    roles: ['adminUsers', 'roles'] as const,
  },
}
