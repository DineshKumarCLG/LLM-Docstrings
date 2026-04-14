import { useEffect, useRef, useState, useMemo } from "react";
import * as d3 from "d3";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "@/api/client";
import { AlertTriangle, Loader2, Settings2, RotateCcw, Network } from "lucide-react";
import type { GraphNode, GraphEdge } from "@/types";
import { CATEGORY_COLORS, type BCVCategory } from "@/types";
import { SpotlightCard } from "@/components/ui";
import { cn } from "@/lib/utils";

interface KnowledgeGraphProps {
  analysisId: string;
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  type: string;
  name: string;
  category?: string;
  signature?: string;
  fullText?: string;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  type: string;
}

/* ── Node colors ───────────────────────────────────────────────── */
const NODE_COLORS: Record<string, { base: string; light: string }> = {
  module:    { base: "#0d9488", light: "#5eead4" },
  class:     { base: "#0891b2", light: "#67e8f9" },
  function:  { base: "#10b981", light: "#6ee7b7" },
  method:    { base: "#14b8a6", light: "#5eead4" },
  import:    { base: "#64748b", light: "#cbd5e1" },
  claim:     { base: "#f59e0b", light: "#fcd34d" },
  violation: { base: "#ef4444", light: "#fca5a5" },
};

const EDGE_COLORS: Record<string, { color: string; dash?: string }> = {
  contains:    { color: "#94a3b8" },
  has_method:  { color: "#0891b2" },
  calls:       { color: "#14b8a6", dash: "6,3" },
  imports:     { color: "#cbd5e1", dash: "4,4" },
  inherits:    { color: "#8b5cf6" },
  has_claim:   { color: "#f59e0b" },
  violated_by: { color: "#ef4444" },
};

const NODE_SIZES: Record<string, number> = {
  module: 1.6, class: 1.4, function: 1, method: 1, import: 0.7, claim: 0.9, violation: 1.1,
};

