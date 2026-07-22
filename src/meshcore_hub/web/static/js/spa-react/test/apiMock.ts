import { vi } from "vitest";

import * as api from "@/utils/api";

export type ApiGetMap = Record<string, unknown>;

export function mockApiGet(responses: ApiGetMap) {
  return vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    const base = path.split("?")[0];
    if (base in responses) return responses[base];
    throw new Error(`Unexpected apiGet path: ${path}`);
  });
}

export function mockApiGetError(error: Error) {
  return vi.spyOn(api, "apiGet").mockRejectedValue(error);
}

export function mockApiPost(response: unknown = null) {
  return vi.spyOn(api, "apiPost").mockResolvedValue(response);
}

export function mockApiPut(response: unknown = null) {
  return vi.spyOn(api, "apiPut").mockResolvedValue(response);
}

export function mockApiDelete() {
  return vi.spyOn(api, "apiDelete").mockResolvedValue(undefined);
}
