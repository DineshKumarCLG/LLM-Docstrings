/**
 * ShimmerButton — 21st.dev-inspired button with animated shimmer sweep.
 * A premium CTA button with a light sweep animation on hover.
 */
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ShimmerButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  className?: string;
  shimmerColor?: string;
  shimmerDuration?: number;
}

export function ShimmerButton({
  children,
  className,
  shimmerColor = "rgba(255, 255, 255, 0.20)",
  shimmerDuration = 2.5,
  ...props
}: ShimmerButtonProps) {
  return (
    <motion.button
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98, y: 0 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={cn(
        "btn-primary relative overflow-hidden",
        className,
      )}
      {...props}
    >
      {/* Animated shimmer sweep */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `linear-gradient(110deg, transparent 25%, ${shimmerColor} 50%, transparent 75%)`,
          backgroundSize: "200% 100%",
          animation: `shimmer ${shimmerDuration}s ease-in-out infinite`,
        }}
      />
      <span className="relative z-10 flex items-center justify-center gap-2">
        {children}
      </span>
    </motion.button>
  );
}
