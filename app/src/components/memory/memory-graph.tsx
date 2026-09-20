/**
 * MemoryGraph - SVG force-directed graph visualization.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryStore } from "@/lib/memory-store";
import { MemoryType } from "@/lib/types/memory";
import { Card } from "@/components/ui/card";

const MEMORY_TYPE_COLORS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "#3b82f6",
  [MemoryType.PREFERENCE]: "#10b981",
  [MemoryType.PROCEDURE]: "#f59e0b",
  [MemoryType.CONTEXT]: "#8b5cf6",
  [MemoryType.STRATEGY]: "#ec4899",
  [MemoryType.EPISODE]: "#6366f1",
};

const NODE_RADIUS = 20;
const MIN_NODE_RADIUS = 10;
const MAX_NODE_RADIUS = 35;

interface GraphState {
  nodes: Array<{ id: string; x: number; y: number; vx: number; vy: number }>;
  links: Array<{ source: string; target: string }>;
}

export function MemoryGraph() {
  const { t } = useTranslation("memoryUi");
  const { graphData, setSelectedId, selectedId } = useMemoryStore();
  const svgRef = useRef<SVGSVGElement>(null);
  const [state, setState] = useState<GraphState>({
    nodes: [],
    links: [],
  });
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Initialize node positions
  useEffect(() => {
    const width = svgRef.current?.clientWidth || 800;
    const height = svgRef.current?.clientHeight || 600;

    const nodes = graphData.nodes.map((node) => {
      const energyRadius =
        MIN_NODE_RADIUS + (node.energy / 100) * (MAX_NODE_RADIUS - MIN_NODE_RADIUS);

      return {
        id: node.id,
        x: node.x ?? width / 2 + (Math.random() - 0.5) * 200,
        y: node.y ?? height / 2 + (Math.random() - 0.5) * 200,
        vx: 0,
        vy: 0,
        radius: energyRadius,
      };
    });

    const links = graphData.links.map((link) => ({
      source: typeof link.source === "string" ? link.source : link.source,
      target: typeof link.target === "string" ? link.target : link.target,
    }));

    setState({ nodes, links });
  }, [graphData]);

  // Force simulation
  useEffect(() => {
    if (state.nodes.length === 0) return;

    let animationFrame: number;
    let iteration = 0;
    const maxIterations = 300;

    const simulate = () => {
      if (iteration >= maxIterations) return;

      setState((prev) => {
        const nodes = [...prev.nodes];
        const width = svgRef.current?.clientWidth || 800;
        const height = svgRef.current?.clientHeight || 600;

        // Repulsion
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const dx = nodes[j].x - nodes[i].x;
            const dy = nodes[j].y - nodes[i].y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = 500 / (dist * dist);

            nodes[i].vx -= (dx / dist) * force;
            nodes[i].vy -= (dy / dist) * force;
            nodes[j].vx += (dx / dist) * force;
            nodes[j].vy += (dy / dist) * force;
          }
        }

        // Attraction (links)
        for (const link of prev.links) {
          const source = nodes.find((n) => n.id === link.source);
          const target = nodes.find((n) => n.id === link.target);
          if (!source || !target) continue;

          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 100) * 0.01;

          source.vx += (dx / dist) * force;
          source.vy += (dy / dist) * force;
          target.vx -= (dx / dist) * force;
          target.vy -= (dy / dist) * force;
        }

        // Center gravity
        for (const node of nodes) {
          node.vx += (width / 2 - node.x) * 0.0005;
          node.vy += (height / 2 - node.y) * 0.0005;
        }

        // Update positions
        for (const node of nodes) {
          node.vx *= 0.9;
          node.vy *= 0.9;
          node.x += node.vx;
          node.y += node.vy;

          // Boundary
          node.x = Math.max(NODE_RADIUS, Math.min(width - NODE_RADIUS, node.x));
          node.y = Math.max(NODE_RADIUS, Math.min(height - NODE_RADIUS, node.y));
        }

        return { nodes, links: prev.links };
      });

      iteration++;
      animationFrame = requestAnimationFrame(simulate);
    };

    simulate();

    return () => cancelAnimationFrame(animationFrame);
  }, [state.nodes.length, state.links.length]);

  // Pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === svgRef.current) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setTransform({
        ...transform,
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform({
      ...transform,
      scale: Math.max(0.1, Math.min(5, transform.scale * delta)),
    });
  };

  // Node click
  const handleNodeClick = (nodeId: string) => {
    setSelectedId(nodeId);
  };

  return (
    <div className="w-full h-full relative bg-background">
      <svg
        ref={svgRef}
        className="w-full h-full"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
      >
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
          {/* Links */}
          {state.links.map((link, i) => {
            const source = state.nodes.find((n) => n.id === link.source);
            const target = state.nodes.find((n) => n.id === link.target);
            if (!source || !target) return null;

            return (
              <line
                key={i}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="hsl(var(--border))"
                strokeWidth="2"
                opacity="0.5"
              />
            );
          })}

          {/* Nodes */}
          {state.nodes.map((node) => {
            const graphNode = graphData.nodes.find((n) => n.id === node.id);
            if (!graphNode) return null;

            const color = MEMORY_TYPE_COLORS[graphNode.type];
            const isSelected = selectedId === node.id;
            const isHovered = hoveredNode === node.id;
            const radius = graphNode.radius || NODE_RADIUS;

            return (
              <g
                key={node.id}
                onClick={() => handleNodeClick(node.id)}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                style={{ cursor: "pointer" }}
              >
                {/* Node circle */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius}
                  fill={color}
                  stroke={isSelected ? "white" : "transparent"}
                  strokeWidth={isSelected ? 3 : 0}
                  opacity={isHovered ? 1 : 0.8}
                />

                {/* Label */}
                <text
                  x={node.x}
                  y={node.y + radius + 15}
                  textAnchor="middle"
                  fontSize="12"
                  fill="hsl(var(--foreground))"
                  pointerEvents="none"
                >
                  {graphNode.label}
                </text>

                {/* Tooltip on hover */}
                {isHovered && (
                  <g>
                    <rect
                      x={node.x + radius + 5}
                      y={node.y - 30}
                      width="120"
                      height="60"
                      fill="hsl(var(--popover))"
                      rx="4"
                      opacity="0.95"
                    />
                    <text
                      x={node.x + radius + 15}
                      y={node.y - 10}
                      fontSize="11"
                      fill="hsl(var(--popover-foreground))"
                    >
                      {t("graph.tooltipType", { value: graphNode.type })}
                    </text>
                    <text
                      x={node.x + radius + 15}
                      y={node.y + 5}
                      fontSize="11"
                      fill="hsl(var(--popover-foreground))"
                    >
                      {t("graph.tooltipEnergy", { value: graphNode.energy })}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Legend */}
      <Card className="absolute bottom-4 left-4 p-3">
        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium">{t("graph.typeLabel")}</div>
          {Object.values(MemoryType).map((type) => (
            <div key={type} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: MEMORY_TYPE_COLORS[type] }}
              />
              <span className="text-xs">{type}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Zoom controls */}
      <div className="absolute bottom-4 right-4 flex gap-2">
        <button
          className="p-2 bg-card border rounded-md hover:bg-accent"
          onClick={() =>
            setTransform({ ...transform, scale: Math.max(0.1, transform.scale * 0.9) })
          }
        >
          −
        </button>
        <button
          className="p-2 bg-card border rounded-md hover:bg-accent"
          onClick={() => setTransform({ ...transform, scale: Math.min(5, transform.scale * 1.1) })}
        >
          +
        </button>
        <button
          className="p-2 bg-card border rounded-md hover:bg-accent"
          onClick={() => setTransform({ x: 0, y: 0, scale: 1 })}
        >
          ↺
        </button>
      </div>
    </div>
  );
}
