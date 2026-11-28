/** Full-page load of /login, so every per-user store starts empty for the next sign-in. */
export function goToLoginPage(): void {
  globalThis.location.assign("/login");
}
