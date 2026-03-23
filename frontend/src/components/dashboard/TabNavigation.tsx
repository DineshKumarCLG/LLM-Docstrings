import { FileText, ShieldCheck, BookOpen } from "lucide-react";
import { AnimatedTabs } from "@/components/ui";
import { type Analysis, type DashboardTab } from "@/types";

interface TabNavigationProps {
  analysisId: string;
  analysis: Analysis;
  activeTab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
}

const TABS: { id: DashboardTab; label: string; icon: React.ReactNode }[] = [
  { id: "documentation", label: "Documentation", icon: <FileText className="h-4 w-4" /> },
  { id: "verification",  label: "Verification",  icon: <ShieldCheck className="h-4 w-4" /> },
  { id: "research",      label: "Research",       icon: <BookOpen className="h-4 w-4" /> },
];

export default function TabNavigation({
  analysisId: _analysisId,
  analysis: _analysis,
  activeTab,
  onTabChange,
}: TabNavigationProps) {
  return (
    <AnimatedTabs
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={(id) => onTabChange(id as DashboardTab)}
      layoutId="dashboard-tab-indicator"
    />
  );
}
