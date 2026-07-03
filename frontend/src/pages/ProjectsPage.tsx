import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { AnimatePresence, motion } from "framer-motion";
import { fetchProjects, createProject, type Project } from "@/lib/api";
import { Spotlight } from "@/components/aceternity/Spotlight";
import { useSkipEntrance } from "@/lib/utils";

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-36 animate-pulse rounded-md border border-hairline bg-hairline"
        />
      ))}
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-3xl text-center">
      <div className="mb-md font-mono text-micro uppercase tracking-widest text-neutral-faint">
        No projects yet
      </div>
      <h2 className="mb-sm font-display text-h1 font-bold text-ink-dark">
        Create your first project
      </h2>
      <p className="mb-lg max-w-md text-small text-neutral-muted">
        A project holds your runs, API keys, and Slack alerts. Create one to get
        started with the AgentDiff CI gate or live drift collector.
      </p>
      <button
        onClick={onCreate}
        className="rounded-sm border border-ink-dark bg-ink-dark px-lg py-sm text-small font-medium text-white transition-colors hover:bg-neutral-muted"
      >
        Create project
      </button>
    </div>
  );
}

function ProjectCard({
  project,
  index,
  onClick,
}: {
  project: Project;
  index: number;
  onClick: () => void;
}) {
  const skip = useSkipEntrance();
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      initial={skip ? false : { y: 12, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.32, ease: "easeOut", delay: index * 0.07 }}
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <AnimatePresence>
        {hovered && (
          <motion.span
            layoutId="project-card-slab"
            className="absolute -inset-1.5 rounded-lg bg-[#EFEDE8]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2, ease: "easeOut" } }}
            exit={{ opacity: 0, transition: { duration: 0.2, ease: "easeIn" } }}
          />
        )}
      </AnimatePresence>
      <button
        onClick={onClick}
        className="relative flex h-full w-full flex-col rounded-md border border-hairline bg-white p-6 text-left transition-shadow hover:shadow-sm"
      >
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          Project
        </div>
        <h3 className="font-display text-lg font-bold leading-tight text-ink-dark">
          {project.name}
        </h3>
        <p className="mt-2 text-small leading-relaxed text-neutral-muted">
          View runs, manage API keys, and configure Slack alerts.
        </p>
        <div className="mt-auto pt-md text-micro text-neutral-faint">
          →
        </div>
      </button>
    </motion.div>
  );
}

export function ProjectsPage() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProjects(getToken);
      setProjects(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createProject(newName.trim(), getToken);
      setProjects((prev) => [...prev, created]);
      setNewName("");
      setShowCreate(false);
      navigate(`/projects/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="relative mx-auto w-full max-w-[1240px] px-xl py-2xl">
      <Spotlight className="left-0 top-0 h-full w-full" />

      {/* Header */}
      <div className="relative mb-2xl flex items-end justify-between">
        <div>
          <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Projects
          </div>
          <h1 className="font-display text-h1 font-bold text-ink-dark">Your projects</h1>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-sm border border-hairline bg-white px-md py-sm text-small font-medium text-ink-dark transition-colors hover:border-ink-dark"
        >
          {showCreate ? "Cancel" : "+ New project"}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-lg flex items-center justify-between rounded-sm border border-ember/30 bg-ember/5 px-md py-sm">
          <span className="text-small text-ember">{error}</span>
          <button
            onClick={() => void load()}
            className="ml-md text-small font-medium text-ember underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Create form */}
      <AnimatePresence>
        {showCreate && (
          <motion.form
            key="create-form"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            onSubmit={(e) => void handleCreate(e)}
            className="mb-xl flex items-end gap-md rounded-md border border-hairline bg-white p-lg"
          >
            <div className="flex-1">
              <label className="mb-xs block font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Project name
              </label>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="my-agent-project"
                className="w-full rounded-sm border border-hairline bg-shell-bg px-md py-sm text-small text-ink-dark placeholder:text-neutral-faint focus:border-ink-dark focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity disabled:opacity-40"
            >
              {creating ? "Creating…" : "Create"}
            </button>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Content */}
      {loading ? (
        <Skeleton />
      ) : projects.length === 0 ? (
        <EmptyState onCreate={() => setShowCreate(true)} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {projects.map((p, i) => (
            <ProjectCard
              key={p.id}
              project={p}
              index={i}
              onClick={() => navigate(`/projects/${p.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
