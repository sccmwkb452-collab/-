"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Point {
  date: string;
  leads: number;
  calculations: number;
}

export function LeadsChart({ data }: { data: Point[] }) {
  return (
    <div className="h-72 w-full" role="img" aria-label="График заявок и расчётов за 14 дней">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="gLeads" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand-accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--brand-accent)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gCalc" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#171717" stopOpacity={0.12} />
              <stop offset="100%" stopColor="#171717" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#ECE7DD" />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#8A8173" }} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#8A8173" }} />
          <Tooltip
            contentStyle={{ borderRadius: 12, border: "1px solid #E3DDD1", boxShadow: "0 8px 24px rgba(0,0,0,0.08)", fontSize: 13 }}
            formatter={(value, name) => [value, name === "leads" ? "Заявки" : "Расчёты"]}
          />
          <Area type="monotone" dataKey="calculations" stroke="#171717" strokeWidth={1.5} fill="url(#gCalc)" />
          <Area type="monotone" dataKey="leads" stroke="var(--brand-accent)" strokeWidth={2.5} fill="url(#gLeads)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