/* ── Legend ─────────────────────────────────────────────────────── */
function GraphLegend() {
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.2 }}
      className="absolute top-4 left-4 z-10 rounded-2xl p-4 glass-strong text-[11px] select-none shadow-xl"
    >
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">Legend</p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-2">
        {(["module", "class", "function", "method", "claim", "violation"] as const).map(t => {
          const c = NODE_COLORS[t];
          return (
            <div key={t} className="flex items-center gap-2">
              <div 
                className="w-4 h-4 rounded-full skeu-raised"
                style={{ 
                  background: `linear-gradient(145deg, ${c.light} 0%, ${c.base} 100%)`,
                  boxShadow: `0 2px 4px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.4)`
                }}
              />
              <span className="text-muted-foreground capitalize font-medium">{t}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 pt-2.5 border-t border-foreground/[0.06] grid grid-cols-2 gap-x-5 gap-y-2">
        {([
          ["contains", "Contains"], ["calls", "Calls"], ["has_claim", "Claim"], ["violated_by", "Violated"],
        ] as const).map(([k, l]) => (
          <div key={k} className="flex items-center gap-2">
            <svg width="18" height="6">
              <line x1="0" y1="3" x2="18" y2="3"
                stroke={EDGE_COLORS[k].color} strokeWidth="2" 
                strokeDasharray={EDGE_COLORS[k].dash || "none"}
                strokeLinecap="round" 
              />
            </svg>
            <span className="text-muted-foreground font-medium">{l}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Settings panel ────────────────────────────────────────────── */
interface PhysicsSettings {
  linkDistance: number;
  chargeStrength: number;
  centerForce: number;
  nodeSize: number;
  showLabels: boolean;
  showArrows: boolean;
  animate: boolean;
}

const DEFAULTS: PhysicsSettings = {
  linkDistance: 100,
  chargeStrength: -300,
  centerForce: 0.4,
  nodeSize: 12,
  showLabels: true,
  showArrows: true,
  animate: true,
};

function Slider({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex justify-between mb-1.5">
        <span className="text-[11px] font-semibold text-muted-foreground">{label}</span>
        <span className="text-[11px] font-mono text-foreground/50 tabular-nums skeu-inset rounded-md px-1.5 py-0.5">
          {step && step < 1 ? value.toFixed(1) : Math.abs(value)}
        </span>
      </div>
      <div className="h-[30px] rounded-xl skeu-inset flex items-center px-3">
        <input type="range" min={min} max={max} step={step || 1} value={value}
          onChange={e => onChange(+e.target.value)}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-transparent
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white
            [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-primary/60
            [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.9)]
            [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing
            [&::-webkit-slider-track]:h-1.5 [&::-webkit-slider-track]:rounded-full
            [&::-webkit-slider-track]:bg-gradient-to-r [&::-webkit-slider-track]:from-primary/25 [&::-webkit-slider-track]:to-primary/5"
        />
      </div>
    </div>
  );
}

function ControlPanel({ settings, onChange, onReset }: {
  settings: PhysicsSettings; onChange: (s: PhysicsSettings) => void; onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute top-4 right-4 z-10 flex gap-2">
      <motion.button
        whileHover={{ scale: 1.05, y: -1 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setOpen(!open)} title="Physics Settings"
        className={cn("skeu-raised rounded-xl p-2.5 transition-all", open && "ring-2 ring-primary/30 glow-teal")}
      >
        <Settings2 className="h-4 w-4 text-foreground/60" />
      </motion.button>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
          className="absolute top-12 right-0 w-72 rounded-2xl glass-strong p-5 space-y-4 shadow-xl"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-foreground">Physics</span>
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={onReset}
              className="text-[11px] text-primary hover:text-primary/70 font-semibold flex items-center gap-1 skeu-raised rounded-lg px-2 py-1"
            >
              <RotateCcw className="h-3 w-3" /> Reset
            </motion.button>
          </div>
          <div className="space-y-3">
            <Slider label="Link distance" value={settings.linkDistance} min={30} max={250} onChange={v => onChange({ ...settings, linkDistance: v })} />
            <Slider label="Repel force" value={settings.chargeStrength} min={-600} max={-30} onChange={v => onChange({ ...settings, chargeStrength: v })} />
            <Slider label="Center pull" value={settings.centerForce} min={0} max={1} step={0.05} onChange={v => onChange({ ...settings, centerForce: v })} />
            <Slider label="Node size" value={settings.nodeSize} min={6} max={24} onChange={v => onChange({ ...settings, nodeSize: v })} />
          </div>
          <div className="pt-3 border-t border-foreground/[0.06] space-y-2.5">
            {([["showLabels", "Labels"], ["showArrows", "Arrows"], ["animate", "Animate"]] as const).map(([k, l]) => (
              <label key={k} className="flex items-center gap-2.5 text-[12px] text-foreground/70 cursor-pointer select-none">
                <span 
                  className={cn(
                    "w-9 h-[20px] rounded-full relative transition-all duration-200",
                    settings[k] ? "bg-gradient-to-r from-primary to-primary/80 shadow-[0_0_8px_hsla(var(--primary)/0.3)]" : "skeu-inset"
                  )}
                  onClick={() => onChange({ ...settings, [k]: !settings[k] })}
                >
                  <span className={cn(
                    "absolute top-[2px] w-4 h-4 rounded-full bg-white transition-transform duration-200",
                    "shadow-[0_1px_4px_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.9)]",
                    settings[k] ? "translate-x-[18px]" : "translate-x-[2px]"
                  )} />
                </span>
                <span className="font-medium">{l}</span>
              </label>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────────── */
export default function KnowledgeGraph({ analysisId }: KnowledgeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const [hovered, setHovered] = useState<SimNode | null>(null);
  const [settings, setSettings] = useState<PhysicsSettings>(DEFAULTS);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const { data, isLoading, error } = useQuery({
    queryKey: ["graph", analysisId],
    queryFn: () => analysisApi.getGraph(analysisId).then(r => r.data),
    enabled: !!analysisId,
  });

  const graph = useMemo(() => {
    if (!data?.graph) return { nodes: [] as SimNode[], links: [] as SimLink[] };
    const nodeCount = data.graph.nodes.length;
    const nodes: SimNode[] = data.graph.nodes.map((n: GraphNode, i: number) => {
      // Initialize positions in a circle around center
      const angle = (i / Math.max(nodeCount, 1)) * 2 * Math.PI;
      const radius = 150;
      return {
        id: n.id, 
        type: n.type, 
        name: n.name,
        category: n.category, 
        signature: n.signature, 
        fullText: n.fullText,
        x: 400 + radius * Math.cos(angle),
        y: 300 + radius * Math.sin(angle),
      };
    });
    const ids = new Set(nodes.map(n => n.id));
    const links: SimLink[] = data.graph.edges
      .filter((e: GraphEdge) => ids.has(e.source) && ids.has(e.target))
      .map((e: GraphEdge) => ({ source: e.source, target: e.target, type: e.type }));
    return { nodes, links };
  }, [data]);

  /* ── D3 render ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!svgRef.current || !containerRef.current || graph.nodes.length === 0) return;
    
    // Small delay to ensure container has dimensions
    const timeoutId = setTimeout(() => {
      if (!svgRef.current || !containerRef.current) return;
      
      const W = containerRef.current.clientWidth || 800;
      const H = containerRef.current.clientHeight || 600;
      const currentSettings = settingsRef.current;
      const R = currentSettings.nodeSize;

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();
      svg.attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);

      const g = svg.append("g");
      svg.call(d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.15, 4])
        .on("zoom", e => g.attr("transform", e.transform)));

      const defs = svg.append("defs");

      // Create gradients for each node
      graph.nodes.forEach(n => {
        const c = NODE_COLORS[n.type] || NODE_COLORS.function;
        const grad = defs.append("linearGradient")
          .attr("id", `node-grad-${n.id}`)
          .attr("x1", "0%").attr("y1", "0%")
          .attr("x2", "100%").attr("y2", "100%");
        grad.append("stop").attr("offset", "0%").attr("stop-color", c.light);
        grad.append("stop").attr("offset", "100%").attr("stop-color", c.base);
      });

      // Arrow markers
      Object.entries(EDGE_COLORS).forEach(([type, { color }]) => {
        defs.append("marker").attr("id", `arrow-${type}`)
          .attr("viewBox", "0 -4 8 8").attr("refX", 18).attr("refY", 0)
          .attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
          .append("path").attr("d", "M0,-3L8,0L0,3Z").attr("fill", color).attr("opacity", 0.6);
      });

      // Drop shadow filter
      const shadow = defs.append("filter").attr("id", "node-shadow")
        .attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
      shadow.append("feDropShadow")
        .attr("dx", 0).attr("dy", 2).attr("stdDeviation", 3)
        .attr("flood-color", "rgba(0,0,0,0.2)");

      // Glow filter for hover
      const glow = defs.append("filter").attr("id", "node-glow")
        .attr("x", "-100%").attr("y", "-100%").attr("width", "300%").attr("height", "300%");
      glow.append("feGaussianBlur").attr("stdDeviation", 6).attr("result", "blur");
      const merge = glow.append("feMerge");
      merge.append("feMergeNode").attr("in", "blur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");

      // Update node positions to center of actual container
      graph.nodes.forEach((n, i) => {
        const angle = (i / Math.max(graph.nodes.length, 1)) * 2 * Math.PI;
        const radius = Math.min(W, H) * 0.25;
        n.x = W / 2 + radius * Math.cos(angle);
        n.y = H / 2 + radius * Math.sin(angle);
      });

      /* ── Simulation ──────────────────────────────────────────── */
      const sim = d3.forceSimulation<SimNode>(graph.nodes)
        .force("link", d3.forceLink<SimNode, SimLink>(graph.links).id(d => d.id).distance(currentSettings.linkDistance))
        .force("charge", d3.forceManyBody().strength(currentSettings.chargeStrength))
        .force("center", d3.forceCenter(W / 2, H / 2).strength(currentSettings.centerForce))
        .force("collide", d3.forceCollide().radius(d => (NODE_SIZES[(d as SimNode).type] || 1) * R + 12))
        .alpha(1)
        .alphaDecay(0.02);
      simRef.current = sim;

      /* ── Edges ───────────────────────────────────────────────── */
      const linkG = g.append("g").attr("class", "links");
      const link = linkG.selectAll("line").data(graph.links).join("line")
        .attr("stroke", d => EDGE_COLORS[d.type]?.color || "#cbd5e1")
        .attr("stroke-width", 1.5)
        .attr("stroke-opacity", 0.4)
        .attr("stroke-linecap", "round")
        .attr("stroke-dasharray", d => EDGE_COLORS[d.type]?.dash || "none")
        .attr("marker-end", d => currentSettings.showArrows ? `url(#arrow-${d.type})` : null);

      /* ── Nodes ───────────────────────────────────────────────── */
      const nodeG = g.append("g").attr("class", "nodes");
      const nodeEl = nodeG.selectAll<SVGGElement, SimNode>("g").data(graph.nodes).join("g")
        .style("cursor", "grab")
        .attr("transform", d => `translate(${d.x},${d.y})`)
        .call(d3.drag<SVGGElement, SimNode>()
          .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

      const nr = (d: SimNode) => (NODE_SIZES[d.type] || 1) * R;

      // Main node circle with gradient and shadow
      nodeEl.append("circle")
        .attr("class", "node-circle")
        .attr("r", d => nr(d))
        .attr("fill", d => `url(#node-grad-${d.id})`)
        .attr("stroke", "rgba(255,255,255,0.6)")
        .attr("stroke-width", 2)
        .attr("filter", "url(#node-shadow)");

      // Top highlight for 3D effect
      nodeEl.append("ellipse")
        .attr("class", "highlight")
        .attr("rx", d => nr(d) * 0.5)
        .attr("ry", d => nr(d) * 0.25)
        .attr("cy", d => -nr(d) * 0.35)
        .attr("fill", "rgba(255,255,255,0.5)")
        .attr("pointer-events", "none");

      // Hover interactions
      nodeEl
        .on("mouseover", function(_, d) {
          setHovered(d);
          d3.select(this).select(".node-circle")
            .transition().duration(150)
            .attr("filter", "url(#node-glow)")
            .attr("stroke-width", 3);
          
          link.transition().duration(150)
            .attr("stroke-opacity", l => 
              ((l.source as SimNode).id === d.id || (l.target as SimNode).id === d.id) ? 0.8 : 0.1
            );
          
          nodeEl.transition().duration(150)
            .attr("opacity", n => {
              if (n.id === d.id) return 1;
              const connected = graph.links.some(l =>
                ((l.source as SimNode).id === d.id && (l.target as SimNode).id === n.id) ||
                ((l.target as SimNode).id === d.id && (l.source as SimNode).id === n.id)
              );
              return connected ? 1 : 0.25;
            });
        })
        .on("mouseout", function() {
          setHovered(null);
          d3.select(this).select(".node-circle")
            .transition().duration(200)
            .attr("filter", "url(#node-shadow)")
            .attr("stroke-width", 2);
          
          link.transition().duration(200).attr("stroke-opacity", 0.4);
          nodeEl.transition().duration(200).attr("opacity", 1);
        });

      /* ── Labels ──────────────────────────────────────────────── */
      const labelG = g.append("g").attr("class", "labels");
      const label = labelG.selectAll("text").data(graph.nodes).join("text")
        .attr("font-size", 10)
        .attr("font-weight", 600)
        .attr("font-family", "'Inter', system-ui, sans-serif")
        .attr("fill", "hsl(210 20% 25%)")
        .attr("text-anchor", "middle")
        .attr("paint-order", "stroke")
        .attr("stroke", "rgba(255,255,255,0.9)")
        .attr("stroke-width", 3)
        .attr("stroke-linejoin", "round")
        .attr("dy", d => nr(d) + 16)
        .attr("x", d => d.x!)
        .attr("y", d => d.y!)
        .attr("opacity", currentSettings.showLabels ? 1 : 0)
        .text(d => d.name);

      /* ── Tick ────────────────────────────────────────────────── */
      sim.on("tick", () => {
        link
          .attr("x1", d => (d.source as SimNode).x!)
          .attr("y1", d => (d.source as SimNode).y!)
          .attr("x2", d => (d.target as SimNode).x!)
          .attr("y2", d => (d.target as SimNode).y!);
        
        nodeEl.attr("transform", d => `translate(${d.x},${d.y})`);
        label.attr("x", d => d.x!).attr("y", d => d.y!);
      });

      if (!currentSettings.animate) sim.tick(120).stop();
    }, 50);
    
    return () => { 
      clearTimeout(timeoutId);
      simRef.current?.stop(); 
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]); // Only re-render when graph data changes, not settings

  /* ── Force updates ─────────────────────────────────────────── */
  useEffect(() => {
    const s = simRef.current;
    if (!s || !containerRef.current) return;
    s.force("link", d3.forceLink<SimNode, SimLink>(graph.links).id(d => d.id).distance(settings.linkDistance))
      .force("charge", d3.forceManyBody().strength(settings.chargeStrength))
      .force("center", d3.forceCenter(containerRef.current.clientWidth / 2, containerRef.current.clientHeight / 2).strength(settings.centerForce))
      .alpha(0.3).restart();
  }, [settings.linkDistance, settings.chargeStrength, settings.centerForce, graph.links]);

  /* ── Loading / error / empty states ────────────────────────── */
  if (isLoading) return (
    <SpotlightCard className="h-[600px] rounded-[var(--radius-2xl)] glass flex items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }} 
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 24 }} 
        className="flex flex-col items-center gap-4"
      >
        <div className="skeu-raised rounded-2xl p-5 glow-teal">
          <Loader2 className="h-7 w-7 animate-spin text-primary" />
        </div>
        <span className="text-xs text-muted-foreground font-semibold tracking-wide">Building knowledge graph…</span>
      </motion.div>
    </SpotlightCard>
  );

  if (error) return (
    <SpotlightCard className="h-[600px] rounded-[var(--radius-2xl)] glass flex items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }} 
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 24 }} 
        className="flex flex-col items-center gap-4"
      >
        <div className="skeu-raised rounded-2xl p-5 glow-danger">
          <AlertTriangle className="h-7 w-7 text-destructive" />
        </div>
        <span className="text-sm text-muted-foreground font-medium">Failed to load graph</span>
      </motion.div>
    </SpotlightCard>
  );

  if (!data || data.graph.nodes.length === 0) return (
    <SpotlightCard className="h-[600px] rounded-[var(--radius-2xl)] glass flex items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }} 
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 24 }} 
        className="flex flex-col items-center gap-4"
      >
        <div className="skeu-raised rounded-2xl p-5">
          <Network className="h-7 w-7 text-muted-foreground/50" />
        </div>
        <span className="text-sm text-muted-foreground font-medium">No graph data available</span>
      </motion.div>
    </SpotlightCard>
  );

  const hoveredColor = hovered ? (NODE_COLORS[hovered.type] || NODE_COLORS.function) : null;

  return (
    <SpotlightCard 
      className="h-[600px] rounded-[var(--radius-2xl)] glass overflow-hidden relative" 
      spotlightColor="rgba(20, 184, 166, 0.06)"
    >
      <div ref={containerRef} className="absolute inset-0">
        <GraphLegend />
        <ControlPanel 
          settings={settings} 
          onChange={setSettings} 
          onReset={() => { setSettings(DEFAULTS); simRef.current?.alpha(1).restart(); }} 
        />

        {/* Tooltip */}
        {hovered && hoveredColor && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="absolute bottom-4 left-4 z-10 rounded-2xl glass-strong p-4 max-w-xs shadow-xl"
          >
            <div className="flex items-center gap-2.5 mb-2">
              <div 
                className="w-5 h-5 rounded-full"
                style={{ 
                  background: `linear-gradient(145deg, ${hoveredColor.light} 0%, ${hoveredColor.base} 100%)`,
                  boxShadow: `0 2px 4px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.4)`
                }}
              />
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{hovered.type}</span>
              {hovered.category && (
                <span 
                  className="text-[9px] font-bold px-1.5 py-0.5 rounded-md text-white shadow-sm"
                  style={{ backgroundColor: CATEGORY_COLORS[hovered.category as BCVCategory] }}
                >
                  {hovered.category}
                </span>
              )}
            </div>
            <p className="text-sm font-semibold text-foreground leading-snug">{hovered.name}</p>
            {hovered.signature && (
              <p className="text-[11px] text-muted-foreground font-mono mt-2 skeu-inset rounded-lg px-2.5 py-1.5 leading-relaxed">
                {hovered.signature}
              </p>
            )}
            {hovered.fullText && (
              <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{hovered.fullText}</p>
            )}
          </motion.div>
        )}

        <svg ref={svgRef} className="w-full h-full" />

        {/* Stats pill */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.3 }}
          className="absolute bottom-4 right-4 z-10 rounded-xl skeu-raised px-4 py-2 text-[11px] font-semibold text-muted-foreground tabular-nums flex items-center gap-2"
        >
          <Network className="h-3.5 w-3.5 text-primary/50" />
          {graph.nodes.length} nodes · {graph.links.length} edges
        </motion.div>
      </div>
    </SpotlightCard>
  );
}
