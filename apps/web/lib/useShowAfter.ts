"use client";

import { useEffect, useState } from "react";

/**
 * How long a load may take before a skeleton appears. Faster loads show nothing, rather
 * than a frame of grey shapes that is gone before it can be read.
 */
export const SKELETON_DELAY_MS = 300;

/** False until `delayMs` has passed since mount, then true. */
export function useShowAfter(delayMs: number = SKELETON_DELAY_MS): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs]);
  return visible;
}
