"use client";

import { useEffect } from "react";
import { trackEvent } from "@/lib/analytics/events";

export function ProjectViewTracker({ slug }: { slug: string }) {
  useEffect(() => {
    trackEvent("project_view", { project: slug });
  }, [slug]);
  return null;
}
