import type { Verdict } from "@/types";

const NAV = ["Explorer", "Runs", "Benchmarks", "Configs"];

export function TopNav({
  verdict,
  baselineRef,
  candidateRef,
}: {
  verdict: Verdict;
  baselineRef: string;
  candidateRef: string;
}) {
  return (
    <header className="glass-panel sticky top-0 z-50 flex h-14 w-full shrink-0 items-center justify-between px-6">
      <div className="flex items-center gap-6">
        <span className="text-lg font-bold tracking-tight text-slate-800">AgentDiff</span>
        <nav className="hidden h-full items-center gap-6 md:flex">
          {NAV.map((item) => (
            <a
              key={item}
              href="#"
              className={
                item === "Runs"
                  ? "flex h-14 items-center border-b-2 border-primary-dark text-sm font-medium text-primary-dark"
                  : "text-sm font-medium text-text-muted transition-colors hover:text-text-main"
              }
            >
              {item}
            </a>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <div className="mr-2 flex items-center rounded border border-slate-200 bg-white/50 px-2 py-1 shadow-sm">
          <span className="font-mono text-xs text-text-muted">{baselineRef}</span>
          <span className="material-symbols-outlined mx-1 text-[14px] text-text-muted">arrow_forward</span>
          <span className="font-mono text-xs text-slate-700">{candidateRef}</span>
        </div>
        {verdict === "fail" && (
          <div className="mr-2 rounded border border-ember/30 bg-red-50 px-2 py-0.5 font-mono text-[10px] font-bold tracking-wider text-ember">
            REGRESSION
          </div>
        )}
        <button className="rounded bg-ember px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-600">
          Deploy Fix
        </button>
        <button className="rounded-full p-1.5 text-text-muted transition-colors hover:bg-slate-100 hover:text-text-main">
          <span className="material-symbols-outlined text-[20px]">settings</span>
        </button>
        <button className="rounded-full p-1.5 text-text-muted transition-colors hover:bg-slate-100 hover:text-text-main">
          <span className="material-symbols-outlined text-[20px]">notifications</span>
        </button>
        <div className="ml-1 grid h-8 w-8 place-items-center rounded-full border border-slate-200 bg-gradient-to-br from-slate-200 to-slate-300 text-[11px] font-semibold text-slate-600 shadow-sm">
          SK
        </div>
      </div>
    </header>
  );
}
