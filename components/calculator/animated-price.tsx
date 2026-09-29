"use client";

import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { formatNumber } from "@/lib/utils";

export function AnimatedPrice({ value, className, duration = 0.8 }: { value: number; className?: string; duration?: number }) {
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);

  useEffect(() => {
    if (reduce) {
      prev.current = value;
      return;
    }
    const controls = animate(prev.current, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, duration, reduce]);

  return (
    <span className={className} aria-live="polite">
      <span className="tabular">{formatNumber(reduce ? value : display)}</span> ₽
    </span>
  );
}
