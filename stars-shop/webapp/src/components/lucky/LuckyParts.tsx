import type { LuckyCheck, LuckyDraw } from "@starshop/shared";
import { formatRoll, formatStars, TelegramStar, verifyLuckyDraw } from "@starshop/shared";
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { Check, ChevronDown, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { haptic } from "../../lib/telegram";
import { cn } from "../ui/cn";

/* Lucky Buy keeps the blue/cyan look of its promo banner in every theme:
 * deep navy #050B1F, blue #0866FF, cyan #00CFFF. */

export const LUCKY_FRAME: CSSProperties = {
  background: [
    "radial-gradient(70% 60% at 50% 0%, rgba(8,102,255,0.45) 0%, rgba(8,102,255,0) 70%)",
    "radial-gradient(50% 50% at 100% 100%, rgba(0,207,255,0.18) 0%, rgba(0,207,255,0) 70%)",
    "linear-gradient(160deg, #050B1F 0%, #061536 55%, #08245f 100%)",
  ].join(", "),
  boxShadow: "inset 0 0 0 1px rgba(92,200,255,0.35), inset 0 1px 0 rgba(166,235,255,0.25), 0 18px 44px -20px rgba(8,102,255,0.85)",
};

/** Ring gauge of the chance with the prize in the middle. */
export function ChanceDial({ chance, stars }: { chance: number; stars: number }) {
  const id = useId().replace(/:/g, "");
  const r = 84;
  const length = 2 * Math.PI * r;
  return (
    <div className="relative mx-auto size-[212px]">
      <div className="absolute inset-6 rounded-full bg-[#0866FF]/25 blur-2xl" aria-hidden />
      <svg viewBox="0 0 200 200" className="relative size-full -rotate-90" aria-hidden>
        <defs>
          <linearGradient id={`dial${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#00CFFF" />
            <stop offset="1" stopColor="#0866FF" />
          </linearGradient>
        </defs>
        <circle cx="100" cy="100" r={r} fill="none" stroke="rgba(120,170,255,0.16)" strokeWidth="12" />
        <motion.circle
          cx="100"
          cy="100"
          r={r}
          fill="none"
          stroke={`url(#dial${id})`}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={length}
          initial={false}
          animate={{ strokeDashoffset: length * (1 - chance / 100) }}
          transition={{ type: "spring", stiffness: 140, damping: 22 }}
          className="drop-shadow-[0_0_8px_rgba(0,207,255,0.7)]"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white">
        <span className="font-display text-[46px] font-extrabold leading-none tracking-[-0.04em] tabular">{chance}%</span>
        <span className="mt-1 text-[12.5px] font-medium text-[#9FC3FF]">шанс выиграть</span>
        <span className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-[13.5px] font-semibold ring-1 ring-inset ring-white/15 tabular">
          <TelegramStar size={16} />
          {formatStars(stars)}
        </span>
      </div>
    </div>
  );
}

/** Drawn number on a 0–100 scale; the cyan zone below the chance wins. */
export function DrawResult({ lucky, animated, onDone }: { lucky: LuckyDraw; animated: boolean; onDone?: () => void }) {
  const reduced = useReducedMotion();
  const chance = lucky.chance_bp / 100;
  const roll = (lucky.roll_bp ?? 0) / 100;
  const play = animated && !reduced;
  const position = useMotionValue(play ? 0 : roll);
  const left = useTransform(position, (v) => `${v}%`);
  const shown = useTransform(position, (v) => formatRoll(Math.round(v * 100)).replace(".", ","));
  const [settled, setSettled] = useState(!play);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });

  useEffect(() => {
    if (!play) return;
    // Sweep across the scale and settle on the drawn number.
    const controls = animate(position, [0, 100, 18, roll], { duration: 2.1, times: [0, 0.4, 0.72, 1], ease: [0.22, 1, 0.36, 1] });
    controls.then(() => {
      setSettled(true);
      if (lucky.won) haptic.success();
      else haptic.tap("light");
      done.current?.();
    });
    return () => controls.stop();
  }, [play, position, roll, lucky.won]);

  return (
    <div className="text-left">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#9FC3FF]">Выпало</div>
          <motion.div className="font-display text-[40px] font-extrabold leading-none tracking-[-0.04em] text-white tabular">{shown}</motion.div>
        </div>
        <div className="text-right text-[12.5px] leading-snug text-[#9FC3FF]">
          для выигрыша
          <br />
          нужно меньше <b className="text-white tabular">{lucky.chance}</b>
        </div>
      </div>
      <div className="relative mt-4 h-3 rounded-full bg-white/10" role="img" aria-label={`Выпало ${lucky.roll}, выигрыш при числе меньше ${lucky.chance}`}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-[#00CFFF] to-[#0866FF] shadow-[0_0_12px_rgba(0,207,255,0.6)]" style={{ width: `${chance}%` }} />
        <motion.div className="absolute top-1/2 -ml-[11px] -mt-[11px] size-[22px] rounded-full bg-white shadow-[0_0_0_4px_rgba(255,255,255,0.18),0_0_18px_rgba(0,207,255,0.9)]" style={{ left }} />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-[#7FA6E8] tabular" aria-hidden>
        {[0, 25, 50, 75, 100].map((n) => (
          <span key={n}>{n}</span>
        ))}
      </div>
      <motion.div
        initial={false}
        animate={{ opacity: settled ? 1 : 0, y: settled ? 0 : 6 }}
        transition={{ duration: 0.35 }}
        className={cn(
          "mt-4 flex items-center gap-2 rounded-2xl px-3.5 py-2.5 text-[14px] font-semibold ring-1 ring-inset",
          lucky.won ? "bg-[#00CFFF]/15 text-[#A6EBFF] ring-[#00CFFF]/40" : "bg-white/8 text-[#CFE2FF] ring-white/15",
        )}
        aria-live="polite"
      >
        {settled && (lucky.won ? <>🍀 Вы выиграли пакет!</> : <>🎲 В этот раз не повезло</>)}
      </motion.div>
    </div>
  );
}

function SeedRow({ label, value, muted }: { label: string; value: ReactNode; muted?: boolean }) {
  return (
    <div className="py-2.5">
      <div className="text-[12px] font-semibold text-text-3">{label}</div>
      <div className={cn("mt-0.5 break-all font-mono text-[12px] leading-relaxed", muted ? "text-text-3" : "text-text")}>{value}</div>
    </div>
  );
}

function CheckLine({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li className={cn("flex items-center gap-2 text-[13px] font-semibold", ok ? "text-success" : "text-danger")}>
      {ok ? <Check className="size-4" /> : <X className="size-4" />}
      {children}
    </li>
  );
}

/** Seeds of the draw and an in-browser check of the result. */
export function FairnessCard({ lucky }: { lucky: LuckyDraw }) {
  const [open, setOpen] = useState(false);
  const [check, setCheck] = useState<LuckyCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const drawn = lucky.server_seed !== null;

  const run = async () => {
    setChecking(true);
    try {
      setCheck(await verifyLuckyDraw(lucky));
    } finally {
      setChecking(false);
    }
  };

  return (
    <section className="rounded-xl3 bg-surface p-5 ring-1 ring-inset ring-line shadow-card">
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-[#00CFFF]" />
        <h3 className="text-[15px] font-semibold">Честный розыгрыш</h3>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-text-2">
        Результат зависит от сида сервера, зафиксированного до оплаты, и сида вашего устройства. После розыгрыша сид сервера раскрывается — результат можно проверить.
      </p>
      <div className="mt-2 divide-y divide-line">
        <SeedRow label="Хэш сида сервера (SHA-256), опубликован до оплаты" value={lucky.server_seed_hash} />
        <SeedRow label="Сид сервера" value={lucky.server_seed ?? "раскроется после розыгрыша"} muted={!drawn} />
        <SeedRow label="Ваш сид" value={lucky.client_seed ?? "задаётся при оплате"} muted={!lucky.client_seed} />
        <SeedRow label="Номер заказа (nonce)" value={lucky.nonce} />
      </div>
      {drawn && (
        <div className="mt-3">
          {check ? (
            <ul className="space-y-1.5 rounded-2xl bg-surface-2 p-3.5">
              <CheckLine ok={check.hashMatches}>Хэш сида сервера совпадает</CheckLine>
              <CheckLine ok={check.rollMatches}>Число {formatRoll(check.roll).replace(".", ",")} совпадает с результатом</CheckLine>
              <CheckLine ok={check.outcomeMatches}>Итог розыгрыша подтверждён</CheckLine>
            </ul>
          ) : (
            <button
              onClick={run}
              disabled={checking}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-2xl bg-surface-2 text-[14px] font-semibold ring-1 ring-inset ring-line transition hover:bg-surface-3 disabled:opacity-60"
            >
              <ShieldCheck className="size-4" /> Проверить на этом устройстве
            </button>
          )}
        </div>
      )}
      <button onClick={() => setOpen((v) => !v)} className="mt-3 flex items-center gap-1 text-[13px] font-semibold text-text-3 hover:text-text" aria-expanded={open}>
        Как проверить самостоятельно
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[12.5px] leading-relaxed text-text-2">
          <li>SHA-256 от сида сервера должен совпасть с хэшем, показанным до оплаты.</li>
          <li>
            Посчитайте HMAC-SHA256 с ключом «сид сервера» от строки <span className="font-mono">«ваш сид:номер заказа»</span>.
          </li>
          <li>Первые 16 hex-символов — число; умножьте его на 10000 и разделите на 2⁶⁴ (без остатка). Это число от 0 до 9999, на экране — от 0,00 до 99,99.</li>
          <li>Выигрыш — если число меньше шанса в сотых долях процента: при шансе 25% — меньше 2500.</li>
        </ol>
      )}
    </section>
  );
}
