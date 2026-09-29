/**
 * Генератор демонстрационных визуализаций и планировок.
 * Рисует архитектурные фасады и поэтажные планы в SVG и конвертирует их в WebP.
 *
 * Запуск: npm run images:generate
 * Результат: public/demo/**
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";
import { houses, type FloorPlan, type HouseSpec, type Material, type Volume, type Win } from "./demo-houses";

type Mood = "day" | "dusk" | "overcast";

const OUT_DIR = path.join(process.cwd(), "public", "demo");
const W = 1600;
const H = 1000;
const GROUND = 770;

function rng(seedText: string) {
  let seed = 0;
  for (const ch of seedText) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

const palette = {
  day: {
    sky: ["#BFCBCF", "#E4E4DC", "#F3EEE3"],
    far: "#A7AEA3",
    near: "#7D8778",
    ground: ["#8C937A", "#666E58"],
    paving: "#D6CFC0",
    tree: "#5F6A51",
    treeDark: "#4C5642",
    light: 0.0,
  },
  dusk: {
    sky: ["#1D222D", "#48475A", "#C8946A"],
    far: "#2E3239",
    near: "#1F2327",
    ground: ["#2A2E29", "#161816"],
    paving: "#4B4640",
    tree: "#1A1D1B",
    treeDark: "#121412",
    light: 0.42,
  },
  overcast: {
    sky: ["#B9BDBC", "#D8D6CF", "#EAE7DF"],
    far: "#A2A7A0",
    near: "#848C82",
    ground: ["#868B78", "#666B5B"],
    paving: "#CFC9BC",
    tree: "#65705B",
    treeDark: "#535D4A",
    light: 0.12,
  },
} as const;

const materials: Record<Material, { fill: string; line: string; step: number; dir: "v" | "h" }> = {
  dark: { fill: "#2B2A28", line: "#383633", step: 0.22, dir: "v" },
  wood: { fill: "#9A734E", line: "#80603F", step: 0.16, dir: "v" },
  plaster: { fill: "#ECE8DF", line: "#ECE8DF", step: 0, dir: "h" },
  stone: { fill: "#C4BCAD", line: "#AFA697", step: 0.32, dir: "h" },
  brick: { fill: "#6E5448", line: "#5E473C", step: 0.13, dir: "h" },
  graphite: { fill: "#3A3B3C", line: "#444546", step: 0.6, dir: "h" },
};

function houseBounds(h: HouseSpec) {
  let minX = Infinity;
  let maxX = -Infinity;
  let maxY = 0;
  for (const v of h.volumes) {
    minX = Math.min(minX, v.x);
    maxX = Math.max(maxX, v.x + v.w);
    maxY = Math.max(maxY, v.h + (v.roof === "flat" ? 0.4 : v.roofH ?? 0));
  }
  for (const d of h.decks ?? []) {
    minX = Math.min(minX, d.x);
    maxX = Math.max(maxX, d.x + d.w);
  }
  return { minX, maxX, maxY };
}

function wallPoints(v: Volume): [number, number][] {
  const r = v.roofH ?? 0;
  switch (v.roof) {
    case "gable":
      return [[v.x, 0], [v.x, v.h], [v.x + v.w / 2, v.h + r], [v.x + v.w, v.h], [v.x + v.w, 0]];
    case "shed-r":
      return [[v.x, 0], [v.x, v.h], [v.x + v.w, v.h + r], [v.x + v.w, 0]];
    case "shed-l":
      return [[v.x, 0], [v.x, v.h + r], [v.x + v.w, v.h], [v.x + v.w, 0]];
    default:
      return [[v.x, 0], [v.x, v.h], [v.x + v.w, v.h], [v.x + v.w, 0]];
  }
}

function renderHouseScene(house: HouseSpec, mood: Mood, variant = 0) {
  const p = palette[mood];
  const rand = rng(`${house.slug}-${variant}`);
  const b = houseBounds(house);
  const widthM = b.maxX - b.minX;
  const S = Math.min((W * 0.66) / widthM, 430 / b.maxY);
  const ox = (W - widthM * S) / 2 - b.minX * S + (variant === 1 ? -60 : variant === 2 ? 70 : 0);
  const X = (m: number) => +(ox + m * S).toFixed(1);
  const Y = (m: number) => +(GROUND - m * S).toFixed(1);
  const pts = (list: [number, number][]) => list.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ");

  const defs: string[] = [];
  const body: string[] = [];

  defs.push(`
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${p.sky[0]}"/><stop offset="0.6" stop-color="${p.sky[1]}"/><stop offset="1" stop-color="${p.sky[2]}"/>
    </linearGradient>
    <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${p.ground[0]}"/><stop offset="1" stop-color="${p.ground[1]}"/>
    </linearGradient>
    <linearGradient id="glassDay" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8E9A9E"/><stop offset="0.55" stop-color="#5E696D"/><stop offset="1" stop-color="#3E4649"/>
    </linearGradient>
    <linearGradient id="glassDusk" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F6D29A"/><stop offset="0.7" stop-color="#E3A461"/><stop offset="1" stop-color="#B9773E"/>
    </linearGradient>
    <linearGradient id="shadeDown" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#000" stop-opacity="0.32"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="sideLight" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity="0.10"/><stop offset="1" stop-color="#000" stop-opacity="0.10"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#F4C27E" stop-opacity="0.55"/><stop offset="1" stop-color="#F4C27E" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="sun" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.75"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="horizonGlow" cx="0.5" cy="1" r="0.8">
      <stop offset="0" stop-color="#F2B77A" stop-opacity="0.55"/><stop offset="1" stop-color="#F2B77A" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="vignette" cx="0.5" cy="0.5" r="0.75">
      <stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="${mood === "dusk" ? 0.45 : 0.22}"/>
    </radialGradient>
    <filter id="blur8"><feGaussianBlur stdDeviation="8"/></filter>
    <filter id="blur20"><feGaussianBlur stdDeviation="20"/></filter>
  `);

  body.push(`<rect width="${W}" height="${H}" fill="url(#sky)"/>`);
  if (mood === "day") body.push(`<circle cx="${1180 + variant * 60}" cy="190" r="260" fill="url(#sun)"/>`);
  if (mood === "dusk") body.push(`<rect x="0" y="${GROUND - 420}" width="${W}" height="420" fill="url(#horizonGlow)"/>`);

  const forest = (color: string, baseY: number, minH: number, maxH: number, count: number, opacity: number) => {
    const shapes: string[] = [];
    for (let i = 0; i < count; i++) {
      const x = (i / count) * W + rand() * 40 - 20;
      const h = minH + rand() * (maxH - minH);
      const w = h * (0.28 + rand() * 0.1);
      const base = baseY + rand() * 8;
      shapes.push(
        `<polygon points="${x - w / 2},${base} ${x},${base - h} ${x + w / 2},${base}"/>`,
        `<polygon points="${x - w * 0.38},${base - h * 0.35} ${x},${base - h * 1.05} ${x + w * 0.38},${base - h * 0.35}"/>`,
      );
    }
    return `<g fill="${color}" opacity="${opacity}">${shapes.join("")}</g>`;
  };
  body.push(forest(p.far, GROUND - 6, 70, 150, 70, 0.7));
  body.push(forest(p.near, GROUND + 2, 110, 230, 34, 0.9));

  body.push(`<rect x="0" y="${GROUND}" width="${W}" height="${H - GROUND}" fill="url(#ground)"/>`);
  body.push(`<rect x="${X(b.minX - 1.2)}" y="${GROUND - 2}" width="${(widthM + 2.4) * S}" height="${0.55 * S}" fill="${p.paving}"/>`);
  body.push(`<rect x="${X(b.minX - 0.6)}" y="${GROUND - 8}" width="${(widthM + 1.2) * S}" height="26" fill="#000" opacity="0.25" filter="url(#blur8)"/>`);

  const litWindows: Win[] = [];
  const litVolumes: Volume[] = [];
  const ordered = [...house.volumes].sort((a, c) => Number(Boolean(c.back)) - Number(Boolean(a.back)));

  ordered.forEach((v, vi) => {
    const m = materials[v.material];
    const clipId = `clip-${vi}`;
    const wall = wallPoints(v);
    defs.push(`<clipPath id="${clipId}"><polygon points="${pts(wall)}"/></clipPath>`);
    body.push(`<polygon points="${pts(wall)}" fill="${m.fill}"/>`);
    const lines: string[] = [];
    if (m.step > 0) {
      const top = v.h + (v.roofH ?? 0);
      if (m.dir === "v") {
        for (let x = v.x + m.step; x < v.x + v.w; x += m.step) lines.push(`M${X(x)} ${Y(0)}V${Y(top)}`);
      } else {
        for (let y = m.step; y < top; y += m.step) lines.push(`M${X(v.x)} ${Y(y)}H${X(v.x + v.w)}`);
      }
    }
    body.push(`<g clip-path="url(#${clipId})">`);
    if (lines.length) body.push(`<path d="${lines.join("")}" stroke="${m.line}" stroke-width="1.4" fill="none"/>`);
    body.push(`<rect x="${X(v.x)}" y="${Y(v.h + (v.roofH ?? 0))}" width="${v.w * S}" height="${(v.h + (v.roofH ?? 0)) * S}" fill="url(#sideLight)"/>`);
    if (v.roof === "flat") body.push(`<rect x="${X(v.x)}" y="${Y(v.h)}" width="${v.w * S}" height="${0.9 * S}" fill="url(#shadeDown)"/>`);
    if (v.back) body.push(`<polygon points="${pts(wall)}" fill="#000" opacity="0.08"/>`);
    if (p.light > 0) body.push(`<polygon points="${pts(wall)}" fill="#0B1020" opacity="${p.light}"/>`);
    body.push(`</g>`);

    if (v.roof === "flat") {
      body.push(`<rect x="${X(v.x - 0.35)}" y="${Y(v.h + 0.38)}" width="${(v.w + 0.7) * S}" height="${0.38 * S}" fill="#1C1C1C"/>`);
    } else {
      const r = v.roofH ?? 0;
      const ov = 0.35;
      let d = "";
      if (v.roof === "gable") {
        const slope = r / (v.w / 2);
        d = `M${X(v.x - ov)} ${Y(v.h - ov * slope)} L${X(v.x + v.w / 2)} ${Y(v.h + r + 0.12)} L${X(v.x + v.w + ov)} ${Y(v.h - ov * slope)}`;
      } else if (v.roof === "shed-r") {
        const slope = r / v.w;
        d = `M${X(v.x - ov)} ${Y(v.h - ov * slope)} L${X(v.x + v.w + ov)} ${Y(v.h + r + ov * slope)}`;
      } else {
        const slope = r / v.w;
        d = `M${X(v.x - ov)} ${Y(v.h + r + ov * slope)} L${X(v.x + v.w + ov)} ${Y(v.h - ov * slope)}`;
      }
      body.push(`<path d="${d}" stroke="#1E1E1E" stroke-width="${0.3 * S}" fill="none" stroke-linejoin="miter" stroke-linecap="butt"/>`);
    }
    body.push(`<rect x="${X(v.x)}" y="${Y(0.32)}" width="${v.w * S}" height="${0.32 * S}" fill="#35332F"/>`);

    for (const w of v.windows) {
      litWindows.push({ ...w, x: v.x + w.x });
      litVolumes.push(v);
    }
  });

  if (house.garageDoor) {
    const g = house.garageDoor;
    const panels: string[] = [];
    for (let y = 0.3; y < g.h; y += 0.3) panels.push(`M${X(g.x)} ${Y(y)}H${X(g.x + g.w)}`);
    body.push(`<rect x="${X(g.x)}" y="${Y(g.h)}" width="${g.w * S}" height="${g.h * S}" fill="${mood === "dusk" ? "#2A2A2A" : "#4A4A48"}"/>`);
    body.push(`<path d="${panels.join("")}" stroke="#2F2F2E" stroke-width="1.5"/>`);
    body.push(`<rect x="${X(g.x)}" y="${Y(g.h)}" width="${g.w * S}" height="${0.25 * S}" fill="url(#shadeDown)"/>`);
  }

  for (const w of litWindows) {
    const x = X(w.x);
    const y = Y(w.y + w.h);
    const ww = w.w * S;
    const wh = w.h * S;
    if (mood === "dusk") {
      body.push(`<ellipse cx="${x + ww / 2}" cy="${GROUND + 30}" rx="${ww * 0.9}" ry="${40 + ww * 0.1}" fill="url(#glow)"/>`);
      body.push(`<rect x="${x - 6}" y="${y - 6}" width="${ww + 12}" height="${wh + 12}" fill="#F3B46B" opacity="0.35" filter="url(#blur8)"/>`);
    }
    body.push(`<rect x="${x}" y="${y}" width="${ww}" height="${wh}" fill="url(#${mood === "dusk" ? "glassDusk" : "glassDay"})"/>`);
    if (mood !== "dusk") {
      body.push(`<polygon points="${x + ww * 0.2},${y} ${x + ww * 0.42},${y} ${x + ww * 0.22},${y + wh} ${x},${y + wh}" fill="#FFFFFF" opacity="0.14"/>`);
    } else {
      const lamps = Math.max(1, Math.round(w.w / 2.2));
      for (let i = 0; i < lamps; i++) {
        const lx = x + (ww / (lamps + 1)) * (i + 1);
        body.push(`<line x1="${lx}" y1="${y}" x2="${lx}" y2="${y + wh * 0.28}" stroke="#6B4A2A" stroke-width="1"/>`);
        body.push(`<circle cx="${lx}" cy="${y + wh * 0.3}" r="${Math.max(4, S * 0.12)}" fill="#FFF3D6"/>`);
      }
      body.push(`<rect x="${x}" y="${y + wh * 0.72}" width="${ww}" height="${wh * 0.28}" fill="#8B5A30" opacity="0.35"/>`);
    }
    const cols = w.cols ?? 1;
    const rows = w.rows ?? 1;
    const mull: string[] = [];
    for (let c = 1; c < cols; c++) mull.push(`M${x + (ww / cols) * c} ${y}V${y + wh}`);
    for (let r = 1; r < rows; r++) mull.push(`M${x} ${y + (wh / rows) * r}H${x + ww}`);
    if (mull.length) body.push(`<path d="${mull.join("")}" stroke="#1B1B1B" stroke-width="${Math.max(2.5, S * 0.07)}"/>`);
    body.push(`<rect x="${x}" y="${y}" width="${ww}" height="${wh}" fill="none" stroke="#1B1B1B" stroke-width="${Math.max(3, S * 0.09)}"/>`);
    if (w.y > 0.3) body.push(`<rect x="${x - 3}" y="${y + wh}" width="${ww + 6}" height="${Math.max(3, S * 0.07)}" fill="#1B1B1B"/>`);
  }

  for (const d of house.decks ?? []) {
    body.push(`<rect x="${X(d.x)}" y="${Y(0.45)}" width="${d.w * S}" height="${0.45 * S}" fill="${mood === "dusk" ? "#4A3526" : "#8A6848"}"/>`);
    body.push(`<rect x="${X(d.x)}" y="${Y(0.45)}" width="${d.w * S}" height="3" fill="${mood === "dusk" ? "#6A4C35" : "#B08A63"}"/>`);
    if (d.canopy) {
      const c = d.canopy;
      body.push(`<rect x="${X(d.x + 0.1)}" y="${Y(c.h)}" width="${0.16 * S}" height="${(c.h - 0.45) * S}" fill="#1E1E1E"/>`);
      body.push(`<rect x="${X(d.x + d.w - 0.26)}" y="${Y(c.h)}" width="${0.16 * S}" height="${(c.h - 0.45) * S}" fill="#1E1E1E"/>`);
      body.push(`<rect x="${X(d.x - 0.2)}" y="${Y(c.h + 0.26)}" width="${(d.w + 0.4) * S}" height="${0.26 * S}" fill="#1C1C1C"/>`);
      body.push(`<rect x="${X(d.x)}" y="${Y(c.h)}" width="${d.w * S}" height="${0.6 * S}" fill="url(#shadeDown)" opacity="0.6"/>`);
    }
  }

  const shrubs: string[] = [];
  for (let x = b.minX - 1; x < b.maxX + 1; x += 1.4 + rand() * 2.2) {
    const r = Math.min(30, (0.22 + rand() * 0.2) * S);
    shrubs.push(`<ellipse cx="${X(x)}" cy="${GROUND + 6}" rx="${r * 1.4}" ry="${r}"/>`);
  }
  body.push(`<g fill="${p.treeDark}" opacity="0.92">${shrubs.join("")}</g>`);

  const tree = (cx: number, base: number, scale: number, columnar: boolean) => {
    const trunk = `<rect x="${cx - 5 * scale}" y="${base - 150 * scale}" width="${10 * scale}" height="${150 * scale}" fill="#2A241E"/>`;
    if (columnar) {
      return `${trunk}<ellipse cx="${cx}" cy="${base - 260 * scale}" rx="${58 * scale}" ry="${210 * scale}" fill="${p.tree}"/>`;
    }
    const blobs = [
      [0, -300, 120], [-80, -240, 95], [85, -235, 100], [-30, -200, 90], [40, -370, 80],
    ].map(([dx, dy, r]) => `<circle cx="${cx + dx * scale}" cy="${base + dy * scale}" r="${r * scale}"/>`);
    return `${trunk}<g fill="${p.tree}">${blobs.join("")}</g><g fill="#000" opacity="0.12">${blobs.slice(1, 3).join("")}</g>`;
  };
  const leftX = 60 + rand() * 90;
  const rightX = W - 70 - rand() * 90;
  body.push(tree(leftX, H - 40, 1.1 + rand() * 0.3, variant % 2 === 1));
  body.push(tree(rightX, H - 20, 1.2 + rand() * 0.3, variant % 2 === 0));

  const grass: string[] = [];
  for (let i = 0; i < 90; i++) {
    const gx = rand() * W;
    const gy = GROUND + 60 + rand() * (H - GROUND - 60);
    grass.push(`M${gx.toFixed(1)} ${gy.toFixed(1)}h${(20 + rand() * 60).toFixed(1)}`);
  }
  body.push(`<path d="${grass.join("")}" stroke="#000" stroke-opacity="0.07" stroke-width="2"/>`);
  body.push(`<rect width="${W}" height="${H}" fill="url(#vignette)"/>`);

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs>${defs.join("")}</defs>${body.join("")}</svg>`;
}

function renderPlan(plan: FloorPlan, index: number) {
  const PW = 1600;
  const PH = 1100;
  const depth = plan.rows.reduce((s, r) => s + r.h, 0);
  const S = Math.min((PW - 300) / plan.width, (PH - 320) / depth);
  const ox = (PW - plan.width * S) / 2;
  const oy = 190 + (PH - 320 - depth * S) / 2;
  const font = "DejaVu Sans, Liberation Sans, sans-serif";
  const out: string[] = [];
  out.push(`<rect width="${PW}" height="${PH}" fill="#F7F6F2"/>`);
  const grid: string[] = [];
  for (let gx = 0; gx < PW; gx += 40) grid.push(`M${gx} 0V${PH}`);
  for (let gy = 0; gy < PH; gy += 40) grid.push(`M0 ${gy}H${PW}`);
  out.push(`<path d="${grid.join("")}" stroke="#E7E3DA" stroke-width="1"/>`);
  out.push(`<text x="80" y="110" font-family="${font}" font-size="44" font-weight="bold" fill="#171717">${plan.title}</text>`);
  out.push(`<text x="80" y="150" font-family="${font}" font-size="22" fill="#8A8173">Демонстрационная планировка · масштаб условный</text>`);

  let y = 0;
  plan.rows.forEach((row, ri) => {
    const total = row.rooms.reduce((s, r) => s + r.w, 0);
    const k = plan.width / total;
    let x = 0;
    row.rooms.forEach((room, ci) => {
      const rw = room.w * k;
      const rx = ox + x * S;
      const ry = oy + y * S;
      const fill = /Гостин|Кухня|Столов/.test(room.name) ? "#EFE7D8" : /Спальн/.test(room.name) ? "#F4EFE6" : /Санузел|Котельн|Постир/.test(room.name) ? "#E6E8E6" : "#FBFAF7";
      out.push(`<rect x="${rx}" y="${ry}" width="${rw * S}" height="${row.h * S}" fill="${fill}" stroke="#2A2A2A" stroke-width="5"/>`);
      const area = (rw * row.h).toFixed(1).replace(".", ",");
      const fs = Math.max(15, Math.min(26, rw * S * 0.085));
      out.push(`<text x="${rx + (rw * S) / 2}" y="${ry + (row.h * S) / 2 - 4}" text-anchor="middle" font-family="${font}" font-size="${fs}" fill="#202020">${room.name}</text>`);
      out.push(`<text x="${rx + (rw * S) / 2}" y="${ry + (row.h * S) / 2 + fs + 4}" text-anchor="middle" font-family="${font}" font-size="${fs * 0.85}" fill="#A47B45">${area} м²</text>`);
      const doorR = Math.min(0.9 * S, rw * S * 0.3, row.h * S * 0.3);
      if (ri > 0 || ci > 0) {
        const dx = rx + 18;
        const dy = ry;
        out.push(`<rect x="${dx}" y="${dy - 4}" width="${doorR}" height="8" fill="${fill}"/>`);
        out.push(`<path d="M${dx} ${dy} L${dx} ${dy + doorR} A${doorR} ${doorR} 0 0 0 ${dx + doorR} ${dy}" fill="none" stroke="#8A8173" stroke-width="1.6"/>`);
      }
      x += rw;
    });
    y += row.h;
  });
  out.push(`<rect x="${ox}" y="${oy}" width="${plan.width * S}" height="${depth * S}" fill="none" stroke="#171717" stroke-width="12"/>`);
  const dimY = oy + depth * S + 60;
  out.push(`<path d="M${ox} ${dimY}H${ox + plan.width * S}M${ox} ${dimY - 14}V${dimY + 14}M${ox + plan.width * S} ${dimY - 14}V${dimY + 14}" stroke="#171717" stroke-width="2"/>`);
  out.push(`<text x="${ox + (plan.width * S) / 2}" y="${dimY - 14}" text-anchor="middle" font-family="${font}" font-size="24" fill="#171717">${plan.width.toFixed(1).replace(".", ",")} м</text>`);
  const dimX = ox + plan.width * S + 60;
  out.push(`<path d="M${dimX} ${oy}V${oy + depth * S}M${dimX - 14} ${oy}H${dimX + 14}M${dimX - 14} ${oy + depth * S}H${dimX + 14}" stroke="#171717" stroke-width="2"/>`);
  out.push(`<text x="${dimX + 24}" y="${oy + (depth * S) / 2}" font-family="${font}" font-size="24" fill="#171717">${depth.toFixed(1).replace(".", ",")} м</text>`);
  out.push(`<text x="${PW - 80}" y="${PH - 50}" text-anchor="end" font-family="${font}" font-size="20" fill="#B5AC9C">Лист ${index + 1}</text>`);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${PW}" height="${PH}" viewBox="0 0 ${PW} ${PH}">${out.join("")}</svg>`;
}

async function toWebp(svg: string, file: string, opts: { width?: number; height?: number; crop?: { left: number; top: number; width: number; height: number } } = {}) {
  let img = sharp(Buffer.from(svg), { density: 72 });
  if (opts.crop) img = img.extract(opts.crop);
  if (opts.width) img = img.resize(opts.width, opts.height);
  await img.webp({ quality: 80 }).toFile(file);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  for (const house of houses) {
    const dir = path.join(OUT_DIR, "projects", house.slug);
    await mkdir(dir, { recursive: true });
    const coverMood: Mood = ["dom-nordik", "dom-grafit", "dom-rezidentsiya", "dom-kubik"].includes(house.slug) ? "dusk" : "day";
    const alt: Mood = coverMood === "dusk" ? "day" : "dusk";
    await toWebp(renderHouseScene(house, coverMood, 0), path.join(dir, "cover.webp"));
    await toWebp(renderHouseScene(house, alt, 1), path.join(dir, "gallery-1.webp"));
    await toWebp(renderHouseScene(house, "overcast", 2), path.join(dir, "gallery-2.webp"));
    await toWebp(renderHouseScene(house, alt, 0), path.join(dir, "gallery-3.webp"), {
      crop: { left: 400, top: 300, width: 800, height: 500 },
      width: 1600,
      height: 1000,
    });
    for (const [i, plan] of house.plans.entries()) {
      await toWebp(renderPlan(plan, i), path.join(dir, `plan-${i + 1}.webp`));
    }
    process.stdout.write(`✓ ${house.slug}\n`);
  }
  const flagship = houses.find((h) => h.slug === "dom-artem");
  const rez = houses.find((h) => h.slug === "dom-rezidentsiya");
  if (flagship && rez) {
    await toWebp(renderHouseScene(flagship, "dusk", 0), path.join(OUT_DIR, "hero.webp"), { width: 2400, height: 1500 });
    await toWebp(renderHouseScene(rez, "day", 2), path.join(OUT_DIR, "about.webp"));
    await toWebp(renderHouseScene(rez, "dusk", 1), path.join(OUT_DIR, "cta.webp"));
  }
  process.stdout.write("Готово\n");
}

main().catch((error: unknown) => {
  process.stderr.write(`${String(error)}\n`);
  process.exit(1);
});
