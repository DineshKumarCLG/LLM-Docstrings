/**
 * GlassCard — 21st.dev-inspired frosted glass card with 3D tilt on hover.
 * Uses framer-motion for smooth spring-based tilt and scale.
 */
import { useRef, useState, useCallback } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  /** Max tilt angle in degrees */
  tiltAmount?: number;
  /** Enable/disable tilt */
  tilt?: boolean;
  /** Enable spotlight on hover */
  spotlight?: boolean;
}

export function GlassCard({
  children,
  className,
  tiltAmount = 6,
  tilt = true,
  spotlight = true,
}: GlassCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [hovering, setHovering] = useState(false);

  const x = useMotionValue(0.5);
  const y = useMotionValue(0.5);

  const rotateX = useSpring(useTransform(y, [0, 1], [tiltAmount, -tiltAmount]), {
    stiffness: 200,
    damping: 30,
  });
  const rotateY = useSpring(useTransform(x, [0, 1], [-tiltAmount, tiltAmount]), {
    stiffness: 200,
    damping: 30,
  });

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!ref.current || !tilt) return;
      const rect = ref.current.getBoundingClientRect();
      x.set((e.clientX - rect.left) / rect.width);
      y.set((e.clientY - rect.top) / rect.height);
    },
    [x, y, tilt],
  );

  const handleMouseLeave = useCallback(() => {
    x.set(0.5);
    y.set(0.5);
    setHovering(false);
  }, [x, y]);

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={handleMouseLeave}
      style={{
        rotateX: tilt ? rotateX : 0,
        rotateY: tilt ? rotateY : 0,
        transformPerspective: 800,
      }}
      whileHover={{ scale: 1.01 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className={cn("glass relative", className)}
    >
      {/* Spotlight glare that follows cursor */}
      {spotlight && (
        <motion.div
          className="pointer-events-none absolute inset-0 z-10 rounded-[inherit]"
          animate={{
            opacity: hovering ? 1 : 0,
            background: hovering
              ? `radial-gradient(300px circle at ${x.get() * 100}% ${y.get() * 100}%, rgba(255,255,255,0.15), transparent 60%)`
              : "none",
          }}
          transition={{ duration: 0.2 }}
        />
      )}
      {children}
    </motion.div>
  );
}
