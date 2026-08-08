import { Routes, Route } from "react-router-dom";
import FileUploader from "@/components/upload/FileUploader";
import DashboardHome from "@/pages/DashboardHome";
import AnalysisDetail from "@/pages/AnalysisDetail";
import CodeViewerPage from "@/pages/CodeViewerPage";
import ProjectRunPage from "@/pages/ProjectRunPage";
import { RAGWorkspace } from "@/pages/RAGWorkspace";

export default function App() {
  return (
    <div className="min-h-screen text-foreground">
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/upload" element={<FileUploader />} />
        <Route path="/rag" element={<RAGWorkspace />} />
        <Route path="/analyses/:id" element={<AnalysisDetail />} />
        <Route path="/analyses/:id/code" element={<CodeViewerPage />} />
        <Route path="/analyses/:id/export" element={<CodeViewerPage />} />
        <Route path="/batches/:batchId" element={<ProjectRunPage />} />
      </Routes>
    </div>
  );
}
