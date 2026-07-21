declare module "@legacy/pages/*.js" {
  export function render(
    container: HTMLElement,
    params: Record<string, unknown>,
    router: { navigate: (url: string, replace?: boolean) => void },
  ): Promise<(() => void) | void>;
}
