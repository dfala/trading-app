import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// Some components persist state (e.g. live sandbox history) to localStorage.
// Clear it between tests so persisted data never leaks across cases.
afterEach(() => {
  try {
    window.localStorage?.clear();
  } catch {
    // localStorage may be unavailable in some environments; ignore.
  }
});
