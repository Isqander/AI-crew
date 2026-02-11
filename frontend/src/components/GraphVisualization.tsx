import { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import { useAuthStore } from '../store/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

// Types from ARCHITECTURE_V2
interface AgentConfig {
  model: string
  temperature: number
  fallback_model: string | null
  endpoint: string
}

interface PromptInfo {
  system: string
  templates: string[]
}

interface GraphTopology {
  graph_id: string
  topology: { nodes: any[]; edges: any[] }
  agents: Record<string, AgentConfig>
  prompts: Record<string, PromptInfo>
  manifest: Record<string, any>
}

// Props
interface Props {
  graphId: string
  currentAgent?: string
}

// Status helper
function getNodeStatus(
  nodeId: string,
  currentAgent?: string,
  _completedAgents?: string[]
): 'active' | 'completed' | 'pending' {
  if (nodeId === currentAgent) return 'active'
  // Simplified: mark as completed if agent order is before current
  return 'pending'
}

// Dagre layout
function layoutWithDagre(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 })

  nodes.forEach((node) => g.setNode(node.id, { width: 220, height: 80 }))
  edges.forEach((edge) => g.setEdge(edge.source, edge.target))

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return { ...node, position: { x: pos.x - 110, y: pos.y - 40 } }
  })

  return { nodes: layoutedNodes, edges }
}

// Custom Agent Node
function AgentNode({ data }: { data: any }) {
  const borderColor =
    data.status === 'active'
      ? 'border-cyan-500'
      : data.status === 'completed'
        ? 'border-green-500'
        : 'border-slate-600'
  const animation = data.status === 'active' ? 'animate-pulse' : ''

  return (
    <div
      className={`bg-slate-800 rounded-lg border-2 ${borderColor} ${animation} px-4 py-3 min-w-[200px] shadow-lg`}
    >
      <Handle type="target" position={Position.Top} className="!bg-cyan-500" />
      <div className="text-white font-semibold text-sm">{data.label}</div>
      {data.model && (
        <span className="inline-block mt-1 px-2 py-0.5 bg-cyan-900/50 text-cyan-300 text-xs rounded-full">
          {data.model}
        </span>
      )}
      {data.fallbackModel && (
        <div className="text-slate-500 text-xs mt-1">fallback: {data.fallbackModel}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-cyan-500" />
    </div>
  )
}

// Node types registration
const nodeTypes = { agentNode: AgentNode }

export function GraphVisualization({ graphId, currentAgent }: Props) {
  const [topology, setTopology] = useState<GraphTopology | null>(null)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [loading, setLoading] = useState(true)

  // Fetch topology
  useEffect(() => {
    const fetchTopology = async () => {
      const token = useAuthStore.getState().accessToken
      try {
        const resp = await fetch(`${API_URL}/graph/topology/${graphId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (resp.ok) {
          const data = await resp.json()
          setTopology(data)
        }
      } catch (err) {
        console.error('Failed to fetch topology:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchTopology()
  }, [graphId])

  // Convert topology to React Flow
  useEffect(() => {
    if (!topology) return

    const agents = topology.manifest?.agents || []
    const rfNodes: Node[] = (topology.topology?.nodes || [])
      .filter((n: any) => n.id !== '__start__' && n.id !== '__end__')
      .map((n: any) => {
        const agentDef = agents.find((a: any) => a.id === n.id)
        const config = topology.agents[n.id]
        return {
          id: n.id,
          type: 'agentNode',
          data: {
            label: agentDef?.display_name || n.id,
            model: config?.model,
            fallbackModel: config?.fallback_model,
            status: getNodeStatus(n.id, currentAgent),
            systemPrompt: topology.prompts[n.id]?.system,
            templates: topology.prompts[n.id]?.templates,
          },
          position: { x: 0, y: 0 },
        }
      })

    const nodeIds = new Set(rfNodes.map((n) => n.id))
    const rfEdges: Edge[] = (topology.topology?.edges || [])
      .filter((e: any) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e: any, i: number) => ({
        id: `${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        animated: e.source === currentAgent,
        style: e.conditional ? { strokeDasharray: '5,5', stroke: '#64748b' } : { stroke: '#06b6d4' },
        label: e.data || '',
        labelStyle: { fill: '#94a3b8', fontSize: 10 },
      }))

    const layouted = layoutWithDagre(rfNodes, rfEdges)
    setNodes(layouted.nodes)
    setEdges(layouted.edges)
  }, [topology, currentAgent, setNodes, setEdges])

  const onNodeClick = useCallback(
    (_: any, node: Node) => {
      setSelectedNode(node.id === selectedNode ? null : node.id)
    },
    [selectedNode]
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">Loading graph...</div>
    )
  }

  if (!topology) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        Graph not available
      </div>
    )
  }

  const selectedAgent = selectedNode ? topology.agents[selectedNode] : null
  const selectedPrompt = selectedNode ? topology.prompts[selectedNode] : null

  return (
    <div className="flex h-[500px] bg-slate-900 rounded-lg overflow-hidden border border-slate-700">
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#334155" gap={20} />
          <Controls className="!bg-slate-800 !border-slate-700 !text-white" />
          <MiniMap
            className="!bg-slate-800 !border-slate-700"
            nodeColor="#0891b2"
            maskColor="rgb(15, 23, 42, 0.7)"
          />
        </ReactFlow>
      </div>
      {selectedNode && (
        <div className="w-72 bg-slate-800 border-l border-slate-700 p-4 overflow-y-auto">
          <h3 className="text-white font-semibold text-sm mb-3">{selectedNode}</h3>
          {selectedAgent && (
            <div className="space-y-2 text-xs">
              <div>
                <span className="text-slate-400">Model:</span>{' '}
                <span className="text-cyan-300">{selectedAgent.model}</span>
              </div>
              <div>
                <span className="text-slate-400">Temperature:</span>{' '}
                <span className="text-white">{selectedAgent.temperature}</span>
              </div>
              {selectedAgent.fallback_model && (
                <div>
                  <span className="text-slate-400">Fallback:</span>{' '}
                  <span className="text-yellow-300">{selectedAgent.fallback_model}</span>
                </div>
              )}
              <div>
                <span className="text-slate-400">Endpoint:</span>{' '}
                <span className="text-white">{selectedAgent.endpoint}</span>
              </div>
            </div>
          )}
          {selectedPrompt && (
            <div className="mt-4">
              <div className="text-slate-400 text-xs mb-1">System prompt:</div>
              <div className="text-slate-300 text-xs bg-slate-900 rounded p-2 max-h-40 overflow-y-auto">
                {selectedPrompt.system}
              </div>
              {selectedPrompt.templates.length > 0 && (
                <div className="mt-2">
                  <div className="text-slate-400 text-xs mb-1">Templates:</div>
                  <div className="flex flex-wrap gap-1">
                    {selectedPrompt.templates.map((t) => (
                      <span
                        key={t}
                        className="px-2 py-0.5 bg-slate-700 text-slate-300 text-xs rounded"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
