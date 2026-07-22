import type { AppConfig } from "@/types/config";

export function hasOperatorOrAdmin(
  roles: string[] | null | undefined,
  config: AppConfig,
): boolean {
  const roleNames = config.role_names || {};
  const operatorRole = roleNames.operator || "operator";
  const adminRole = roleNames.admin || "admin";
  return !!roles && (roles.includes(operatorRole) || roles.includes(adminRole));
}
