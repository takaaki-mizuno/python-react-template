export const queryKeys = {
  auth: {
    root: ['auth'] as const,
    me: ['auth', 'me'] as const,
    strictMe: ['auth', 'me', 'strict'] as const,
  },
}
