"use client";

import type { ComponentType, Ref } from "react";
import type {
  GraphData,
  LinkObject,
  NodeObject,
} from "force-graph";
import ForceGraph2DKapsule from "force-graph";
import fromKapsule from "react-kapsule";

type Accessor<In, Out> = Out | string | ((obj: In) => Out);

export interface ForceGraph2DMethods {
  emitParticle: (link: LinkObject) => void;
  d3Force: (...args: unknown[]) => unknown;
  d3ReheatSimulation: () => void;
  stopAnimation: () => void;
  pauseAnimation: () => void;
  resumeAnimation: () => void;
  centerAt: (x?: number, y?: number, durationMs?: number) => void;
  zoom: (scale?: number, durationMs?: number) => number | void;
  zoomToFit: (durationMs?: number, padding?: number) => void;
  getGraphBbox: () => unknown;
  screen2GraphCoords: (x: number, y: number) => { x: number; y: number };
  graph2ScreenCoords: (x: number, y: number) => { x: number; y: number };
}

export interface ForceGraph2DProps<
  N extends NodeObject = NodeObject,
  L extends LinkObject<N> = LinkObject<N>,
> {
  width?: number;
  height?: number;
  graphData?: GraphData<N, L>;
  backgroundColor?: string;
  nodeLabel?: Accessor<N, string | HTMLElement>;
  nodeColor?: Accessor<N, string>;
  nodeVal?: Accessor<N, number>;
  nodeCanvasObject?: (
    node: N,
    ctx: CanvasRenderingContext2D,
    globalScale: number
  ) => void;
  linkColor?: Accessor<L, string>;
  linkWidth?: Accessor<L, number>;
  linkDirectionalArrowLength?: Accessor<L, number>;
  linkDirectionalArrowRelPos?: Accessor<L, number>;
  onNodeClick?: (node: N, event: MouseEvent) => void;
  onBackgroundClick?: (event: MouseEvent) => void;
  cooldownTicks?: number;
}

const ForceGraph2D = fromKapsule<ForceGraph2DProps, ForceGraph2DMethods>(
  ForceGraph2DKapsule as never,
  {
    methodNames: [
      "emitParticle",
      "d3Force",
      "d3ReheatSimulation",
      "stopAnimation",
      "pauseAnimation",
      "resumeAnimation",
      "centerAt",
      "zoom",
      "zoomToFit",
      "getGraphBbox",
      "screen2GraphCoords",
      "graph2ScreenCoords",
    ],
  }
) as ComponentType<ForceGraph2DProps & { ref?: Ref<ForceGraph2DMethods> }>;

export default ForceGraph2D;
