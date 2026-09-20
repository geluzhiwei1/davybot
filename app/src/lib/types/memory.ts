/**
 * Memory type definitions.
 */

export enum MemoryType {
  FACT = "fact",
  PREFERENCE = "preference",
  PROCEDURE = "procedure",
  CONTEXT = "context",
  STRATEGY = "strategy",
  EPISODE = "episode",
}

export interface MemoryEntry {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  validStart: string;
  validEnd?: string;
  confidence: number;
  energy: number;
  accessCount: number;
  memoryType: MemoryType;
  keywords: string[];
  sourceEventId?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: MemoryType;
  energy: number;
  x?: number;
  y?: number;
  radius?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  label: string;
  confidence: number;
  id?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface MemoryFilters {
  type?: MemoryType | "all";
  minConfidence?: number;
  minEnergy?: number;
  dateFrom?: string;
  dateTo?: string;
  subject?: string;
  keyword?: string;
  onlyValid?: boolean;
}

export interface MemoryStats {
  total: number;
  byType: Partial<Record<MemoryType, number>>;
  avgConfidence: number;
  avgEnergy: number;
  mostAccessed: MemoryEntry[];
  recent: MemoryEntry[];
  lowEnergy: number;
}

export interface TimelineEntry {
  date: string;
  memories: MemoryEntry[];
}

export interface CreateMemoryParams {
  subject: string;
  predicate: string;
  object: string;
  memoryType: MemoryType;
  confidence: number;
  energy: number;
  keywords: string[];
  validStart?: string;
  validEnd?: string;
}

export interface UpdateMemoryParams {
  subject?: string;
  predicate?: string;
  object?: string;
  memoryType?: MemoryType;
  confidence?: number;
  energy?: number;
  keywords?: string[];
  validStart?: string;
  validEnd?: string;
}
