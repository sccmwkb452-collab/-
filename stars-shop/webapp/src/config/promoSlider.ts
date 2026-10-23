/* Promo slider at the top of the home page: texts, pictures, actions and timing.
 * The component (components/home/PromoSlider.tsx) only renders what is here.
 *
 * Pictures live in src/assets/promo/. To change one, replace the file under the
 * same name (keep a similar aspect ratio) or import another file below.
 * `?no-inline` keeps every picture a separate cacheable file, never base64 in the bundle. */

import slide1Art from "../assets/promo/slide-1-art.webp?no-inline";
import slide1Icon from "../assets/promo/slide-1-icon.webp?no-inline";
import slide2Art from "../assets/promo/slide-2-art.webp?no-inline";
import slide2Icon from "../assets/promo/slide-2-icon.webp?no-inline";
import slide3Art from "../assets/promo/slide-3-art.webp?no-inline";
import slide3Icon from "../assets/promo/slide-3-icon.webp?no-inline";
import slide4Art from "../assets/promo/slide-4-art.webp?no-inline";
import slide4Icon from "../assets/promo/slide-4-icon.webp?no-inline";

export type PromoAction =
  /** Smooth scroll to a block of the home page by its id, e.g. "catalog". */
  | { type: "scroll"; target: string }
  /** Mini App route, e.g. "/orders" or "/profile#bonuses". */
  | { type: "route"; to: string }
  /** External https:// or https://t.me/ link; inside Telegram it opens through the Telegram API. */
  | { type: "external"; url: string };

export interface PromoSlide {
  /** Unique slide key. */
  id: string;
  /** One or two lines, shown in capitals: the first is white, the second gets the blue gradient. */
  title: readonly [string] | readonly [string, string];
  /** "•" is drawn as a cyan dot. */
  subtitle: string;
  /** Button label; the arrow is added automatically. */
  cta: string;
  /** Where the banner and its button lead. null — no destination yet:
   * the button is hidden and the banner is not clickable. */
  action: PromoAction | null;
  /** Right-hand picture (decorative). `focus` is the horizontal point, 0–100 %,
   * kept in view when a narrow screen shows only part of the picture. */
  art: { src: string; focus: number };
  /** Left-hand picture, wide screens only. "badge" — a round emblem,
   * "figure" — a character standing on the bottom edge of the banner. */
  icon?: { src: string; kind: "badge" | "figure" };
}

export interface PromoSliderConfig {
  /** Auto-advance interval, ms. */
  intervalMs: number;
  /** false — slides change only by the dots and swipes. */
  autoplay: boolean;
  slides: PromoSlide[];
}

export const promoSlider: PromoSliderConfig = {
  intervalMs: 3200,
  autoplay: true,
  slides: [
    {
      id: "stars",
      title: ["Продажа звёзд", "премиум"],
      subtitle: "Быстро • Надёжно • Выгодно",
      cta: "Купить",
      action: { type: "scroll", target: "catalog" },
      art: { src: slide1Art, focus: 15 },
      icon: { src: slide1Icon, kind: "badge" },
    },
    {
      id: "discounts",
      title: ["Скидки", "на звёзды!"],
      subtitle: "Пополняй сейчас — получай больше!",
      cta: "Купить",
      action: { type: "scroll", target: "catalog" },
      art: { src: slide2Art, focus: 34 },
      icon: { src: slide2Icon, kind: "badge" },
    },
    {
      id: "lucky-buy",
      title: ["Lucky Buy"],
      subtitle: "Испытай удачу — лови бонус!",
      cta: "Попробовать",
      // The shop has no raffles; the existing bonus section of the profile is the closest page.
      action: { type: "route", to: "/profile#bonuses" },
      art: { src: slide3Art, focus: 55 },
      icon: { src: slide3Icon, kind: "figure" },
    },
    {
      id: "premium",
      title: ["Премиум", "для тебя"],
      subtitle: "Больше возможностей каждый день",
      cta: "Подключить",
      // The shop has no premium page yet. When there is one, set it here, e.g.
      // action: { type: "route", to: "/<page>" } or { type: "external", url: "https://…" }
      action: null,
      art: { src: slide4Art, focus: 45 },
      icon: { src: slide4Icon, kind: "badge" },
    },
  ],
};
