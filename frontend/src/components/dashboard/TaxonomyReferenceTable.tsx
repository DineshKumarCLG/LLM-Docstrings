import { cn } from "@/lib/utils";
import { BCV_TAXONOMY } from "@/lib/constants";
import { CATEGORY_COLORS } from "@/types";
import type { BCVCategory } from "@/types";

interface TaxonomyReferenceTableProps {
  highlightCategories?: BCVCategory[];
}

export default function TaxonomyReferenceTable({ highlightCategories = [] }: TaxonomyReferenceTableProps) {
  const hasHighlights = highlightCategories.length > 0;

  return (
    <div className="rounded-2xl glass overflow-hidden">
      <div className="px-4 py-3 border-b border-foreground/[0.06]">
        <h3 className="text-sm font-semibold text-foreground/80 uppercase tracking-wide">BCV Taxonomy Reference</h3>
      </div>
      <div className="divide-y divide-foreground/[0.05]">
        {BCV_TAXONOMY.map((entry) => {
          const color = CATEGORY_COLORS[entry.category];
          const isHighlighted = !hasHighlights || highlightCategories.includes(entry.category);
          return (
            <div
              key={entry.category}
              className={cn("flex items-start gap-4 px-4 py-3 transition-opacity duration-200", isHighlighted ? "opacity-100" : "opacity-30")}
              style={{ borderLeft: `4px solid ${color}` }}
            >
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center rounded-lg px-2 py-0.5 text-xs font-bold text-white" style={{ backgroundColor: color }}>{entry.category}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground/90 leading-snug">{entry.fullName}</p>
                <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{entry.description}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
