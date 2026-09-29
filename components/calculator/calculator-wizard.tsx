"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, ArrowRight, Loader2, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics/events";
import { postJson } from "@/lib/leads/client";
import { calculateEstimate } from "@/lib/pricing/engine";
import type { EstimateResult, PricingConfig } from "@/lib/pricing/types";
import { cn } from "@/lib/utils";
import { CalculatorResult } from "./result";
import { StepArea, StepBedrooms, StepHouseType, StepOptions, StepPackage, StepPeriod, StepTechnology } from "./steps";
import { DesktopSummary, MobileSummaryBar } from "./summary";
import { STEP_HINTS, STEP_TITLES, type CalculatorState, type ProjectContext } from "./types";

const STORAGE_KEY = "forma-calculator-v1";
const STEPS = [StepHouseType, StepArea, StepBedrooms, StepTechnology, StepPackage, StepOptions, StepPeriod];
const TOTAL = STEPS.length;

interface WizardProps {
  config: PricingConfig;
  initial: Partial<CalculatorState>;
  project: ProjectContext | null;
}

function isStepValid(step: number, s: CalculatorState) {
  switch (step) {
    case 0: return Boolean(s.houseType);
    case 3: return Boolean(s.technology);
    case 4: return Boolean(s.package);
    case 6: return Boolean(s.period);
    default: return true;
  }
}

interface SavedProgress {
  state: CalculatorState;
  step: number;
}

function readSavedRaw() {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

const noopSubscribe = () => () => undefined;

function parseSaved(raw: string | null): SavedProgress | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as SavedProgress;
    return data?.state && data.step > 0 ? data : null;
  } catch {
    return null;
  }
}

