import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { fetchProjects, createProject, type Project } from "@/lib/api";
import { useSkipEntrance } from "@/lib/utils";

const ease = [0.22, 1, 0.36, 1] as const;

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-0 border-2 border-foreground md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-36 animate-pulse bg-muted md:border-r-2 md:border-foreground md:last:border-r-0"
        />
      ))}
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center border-2 border-foreground py-3xl text-center">
      <div className="mb-md font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        No projects yet
      </div>
      <h2 className="mb-sm font-mono text-2xl font-bold uppercase tracking-tight text-foreground">
        Create your first project
      </h2>
      <p className="mb-lg max-w-md font-mono text-small text-muted-foreground">
        A project holds your runs, API keys, and Slack alerts. Create one to get
        started with the AgentDiff CI gate or live drift collector.
      </p>
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
        onClick={onCreate}
        className="group flex items-center gap-0 font-mono text-xs uppercase tracking-wider text-background"
      >
        <span className="flex h-9 w-9 items-center justify-center bg-[#ea580c]">
          <ArrowRight size={14} strokeWidth={2} className="text-background" />
        </span>
        <span className="bg-foreground px-lg py-2.5">Create project</span>
      </motion.button>
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

  // Turn a display name into a `name.proj`-style mono label.
  const slug = project.name.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9._-]/g, "");

  return (
    <motion.button
      initial={skip ? false : { y: 12, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.32, ease, delay: index * 0.07 }}
      onClick={onClick}
      className="group flex h-full w-full flex-col border-2 border-foreground bg-background text-left transition-colors hover:bg-foreground/[0.03]"
    >
      {/* Header bar */}
      <div className="flex items-center justify-between border-b-2 border-foreground px-5 py-3">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {slug ? `${slug}.proj` : "project.proj"}
        </span>
        <span className="font-mono text-xs tracking-[0.2em] text-muted-foreground opacity-50">
          {String(index + 1).padStart(2, "0")}
        </span>
      </div>
      {/* Body */}
      <div className="flex flex-1 flex-col px-5 py-4">
        <h3 className="font-mono text-lg font-bold uppercase leading-tight tracking-tight text-foreground">
          {project.name}
        </h3>
        <p className="mt-2 font-mono text-small leading-relaxed text-muted-foreground">
          View runs, manage API keys, and configure Slack alerts.
        </p>
        <div className="mt-auto pt-md">
          <ArrowRight
            size={14}
            strokeWidth={2}
            className="text-[#ea580c] transition-transform group-hover:translate-x-1"
            aria-hidden="true"
          />
        </div>
      </div>
    </motion.button>
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
  const [search, setSearch] = useState("");

  const load = useCallback(
    async (q?: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchProjects(getToken, q?.trim() || undefined);
        setProjects(data.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load projects");
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  // Initial load.
  useEffect(() => {
    void load();
  }, [load]);

  // Debounced server-side search.
  useEffect(() => {
    const t = setTimeout(() => void load(search), 300);
    return () => clearTimeout(t);
  }, [search, load]);

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
      {/* Header */}
      <div className="relative mb-2xl flex items-end justify-between">
        <div>
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            {"// PROJECTS"}
          </div>
          <h1 className="font-mono text-2xl font-bold uppercase tracking-tight text-foreground">
            Your projects
          </h1>
        </div>
        <div className="flex items-center gap-md">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects…"
            aria-label="Search projects"
            className="w-56 border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
          />
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="border-2 border-foreground bg-background px-md py-sm font-mono text-xs uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
          >
            {showCreate ? "Cancel" : "+ New project"}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-lg flex items-center justify-between border-2 border-[#ea580c] bg-background px-md py-sm">
          <span className="font-mono text-small text-[#ea580c]">{error}</span>
          <button
            onClick={() => void load()}
            className="ml-md font-mono text-small font-medium text-[#ea580c] underline"
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
            transition={{ duration: 0.2, ease }}
            onSubmit={(e) => void handleCreate(e)}
            className="mb-xl flex items-end gap-md border-2 border-foreground bg-background p-lg"
          >
            <div className="flex-1">
              <label className="mb-xs block font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Project name
              </label>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="my-agent-project"
                className="w-full border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
              />
            </div>
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="bg-foreground px-lg py-sm font-mono text-xs uppercase tracking-wider text-background transition-opacity disabled:opacity-40"
            >
              {creating ? "Creating…" : "Create"}
            </button>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Content */}
      {loading ? (
        <Skeleton />
      ) : projects.length === 0 && search.trim() ? (
        <div className="border-2 border-foreground bg-background py-2xl text-center font-mono text-small text-muted-foreground">
          No projects match{" "}
          <span className="font-mono text-foreground">&ldquo;{search.trim()}&rdquo;</span>.
        </div>
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
