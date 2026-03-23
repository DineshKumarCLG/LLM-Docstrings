/**
 * AnimatedTabs — 21st.dev-inspired tab bar with sliding indicator.
 * Uses framer-motion layoutId for smooth tab indicator animation.
 */
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface AnimatedTabsProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  className?: string;
  layoutId?: string;
}

export function AnimatedTabs({
  tabs,
  activeTab,
  onTabChange,
  className,
  layoutId = "tab-indicator",
}: AnimatedTabsProps) {
  return (
    <div className={cn("flex gap-1 p-1.5 rounded-2xl skeu-inset w-fit", className)}>
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-colors duration-200 z-10",
              isActive
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {isActive && (
              <motion.div
                layoutId={layoutId}
                className="absolute inset-0 glass-strong rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)]"
                transition={{
                  type: "spring",
                  stiffness: 350,
                  damping: 30,
                }}
              />
            )}
            <span
              className={cn(
                "relative z-10 transition-colors duration-200",
                isActive ? "text-indigo-600" : "text-current",
              )}
            >
              {tab.icon}
            </span>
            <span className="relative z-10">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
