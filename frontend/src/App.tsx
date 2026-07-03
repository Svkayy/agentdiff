import { BrowserRouter, Routes, Route } from "react-router-dom";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import { Shell } from "@/components/Shell";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { RunDetailPage } from "@/pages/RunDetailPage";

function AuthGate() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-shell-bg">
      <SignIn />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SignedOut>
        <AuthGate />
      </SignedOut>
      <SignedIn>
        <Shell>
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
          </Routes>
        </Shell>
      </SignedIn>
    </BrowserRouter>
  );
}
