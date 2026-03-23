import { cn } from "@/lib/utils";
import { CATEGORY_COLORS, CATEGORY_LABELS } from "@/types";
import type { BCVCategory } from "@/types";

const BCV_CATEGORIES: BCVCategory[] = ["RSV", "PCV", "SEV", "ECV", "COV", "CCV"];

interface CategoryBreakdownChipsProps {
  breakdown: Record<BCVCategory, number>;
  activeFilter: BCVCategory | "all";
  onFilterChange: (category: BCVCategory | "all") => void;
}

export default function CategoryBreakdownChips({ breakdown, activeFilter, onFilterChange }: CategoryBreakdownChipsProps) {
  const handleChipClick = (category: BCVCategory) => {
    if (activeFilter === category) onFilterChange("all");
    else onFilterChange(category);
  };

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
      {BCV_CATEGORIES.map((category) => {
        const color = CATEGORY_COLORS[category];
        const count = breakdown[category] ?? 0;
        const isActive = activeFilter === category;
        const hasViolations = count > 0;

        return (
          <button
            key={category}
            type="button"
            onClick={() => handleChipClick(category)}
            aria-pressed={isActive}
            aria-label={`${CATEGORY_LABELS[category]}: ${count} violation${count !== 1 ? "s" : ""}${isActive ? ", active filter" : ""}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5",
              "text-sm font-semibold transition-all duration-200 cursor-pointer select-none",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
              isActive
                ? "ring-2 ring-offset-2 ring-offset-background opacity-100 shadow-lg scale-105"
                : cn("hover:opacity-90 hover:scale-105", hasViolations ? "opacity-75" : "opacity-30"),
            )}
            style={{
              backgroundColor: `${color}25`,
              color: color,
              borderWidth: 1,
              borderColor: `${color}40`,
              ...(isActive ? { "--tw-ring-color": color } as React.CSSProperties : {}),
            }}
          >
            <span>{category}</span>
            <span className={cn("inline-flex items-center justify-center rounded-full min-w-[1.25rem] h-5 px-1 text-xs font-bold bg-black/10")}>{count}</span>
          </button>
        );
      })}
    </div>
  );
}