export function CalculatorWizard({ config, initial, project }: WizardProps) {
  const reduce = useReducedMotion();
  const defaults: CalculatorState = useMemo(
    () => ({
      houseType: null,
      area: Math.min(Math.max(150, config.params.areaMin), config.params.areaMax),
      bedrooms: 3,
      technology: null,
      package: null,
      options: [],
      period: null,
      ...initial,
    }),
    [config.params.areaMin, config.params.areaMax, initial],
  );

  const [state, setState] = useState<CalculatorState>(defaults);
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const [phase, setPhase] = useState<"steps" | "result">("steps");
  const [serverEstimate, setServerEstimate] = useState<EstimateResult | null>(null);
  const [calculationId, setCalculationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const started = useRef(false);
  const topRef = useRef<HTMLDivElement>(null);

  // Незавершённый расчёт из sessionStorage читается как внешнее хранилище (без setState в эффекте).
  const savedRaw = useSyncExternalStore(noopSubscribe, readSavedRaw, () => null);
  const [savedDismissed, setSavedDismissed] = useState(false);
  const saved = useMemo(() => (project || savedDismissed ? null : parseSaved(savedRaw)), [project, savedDismissed, savedRaw]);

  useEffect(() => {
    if (project) trackEvent("calculator_project_selected", { project: project.slug });
  }, [project]);

  const restore = () => {
    if (!saved) return;
    setState({ ...defaults, ...saved.state });
    setStep(Math.min(Math.max(saved.step, 0), TOTAL - 1));
    setSavedDismissed(true);
  };

  useEffect(() => {
    if (phase !== "steps" || (step === 0 && !started.current)) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ state, step }));
    } catch {
      // Хранилище недоступно (приватный режим) — прогресс просто не сохраняется.
    }
  }, [state, step, phase]);

  const update = useCallback((patch: Partial<CalculatorState>) => {
    if (!started.current) {
      started.current = true;
      trackEvent("calculator_start", { project: project?.slug });
    }
    setSavedDismissed(true);
    setState((s) => ({ ...s, ...patch }));
  }, [project?.slug]);

  const liveEstimate = useMemo(() => {
    if (!state.houseType || !state.technology) return null;
    try {
      return calculateEstimate(config, {
        houseType: state.houseType,
        area: state.area,
        bedrooms: state.bedrooms,
        technology: state.technology,
        package: state.package ?? config.packages[config.packages.length - 1]?.code ?? "",
        options: state.options,
      });
    } catch {
      return null;
    }
  }, [config, state]);

  const scrollTop = () => topRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });

  const goTo = (next: number) => {
    setDirection(next > step ? 1 : -1);
    setStep(next);
    trackEvent("calculator_step", { step: next + 1 });
    scrollTop();
  };

  const finish = async () => {
    setLoading(true);
    try {
      const res = await postJson<{ ok: true; id: string; estimate: EstimateResult }>("/api/calculations", { ...state, projectSlug: project?.slug });
      setServerEstimate(res.estimate);
      setCalculationId(res.id);
      setPhase("result");
      trackEvent("calculator_complete", { price: res.estimate.total, project: project?.slug });
      scrollTop();
    } catch (error) {
      toast.error("Не удалось выполнить расчёт", { description: error instanceof Error ? error.message : undefined });
    } finally {
      setLoading(false);
    }
  };

  const next = () => (step < TOTAL - 1 ? goTo(step + 1) : finish());
  const valid = isStepValid(step, state);
  const reset = () => {
    setState({ ...defaults, ...initial });
    setPhase("steps");
    setServerEstimate(null);
    setCalculationId(null);
    goTo(0);
  };

  const Step = STEPS[step];
  const progress = phase === "result" ? 100 : ((step + 1) / TOTAL) * 100;
  const nextLabel = step === TOTAL - 1 ? "Рассчитать" : "Далее";

  const nextButton = (
    <Button size="lg" onClick={next} disabled={!valid || loading} className="shrink-0">
      {loading && <Loader2 className="animate-spin" />}
      {nextLabel}
      {!loading && <ArrowRight />}
    </Button>
  );

  return (
    <div ref={topRef} className="container-page scroll-mt-20 pb-32 lg:pb-24">
      <div className="mb-8 sm:mb-10">
        <div className="flex items-center justify-between text-sm">
          <p className="font-medium" aria-live="polite">
            {phase === "result" ? "Расчёт готов" : `Шаг ${step + 1} из ${TOTAL}`}
          </p>
          <button type="button" onClick={reset} className="flex items-center gap-1.5 text-muted-foreground transition hover:text-foreground cursor-pointer">
            <RotateCcw className="size-3.5" />
            Начать заново
          </button>
        </div>
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-sand/60" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress)} aria-label="Прогресс расчёта">
          <motion.div className="h-full rounded-full bg-accent" initial={false} animate={{ width: `${progress}%` }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
        </div>
        {phase === "steps" && (
          <ol className="mt-4 hidden gap-1 md:flex" aria-label="Шаги">
            {STEP_TITLES.map((title, i) => (
              <li key={title} className="flex-1">
                <button
                  type="button"
                  disabled={i > step && !Array.from({ length: i }, (_, k) => isStepValid(k, state)).every(Boolean)}
                  onClick={() => goTo(i)}
                  aria-current={i === step ? "step" : undefined}
                  className={cn(
                    "w-full truncate text-left text-xs transition disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer",
                    i === step ? "font-semibold text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {String(i + 1).padStart(2, "0")} · {["Тип", "Площадь", "Спальни", "Технология", "Комплектация", "Опции", "Сроки"][i]}
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      {saved && phase === "steps" && (
        <div className="mb-8 flex flex-col gap-3 rounded-2xl border border-accent/30 bg-accent/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">У вас есть незавершённый расчёт (шаг {saved.step + 1} из {TOTAL}). Продолжить с того же места?</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={restore}>Продолжить</Button>
            <Button size="sm" variant="ghost" onClick={() => setSavedDismissed(true)}>Начать новый</Button>
          </div>
        </div>
      )}

      <div className="grid gap-10 lg:grid-cols-[1fr_22rem] xl:gap-14">
        <div className="min-w-0">
          {phase === "result" && serverEstimate ? (
            <CalculatorResult
              estimate={serverEstimate}
              state={state}
              calculationId={calculationId}
              projectSlug={project?.slug}
              onEdit={() => {
                setPhase("steps");
                goTo(0);
              }}
              onSubmitted={() => {
                try {
                  window.sessionStorage.removeItem(STORAGE_KEY);
                } catch {
                  // Нечего очищать.
                }
              }}
            />
          ) : (
            <>
              <AnimatePresence mode="wait" custom={direction} initial={false}>
                <motion.section
                  key={step}
                  custom={direction}
                  initial={reduce ? false : { opacity: 0, x: direction * 40 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={reduce ? undefined : { opacity: 0, x: direction * -40 }}
                  transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                  aria-labelledby="step-title"
                >
                  <h2 id="step-title" className="text-3xl font-semibold tracking-tight sm:text-4xl">{STEP_TITLES[step]}</h2>
                  <p className="mt-3 max-w-2xl text-muted-foreground">{STEP_HINTS[step]}</p>
                  <div className="mt-8">
                    <Step state={state} config={config} update={update} />
                  </div>
                </motion.section>
              </AnimatePresence>

              <div className="mt-10 hidden items-center justify-between border-t border-border pt-6 lg:flex">
                <Button variant="ghost" size="lg" onClick={() => goTo(step - 1)} disabled={step === 0}>
                  <ArrowLeft />
                  Назад
                </Button>
                <div className="flex items-center gap-4">
                  {!valid && <span className="text-sm text-muted-foreground">Выберите вариант, чтобы продолжить</span>}
                  {nextButton}
                </div>
              </div>
            </>
          )}
        </div>

        <DesktopSummary state={state} config={config} estimate={phase === "result" ? serverEstimate : liveEstimate} project={project} />
      </div>

      {phase === "steps" && (
        <MobileSummaryBar
          state={state}
          config={config}
          estimate={liveEstimate}
          project={project}
          action={
            <div className="flex items-center gap-2">
              {step > 0 && (
                <Button variant="outline" size="icon" onClick={() => goTo(step - 1)} aria-label="Назад">
                  <ArrowLeft />
                </Button>
              )}
              {nextButton}
            </div>
          }
        />
      )}
    </div>
  );
}
