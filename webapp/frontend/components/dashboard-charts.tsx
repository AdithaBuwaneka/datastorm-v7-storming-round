"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  LabelList,
  ReferenceLine,
  PieChart,
  Pie,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// Brand palette (kept in sync with the deck / paper).
const NAVY = "#0E3F6E";
const ACCENT = "#0E7CBE";
const TEAL = "#14B8A6";
const GREEN = "#10B981";
const AMBER = "#F59E0B";
const ORANGE = "#F97316";
const RED = "#EF4444";
const GREY = "#94A3B8";

function fmtInt(n: number) {
  return n.toLocaleString();
}

function ChartTooltip({
  active,
  payload,
  suffix,
}: {
  active?: boolean;
  payload?: any[];
  suffix?: string;
}) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0];
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-foreground">{p.payload.name}</div>
      <div className="text-muted-foreground">
        {fmtInt(p.value)}
        {suffix ? ` ${suffix}` : ""}
      </div>
    </div>
  );
}

/** Horizontal bar chart — outlets per province. */
export function ProvinceBarChart({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const colors = [NAVY, ACCENT, TEAL, GREY];
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart
        data={sorted}
        layout="vertical"
        margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tick={{ fontSize: 13, fill: "currentColor" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          content={<ChartTooltip suffix="outlets" />}
          cursor={{ fill: "rgba(14,124,190,0.06)" }}
        />
        <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={26}>
          {sorted.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} />
          ))}
          <LabelList
            dataKey="value"
            position="right"
            formatter={(v: number) => fmtInt(v)}
            style={{ fontSize: 12, fill: "currentColor", fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Donut — dormancy risk band distribution. */
export function DormancyDonut({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const colorByName: Record<string, string> = {
    Low: GREEN,
    Moderate: AMBER,
    High: ORANGE,
    Critical: RED,
  };
  const total = data.reduce((s, d) => s + d.value, 0);
  return (
    <div className="flex items-center gap-3">
      <div className="w-[44%] shrink-0">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={50}
              outerRadius={82}
              paddingAngle={2}
              stroke="none"
            >
              {data.map((d, i) => (
                <Cell key={i} fill={colorByName[d.name] ?? GREY} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip suffix="outlets" />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-1 flex-col gap-2.5 text-sm">
        {data.map((d) => (
          <li key={d.name} className="flex flex-col gap-0.5">
            <span className="flex items-center gap-2 font-medium">
              <span
                className="inline-block h-3 w-3 shrink-0 rounded-sm"
                style={{ background: colorByName[d.name] ?? GREY }}
              />
              {d.name}
            </span>
            <span className="whitespace-nowrap pl-5 text-muted-foreground">
              {fmtInt(d.value)}
              <span className="ml-1 text-xs">
                ({total ? Math.round((d.value / total) * 100) : 0}%)
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Diverging horizontal bar — distributor composite health (z-score).
 *  Positive scores extend RIGHT (green), negative extend LEFT (red) from a
 *  centre zero line. A custom label sits on the open side of each bar so it
 *  never collides with the axis names. */
function DivergingZLabel(props: any) {
  const { x, y, width, height, value } = props;
  const cy = y + height / 2 + 4;
  const text = value >= 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
  // Recharts reports x/width differently for negative bars, so derive the
  // true left/right edges and always place the label on the OUTER side.
  const left = Math.min(x, x + width);
  const right = Math.max(x, x + width);
  if (value >= 0) {
    return (
      <text
        x={right + 6}
        y={cy}
        textAnchor="start"
        fontSize={11}
        fontWeight={600}
        fill="currentColor"
      >
        {text}
      </text>
    );
  }
  return (
    <text
      x={left - 6}
      y={cy}
      textAnchor="end"
      fontSize={11}
      fontWeight={600}
      fill="currentColor"
    >
      {text}
    </text>
  );
}

export function ScorecardBar({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const maxAbs = Math.max(0.5, ...sorted.map((d) => Math.abs(d.value)));
  const bound = maxAbs * 1.35; // padding so labels have room on both ends
  const height = Math.max(200, sorted.length * 34);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={sorted}
        layout="vertical"
        margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
      >
        <XAxis type="number" domain={[-bound, bound]} hide />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tick={{ fontSize: 12, fill: "currentColor" }}
          axisLine={false}
          tickLine={false}
        />
        <ReferenceLine x={0} stroke="#CBD5E1" strokeWidth={1} />
        <Tooltip
          content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null;
            const z = payload[0].value as number;
            return (
              <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md">
                <div className="font-semibold">{payload[0].payload.name}</div>
                <div className="text-muted-foreground">
                  health-z {z >= 0 ? "+" : ""}
                  {z.toFixed(2)}
                </div>
              </div>
            );
          }}
          cursor={{ fill: "rgba(14,124,190,0.06)" }}
        />
        <Bar dataKey="value" radius={3} barSize={18}>
          {sorted.map((d, i) => (
            <Cell
              key={i}
              fill={
                d.value >= 0.5 ? GREEN : d.value >= -0.5 ? ACCENT : RED
              }
            />
          ))}
          <LabelList dataKey="value" content={<DivergingZLabel />} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Vertical bar — top outlets by 24-month NPV. */
export function CoolerNpvBar({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const fmtM = (n: number) => `${(n / 1_000_000).toFixed(1)}M`;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 18, right: 8, left: 8, bottom: 4 }}>
        <XAxis
          dataKey="name"
          tick={{ fontSize: 10, fill: "currentColor" }}
          axisLine={false}
          tickLine={false}
          angle={-35}
          textAnchor="end"
          height={56}
          interval={0}
        />
        <YAxis hide />
        <Tooltip
          content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null;
            const p = payload[0];
            return (
              <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md">
                <div className="font-semibold">{p.payload.name}</div>
                <div className="text-muted-foreground">
                  NPV LKR {fmtM(p.value)}
                </div>
              </div>
            );
          }}
          cursor={{ fill: "rgba(14,124,190,0.06)" }}
        />
        <Bar dataKey="value" radius={[5, 5, 0, 0]} fill={ACCENT} barSize={26}>
          <LabelList
            dataKey="value"
            position="top"
            formatter={(v: number) => fmtM(v)}
            style={{ fontSize: 10, fill: "currentColor", fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Donut — LKR 5M trade-spend split by channel. */
export function ChannelDonut({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const colorByName: Record<string, string> = {
    Discount: AMBER,
    Merchandising: ACCENT,
    Promotional: GREEN,
  };
  const total = data.reduce((s, d) => s + d.value, 0);
  const fmtLKR = (n: number) =>
    `LKR ${(n / 1_000_000).toFixed(2)}M`;
  return (
    <div className="flex items-center gap-3">
      <div className="w-[44%] shrink-0">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={50}
              outerRadius={82}
              paddingAngle={2}
              stroke="none"
            >
              {data.map((d, i) => (
                <Cell key={i} fill={colorByName[d.name] ?? GREY} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }: any) => {
                if (!active || !payload?.length) return null;
                const p = payload[0];
                return (
                  <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md">
                    <div className="font-semibold">{p.payload.name}</div>
                    <div className="text-muted-foreground">{fmtLKR(p.value)}</div>
                  </div>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-1 flex-col gap-2.5 text-sm">
        {data.map((d) => (
          <li key={d.name} className="flex flex-col gap-0.5">
            <span className="flex items-center gap-2 font-medium">
              <span
                className="inline-block h-3 w-3 shrink-0 rounded-sm"
                style={{ background: colorByName[d.name] ?? GREY }}
              />
              {d.name}
            </span>
            <span className="whitespace-nowrap pl-5 text-muted-foreground">
              {fmtLKR(d.value)}
              <span className="ml-1 text-xs">
                ({total ? Math.round((d.value / total) * 100) : 0}%)
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
