/**
 * Shared runtime configuration.
 *
 * `JAVA` is the base URL of the Java backend. It was previously copy-pasted
 * into nine separate files; centralising it here means the env strategy lives
 * in exactly one place.
 */
export const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";
