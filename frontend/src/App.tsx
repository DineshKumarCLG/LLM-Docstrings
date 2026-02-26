import { Routes, Route } from "react-router-dom";
import FileUploader from "@/components/upload/FileUploader";
import DashboardHome from "@/pages/DashboardHome";
import AnalysisDetail from "@/pages/AnalysisDetail";
import CodeViewerPage from "@/pages/CodeViewerPage";

/**
 * App shell with routes.
 * Dashboard, analysis detail, code viewer, and export wired.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/upload" element={<FileUploader />} />
        <Route path="/analyses/:id" element={<AnalysisDetail />} />
        <Route path="/analyses/:id/code" element={<CodeViewerPage />} />
        <Route path="/analyses/:id/export" element={<CodeViewerPage />} />
      </Routes>
    </div>
  );
}
