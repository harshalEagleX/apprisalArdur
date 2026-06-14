/**
 * Render a human-friendly name for a user/operator/reviewer.
 *
 * The backend often only has an email as the username (no separate full name),
 * which surfaces in the UI as a raw system identifier like
 * "dhoteharshal16@gmail.com". Showing the local part keeps the name readable and
 * never leaks the bare domain. A real full name (no "@") is returned untouched.
 */
export function displayName(value: string | null | undefined): string {
  if (value == null) return "Unknown user";
  const v = String(value).trim();
  if (!v) return "Unknown user";
  const at = v.indexOf("@");
  return at > 0 ? v.slice(0, at) : v;
}

export default displayName;
