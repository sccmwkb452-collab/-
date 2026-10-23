import { AnimatePresence, motion, useInView, useIsPresent, usePageInView, useReducedMotion, type Variants } from "motion/react";
import { ArrowRight, Pause, Play } from "lucide-react";
import { Fragment, useCallback, useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { useNavigate } from "react-router";
import { promoSlider, type PromoAction, type PromoSlide } from "../../config/promoSlider";
import { haptic, openExternal } from "../../lib/telegram";
import { cn } from "../ui/cn";

/* Palette of the banners: deep navy #050B1F, blue #0866FF, cyan #00CFFF.
 * Fixed on purpose: the banners stay dark and blue in every theme. */

const EASE = [0.22, 1, 0.36, 1] as const;
const SWIPE_PX = 40;

// Fade with a light shift in the direction of travel (`custom` = signed shift, 0 with reduced motion).
const slideVariants: Variants = {
  enter: (shift: number) => ({ opacity: 0, x: shift }),
  center: { opacity: 1, x: 0, transition: { duration: 0.6, ease: EASE } },
  exit: (shift: number) => ({ opacity: 0, x: -shift, transition: { duration: 0.42, ease: EASE } }),
};

const artVariants: Variants = {
  enter: { scale: 0.94 },
  center: { scale: 1, transition: { duration: 0.9, ease: EASE } },
  exit: { scale: 1.03, transition: { duration: 0.42, ease: EASE } },
};

const FRAME_STYLE: CSSProperties = {
  background: [
    "radial-gradient(58% 130% at 84% 50%, rgba(8,102,255,0.55) 0%, rgba(8,102,255,0) 70%)",
    "radial-gradient(34% 90% at 9% 50%, rgba(8,102,255,0.22) 0%, rgba(8,102,255,0) 72%)",
    "linear-gradient(100deg, #050B1F 0%, #061536 36%, #082a7c 68%, #0a43c4 100%)",
  ].join(", "),
  boxShadow: "0 0 0 1px rgba(0,207,255,0.08), 0 14px 38px -16px rgba(8,102,255,0.8)",
};

const SPARKLES = [
  { left: "6%", top: "14%", size: 7, delay: "0s" },
  { left: "41%", top: "10%", size: 6, delay: "1.2s" },
  { left: "35%", top: "82%", size: 8, delay: "2.1s" },
  { left: "57%", top: "26%", size: 5, delay: "0.6s" },
];

function Sparkle({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="drop-shadow-[0_0_4px_rgba(0,207,255,0.9)]">
      <path d="M12 0c.6 7.4 4.6 11.4 12 12-7.4.6-11.4 4.6-12 12-.6-7.4-4.6-11.4-12-12 7.4-.6 11.4-4.6 12-12Z" fill="#E6F6FF" />
    </svg>
  );
}

function isFocusVisible(el: EventTarget): boolean {
  try {
    return el instanceof Element && el.matches(":focus-visible");
  } catch {
    return false; // very old WebViews do not know the selector
  }
}

function Subtitle({ text }: { text: string }) {
  // The spaces around "•" stay in the text, so the line can still wrap there.
  return text.split("•").map((part, i) => (
    <Fragment key={i}>
      {i > 0 && (
        <span className="mx-0.5 text-[#00CFFF]" aria-hidden>
          •
        </span>
      )}
      {part}
    </Fragment>
  ));
}

function SlideIcon({ icon }: { icon: NonNullable<PromoSlide["icon"]> }) {
  const figure = icon.kind === "figure";
  return (
    <div className={cn("pointer-events-none hidden shrink-0 @3xl:flex", figure ? "items-end" : "items-center")} aria-hidden>
      <img
        src={icon.src}
        alt=""
        draggable={false}
        loading="lazy"
        decoding="async"
        className={cn(
          "w-auto max-w-none",
          figure
            ? "h-[calc(var(--promo-h)*0.84)] [mask-image:radial-gradient(ellipse_50%_64%_at_50%_58%,#000_66%,transparent_100%)]"
            : "h-[calc(var(--promo-h)*0.62)] [mask-image:radial-gradient(closest-side,#000_86%,transparent_100%)]",
        )}
      />
      <span className="ml-4 mr-6 h-[58%] w-px self-center bg-gradient-to-b from-transparent via-[#00CFFF]/70 to-transparent" />
    </div>
  );
}

interface SlideProps {
  slide: PromoSlide;
  shift: number;
  label: string;
  titleId: string;
  onAction: (action: PromoAction) => void;
}

function Slide({ slide, shift, label, titleId, onAction }: SlideProps) {
  // A leaving slide stays in the DOM while it fades out: keep it under the new one and out of reach.
  const present = useIsPresent();
  const [first, second] = slide.title;
  const action = slide.action;
  return (
    <motion.div
      custom={shift}
      variants={slideVariants}
      initial="enter"
      animate="center"
      exit="exit"
      inert={!present}
      className={cn("relative col-start-1 row-start-1", present ? "z-[1]" : "pointer-events-none")}
      role="group"
      aria-roledescription="слайд"
      aria-label={label}
    >
      <motion.div
        variants={shift ? artVariants : undefined}
        className="pointer-events-none absolute inset-y-0 right-0 w-[56%] [mask-image:linear-gradient(to_right,transparent_0%,#000_30%)] @xl:w-[54%] @3xl:w-[48%]"
        style={{ transformOrigin: `${slide.art.focus}% 50%` }}
      >
        <img
          src={slide.art.src}
          alt=""
          draggable={false}
          decoding="async"
          className="size-full object-cover"
          style={{ objectPosition: `${slide.art.focus}% 50%` }}
        />
      </motion.div>

      <div className="relative z-10 flex min-h-(--promo-h) pl-4 pr-[40%] @xl:pl-6 @xl:pr-[46%] @3xl:pl-7 @3xl:pr-[40%]">
        {slide.icon && <SlideIcon icon={slide.icon} />}
        <div className="flex min-w-0 flex-col items-start justify-center py-3 @xl:py-5">
          <div className="min-w-0">
            <p
              id={titleId}
              className="font-display text-[clamp(15px,calc(1px+5.2cqw),20px)] font-extrabold uppercase leading-[1.04] tracking-[-0.015em] drop-shadow-[0_2px_14px_rgba(0,140,255,0.45)] @xl:text-[clamp(22px,calc(4.6cqw-2px),30px)] @3xl:text-[clamp(22px,calc(4.5cqw-12px),30px)]"
            >
              <span className="block bg-[linear-gradient(180deg,#FFFFFF_35%,#CFE8FF_100%)] bg-clip-text text-transparent">{first}</span>
              {second && <span className="block bg-[linear-gradient(180deg,#A6EBFF_0%,#3FA9FF_55%,#1F7BFF_100%)] bg-clip-text text-transparent">{second}</span>}
            </p>
            <p className="mt-1.5 text-[clamp(11.5px,calc(4px+2.1cqw),13px)] font-medium leading-snug text-[#CFE2FF] [text-shadow:0_1px_10px_rgba(5,11,31,0.85)] @xl:mt-2 @xl:text-[clamp(13.5px,calc(6px+1.2cqw),16px)]">
              <Subtitle text={slide.subtitle} />
            </p>
          </div>
          {action && (
            // Stretched button: its ::after covers the banner, so the whole banner is one click target.
            <button
              type="button"
              onClick={() => onAction(action)}
              aria-describedby={titleId}
              className="group/cta mt-2.5 shrink-0 cursor-pointer rounded-full after:absolute after:inset-0 after:content-[''] @xl:mt-4"
            >
              <span className="relative inline-flex h-8 items-center gap-1.5 overflow-hidden rounded-full border border-[#9FD8FF]/55 bg-[linear-gradient(180deg,#2D8DFF_0%,#0866FF_58%,#0657DE_100%)] px-3.5 text-[12.5px] font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_8px_22px_-8px_rgba(8,102,255,0.9),0_0_18px_-4px_rgba(0,207,255,0.55)] transition-[transform,filter] duration-200 ease-out-soft group-hover/cta:brightness-110 group-active/cta:scale-[0.97] @xl:h-10 @xl:px-5 @xl:text-[14px]">
                <span className="pointer-events-none absolute inset-y-0 left-0 w-1/3 animate-[sheen_3.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/30 to-transparent" aria-hidden />
                {slide.cta}
                <ArrowRight className="size-3.5 @xl:size-4" aria-hidden />
              </span>
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** Auto-playing promo banners at the top of the home page (config: config/promoSlider.ts). */
export function PromoSlider() {
  const { slides, intervalMs, autoplay } = promoSlider;
  const count = slides.length;
  const navigate = useNavigate();
  const reducedMotion = useReducedMotion();
  const baseId = useId();

  const [{ index, dir }, setPosition] = useState({ index: 0, dir: 1 });
  const [userPaused, setUserPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [keyboardFocus, setKeyboardFocus] = useState(false);
  const [dragging, setDragging] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const inView = useInView(rootRef, { amount: 0.25, initial: true });
  const pageVisible = usePageInView();

  const rotating = autoplay && count > 1 && !userPaused;
  const paused = !rotating || hovered || keyboardFocus || dragging || !inView || !pageVisible;

  const go = useCallback((delta: 1 | -1) => setPosition((p) => ({ index: (p.index + delta + count) % count, dir: delta })), [count]);
  const goTo = useCallback((i: number) => setPosition((p) => (i === p.index ? p : { index: i, dir: i > p.index ? 1 : -1 })), []);

  // Autoplay: one timeout per slide. A pause keeps the time already spent, so the
  // progress bar (a CSS animation paused in sync) and the switch stay aligned.
  const elapsed = useRef(0);
  useEffect(() => {
    elapsed.current = 0;
  }, [index]);
  useEffect(() => {
    if (paused) return;
    const started = performance.now();
    const timer = window.setTimeout(() => go(1), Math.max(0, intervalMs - elapsed.current));
    return () => {
      window.clearTimeout(timer);
      elapsed.current += performance.now() - started;
    };
  }, [index, paused, intervalMs, go]);

  // Slides mount one at a time: warm the cache so the next picture never pops in.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 800px)").matches; // left icons are shown only there
    for (const s of slides) {
      for (const src of [s.art.src, wide ? s.icon?.src : undefined]) {
        if (src) new Image().src = src;
      }
    }
  }, [slides]);

  const runAction = useCallback(
    (action: PromoAction) => {
      haptic.tap("medium");
      if (action.type === "scroll") document.getElementById(action.target)?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
      else if (action.type === "route") navigate(action.to);
      else openExternal(action.url);
    },
    [navigate, reducedMotion],
  );

  // Swipe: horizontal drags switch slides; vertical ones stay native page scroll (touch-action: pan-y).
  const drag = useRef<{ id: number; x: number; y: number; swiping: boolean } | null>(null);
  const suppressClick = useRef(false);
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    suppressClick.current = false;
    if (count < 2 || (e.pointerType === "mouse" && e.button !== 0)) return;
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, swiping: false };
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId || d.swiping) return;
    const dx = e.clientX - d.x;
    if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(e.clientY - d.y) * 1.2) {
      d.swiping = true;
      e.currentTarget.setPointerCapture?.(e.pointerId);
    }
  };
  const endDrag = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (!d.swiping) return;
    suppressClick.current = true; // the click that ends a swipe must not open the banner
    const dx = e.clientX - d.x;
    if (!cancelled && Math.abs(dx) >= SWIPE_PX) {
      haptic.select();
      go(dx < 0 ? 1 : -1);
    }
  };

  const dotRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const onDotsKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: count - 1 };
    const next = keys[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const target = (next + count) % count;
    goTo(target);
    dotRefs.current[target]?.focus();
  };

  if (!count) return null;
  const slide = slides[index];
  const shift = reducedMotion ? 0 : dir * 40;

  return (
    <section
      ref={rootRef}
      aria-roledescription="карусель"
      aria-label="Акции магазина"
      className="@container"
      style={{ "--promo-h": "max(160px, calc(126px + 8.6cqw))" } as CSSProperties}
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") setHovered(true);
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === "mouse") setHovered(false);
      }}
      onFocus={(e) => setKeyboardFocus(isFocusVisible(e.target))}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setKeyboardFocus(false);
      }}
    >
      <div
        className="relative isolate grid min-h-(--promo-h) select-none overflow-hidden rounded-[22px] [touch-action:pan-y] @3xl:rounded-[26px]"
        style={FRAME_STYLE}
        aria-live={rotating ? "off" : "polite"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => endDrag(e, false)}
        onPointerCancel={(e) => endDrag(e, true)}
        onPointerLeave={(e) => {
          if (drag.current && !drag.current.swiping) endDrag(e, true);
        }}
        onClickCapture={(e) => {
          if (!suppressClick.current) return;
          suppressClick.current = false;
          e.preventDefault();
          e.stopPropagation();
        }}
      >
        {SPARKLES.map((s) => (
          <span
            key={s.left + s.top}
            className="pointer-events-none absolute animate-[twinkle_3.2s_ease-in-out_infinite]"
            style={{ left: s.left, top: s.top, animationDelay: s.delay }}
            aria-hidden
          >
            <Sparkle size={s.size} />
          </span>
        ))}

        <AnimatePresence initial={false} custom={shift}>
          <Slide key={slide.id} slide={slide} shift={shift} label={`${index + 1} из ${count}`} titleId={`${baseId}-${slide.id}`} onAction={runAction} />
        </AnimatePresence>

        {/* glowing frame drawn above the slides */}
        <span className="pointer-events-none absolute inset-0 z-20 rounded-[inherit] border border-[#5CC8FF]/45 shadow-[inset_0_0_20px_rgba(0,207,255,0.16),inset_0_1px_0_rgba(166,235,255,0.35)]" aria-hidden />
      </div>

      {count > 1 && (
        <div className="mt-2 flex items-center justify-center gap-1">
          <div className="flex items-center" onKeyDown={onDotsKeyDown}>
            {slides.map((s, i) => {
              const active = i === index;
              return (
                <button
                  key={s.id}
                  ref={(el) => {
                    dotRefs.current[i] = el;
                  }}
                  type="button"
                  onClick={() => {
                    haptic.select();
                    goTo(i);
                  }}
                  aria-label={`Слайд ${i + 1} из ${count}: ${s.title.join(" ")}`}
                  aria-current={active || undefined}
                  className="group/dot flex h-6 cursor-pointer items-center rounded-full px-1"
                >
                  <span
                    className={cn(
                      "relative block h-1.5 overflow-hidden rounded-full transition-[width,background-color] duration-300 ease-out-soft",
                      active ? "w-7 bg-[#0866FF]/25" : "w-1.5 bg-[#4F8BFF]/40 group-hover/dot:bg-[#4F8BFF]/70",
                    )}
                  >
                    {active && (
                      <span
                        key={index}
                        className="absolute inset-0 origin-left rounded-full bg-gradient-to-r from-[#0866FF] to-[#00CFFF]"
                        style={autoplay ? { animation: `promo-progress ${intervalMs}ms linear forwards`, animationPlayState: paused ? "paused" : "running" } : undefined}
                      />
                    )}
                  </span>
                </button>
              );
            })}
          </div>
          {autoplay && (
            <button
              type="button"
              onClick={() => setUserPaused((v) => !v)}
              aria-label={userPaused ? "Включить автопрокрутку" : "Остановить автопрокрутку"}
              className="flex size-6 cursor-pointer items-center justify-center rounded-full text-text-3 transition-colors hover:text-[#0866FF]"
            >
              {userPaused ? <Play className="size-3 fill-current" aria-hidden /> : <Pause className="size-3 fill-current" aria-hidden />}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
