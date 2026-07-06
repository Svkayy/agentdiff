import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GraphNodeCard, type NodeData } from "@/components/nodes/GraphNodeCard";
import type { AgentGraph as AgentGraphModel, GraphNode } from "@/types";

const nodeTypes = { diff: GraphNodeCard };

const COL_AGENT_X = 40;
const COL_TOOL_X = 470;
const ROW_DY = 150;

export function AgentGraph({
  graph,
  selectedId,
  onSelect,
}: {
  graph: AgentGraphModel;
  selectedId: string | null;
  onSelect: (n: GraphNode) => void;
}) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const agents = graph.nodes.filter((n) => n.kind === "agent");
    const tools = graph.nodes.filter((n) => n.kind !== "agent");
    const stoppedIds = new Set(graph.nodes.filter((n) => n.stopped).map((n) => n.id));

    const place = (list: GraphNode[], x: number): Node<NodeData>[] =>
      list.map((node, i) => ({
        id: node.id,
        type: "diff",
        position: { x, y: i * ROW_DY + 32 },
        data: { node },
        selected: node.id === selectedId,
        // Keyboard-focusable: tabIndex=0 + Enter/Space triggers the same
        // selection path as a click (React Flow's built-in node a11y).
        focusable: true,
        ariaLabel: `${node.kind === "agent" ? "Agent" : "Tool"} ${node.label}${
          node.stopped ? ", stopped firing" : ""
        }`,
      }));

    const rfNodes: Node<NodeData>[] = [...place(agents, COL_AGENT_X), ...place(tools, COL_TOOL_X)];

    const rfEdges: Edge[] = graph.edges.map((e) => {
      const broken = stoppedIds.has(e.source) || stoppedIds.has(e.target);
      return {
        id: `${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        className: broken ? "stopped" : undefined,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: broken ? "#ea580c" : "#7dd3fc",
          width: 18,
          height: 18,
        },
      };
    });

    return { rfNodes, rfEdges };
  }, [graph, selectedId]);

  const onNodeClick: NodeMouseHandler<Node<NodeData>> = (_, node) => {
    onSelect(node.data.node);
  };

  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        No comparison data in this run.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      onNodeClick={onNodeClick}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      nodesFocusable
      minZoom={0.4}
      maxZoom={1.5}
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#94a3b8" />
    </ReactFlow>
  );
}
