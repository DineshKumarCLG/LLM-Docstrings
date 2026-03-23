/**
 * AnimatedNumber — 21st.dev-inspired animated number ticker
 * Rolls digits from 0 to target with spring physics via framer-motion.
 */
import { useEffect, useRef, useState } from "react";
import { useSpring, useTransform, useInView } from "framer-motion";
import { cn } from "@/lib/utils";

interface AnimatedNumberProps {
  value: number;
  className?: string;
  /** Format as percentage string */
  suffix?: string;
  /** Decimal places */
  decimals?: number;
  /** Spring stiffness — lower = slower */
  stiffness?: number;
  /** Spring damping */
  damping?: number;
}

export function AnimatedNumber({
  value,
  className,
  suffix = "",
  decimals = 0,
  stiffness = 60,
  damping = 20,
}: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const spring = useSpring(0, { stiffness, damping });
  const display = useTransform(spring, (v) =>
    decimals > 0 ? v.toFixed(decimals) : Math.round(v).toLocaleString(),
  );

  // Subscribe to the MotionValue and render as plain string
  const [rendered, setRendered] = useState(() =>
    decimals > 0 ? (0).toFixed(decimals) : "0",
  );

  useEffect(() => {
    const unsubscribe = display.on("change", (v) => setRendered(v));
    return unsubscribe;
  }, [display]);

  useEffect(() => {
    if (isInView) spring.set(value);
  }, [isInView, value, spring]);

  return (
    <span ref={ref} className={cn("tabular-nums", className)}>
      {rendered}
      {suffix}
    </span>
  );
}
